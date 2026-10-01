"""パブコメの「かんたん要約」（summaries.json）を書くための道具。

使い方:
  python summary_tool.py missing              … 要約がまだない募集中の案件を一覧表示（国・都道府県・市区町村）
  python summary_tool.py read 国 495260170     … その案件の資料（概要PDFなど）の文字を取り出して表示
  python summary_tool.py read 都道府県 8bc4751490
  python summary_tool.py read 市区町村 1a2b3c4d5e
  DEEP=1 python summary_tool.py read 国 495260170   … 案そのもの・新旧対照表まで深く読む（要約を書くときはこちら）

要約は各フォルダの summaries.json に「"案件番号": "要約"」の形で保存する（書き方は ROUTINE.md）。
"""
import html
import io
import os
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
JST = timezone(timedelta(hours=9))
LEVELS = {"国": HERE, "都道府県": HERE / "都道府県レベル", "市区町村": HERE / "市区町村レベル"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"}
LIMIT = int(os.environ.get("LIMIT", 8000))   # 1つの資料から表示する文字数の上限
DEEP = os.environ.get("DEEP") == "1"   # 1 にすると、新旧対照表なども含めて深く読む

_insecure = ssl.create_default_context()
_insecure.check_hostname = False
_insecure.verify_mode = ssl.CERT_NONE


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def open_items(level):
    """その版の、いま募集中の案件を返す。"""
    data = load(LEVELS[level] / "data.json")
    now = datetime.now(JST)
    cut = now.isoformat() if level == "国" else now.date().isoformat()
    excluded = load(LEVELS[level] / "exclude.json")   # 載せないことにした案件は除く
    return [it for it in data.get("items", []) if it.get("deadline") and it["deadline"] >= cut
            and it["id"] not in excluded]


def missing():
    total = 0
    for level, folder in LEVELS.items():
        done = load(folder / "summaries.json")
        for it in open_items(level):
            if it["id"] not in done:
                where = it.get("ministry") or it.get("pref", "")
                print(f'{level} | {it["id"]} | {where} | {it["title"]}')
                total += 1
    print(f"要約が必要な案件: {total} 件")


def download(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        res = urllib.request.urlopen(req, timeout=60)
    except urllib.error.URLError as e:
        if "CERTIFICATE" not in str(e):
            raise
        res = urllib.request.urlopen(req, timeout=60, context=_insecure)
    size = int(res.headers.get("Content-Length") or 0)
    if size > 20_000_000:   # 大きすぎる資料（20MB超）は時間がかかるので読まない
        raise ValueError(f"ファイルが大きすぎます（{size // 1_000_000}MB）。概要版などを読んでください")
    return res.read(), res.headers.get("Content-Type", "")


def to_text(body, ctype):
    """PDF・ワード・HTMLの中身を文字にする。"""
    if body[:4] == b"%PDF":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        out = []
        for page in reader.pages[:15]:
            out.append(page.extract_text() or "")
            if sum(len(x) for x in out) > LIMIT * 8:   # 目次などを飛ばす分、多めに読む
                break
        return "\n".join(out)
    if body[:4] == b"\xd0\xcf\x11\xe0":   # 古い形式のワード・エクセル
        return "（古い形式のファイルのため読めませんでした）"
    if body[:2] == b"PK":
        try:
            import zipfile
            xml = zipfile.ZipFile(io.BytesIO(body)).read("word/document.xml").decode("utf-8", "replace")
            return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml))
        except Exception:
            return "（ワード以外のファイルのため読めませんでした）"
    m = re.search(r"charset=([\w-]+)", ctype) or re.search(rb'charset=["\']?([\w-]+)', body[:4000])
    enc = m.group(1) if m else "utf-8"
    enc = enc.decode() if isinstance(enc, bytes) else enc
    text = body.decode("cp932" if enc.lower() in ("shift_jis", "sjis", "x-sjis", "shift-jis") else enc, "replace")
    text = re.sub(r"(?is)<(script|style|nav|header|footer|noscript)\b.*?</\1>", "", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    # 自治体のページは、本文の始まりの目印より前（メニュー部分）を飛ばす
    m = re.search(r"ここから本文|本文ここから|本文開始|\n\s*本文\s*\n|\n\s*現在地\s*\n", text)
    if m and m.start() < len(text) * 0.7:
        text = text[m.end():]
    return text


def tidy(text):
    text = re.sub(r"[.．…・‥]{4,}", "…", text)
    lines = [re.sub(r"[ \t　]+", " ", x).strip() for x in text.splitlines()]
    lines = [x for x in lines if not re.search(r"…\s*\d+$", x)]   # 目次の行は飛ばす
    # 縦書きのPDFは1文字ずつの行になるので、短い行が続くところはつなげる
    joined = []
    for x in lines:
        if len(x) <= 2 and joined and joined[-1][1]:
            joined[-1] = (joined[-1][0] + x, True)
        else:
            joined.append((x, len(x) <= 2))
    lines = [x for x, _ in joined]
    text = "\n".join(x for x in lines if x)
    return text[:LIMIT] + ("\n…（以下略）" if len(text) > LIMIT else "")


def show(name, url, guide=False):
    print(f"\n===== {name} =====\n{url}")
    try:
        raw = to_text(*download(url))
        text = tidy(raw)
        m = re.search(r"\n\s*要\s*約\s*\n", raw)
        if m and m.start() > LIMIT // 2:   # 評価書などは、後ろのほうにある「要約」を先に見せる
            text = "【資料中の要約】\n" + re.sub(r"\s+", "", raw[m.end(): m.end() + 1500]) + "\n【本文】\n" + text
        if guide:   # 意見募集要領は、出し方の説明より前（趣旨・背景）だけ見せる
            text = re.split(r"\n[^\n]{0,8}(?:資料の?入手|意見.{0,6}(?:提出|募集)(?:期間|方法|先)|意見公募の対象)", text)[0][:1200]
        print(text)
    except Exception as e:
        print(f"（読み込めませんでした：{e}）")


def page_files(url):
    """自治体のページから、PDF・ワードなどの資料へのリンク（名前とURL）を集める。"""
    try:
        body, _ = download(url)
    except Exception:
        return []
    src = body.decode("utf-8", "replace")
    if "charset=shift_jis" in src.lower() or "charset=\"shift_jis" in src.lower():
        src = body.decode("cp932", "replace")
    out = []
    for href, name in re.findall(r'<a[^>]+href="([^"]+\.(?:pdf|docx?|xlsx?)[^"]*)"[^>]*>(.*?)</a>', src, re.I | re.S):
        name = html.unescape(re.sub(r"<[^>]+>|\s+", " ", name)).strip()
        out.append({"name": name, "url": urllib.parse.urljoin(url, html.unescape(href))})
    return out


def read(level, pid):
    it = next((x for x in load(LEVELS[level] / "data.json").get("items", []) if x["id"] == pid), None)
    if not it:
        sys.exit(f"{level}版に案件番号 {pid} が見つかりません")
    det = it.get("detail") or {}
    print(f"正式名：{it['title']}")
    print(f"省庁・自治体：{it.get('ministry') or it.get('pref')}")
    if det.get("rule_name"):
        print(f"定めようとするもの：{det['rule_name']}")
    if det.get("law"):
        print(f"根拠になる法律：{det['law']}")
    if level == "国":
        # 「概要」とつく資料を先に、なければ案そのものを読む
        files = det.get("draft_files", []) + det.get("other_files", [])
        print("資料：" + " ／ ".join(f["name"] for f in files))
        # 概要がなければ、趣旨が書かれていることの多い「意見募集要領」と案そのものを読む
        picked = ([f for f in files if re.search(r"概要|ポイント", f["name"])]
                  or det.get("guide_files", [])[:1] + det.get("draft_files", [])[:1])
        if DEEP:   # 深く読む：概要 → 新旧対照表（何が変わるか）→ 案そのもの の順に読む
            gaiyo = [f for f in files if re.search(r"概要|ポイント|説明", f["name"])]
            shinkyu = [f for f in files if re.search(r"新旧|対照", f["name"]) and f not in gaiyo]
            rest = [f for f in det.get("draft_files", []) if f not in gaiyo + shinkyu]
            picked = (gaiyo + shinkyu + rest) or picked
        for f in picked[:5 if DEEP else 2]:
            show(f["name"], f["url"], f in det.get("guide_files", []))
        if not picked:
            show("e-Govのページ", it["url"])
    else:
        show(f"{level}のページ", it["url"])
        pat = r"概要|案|骨子|ポイント|新旧|対照|本文|計画|方針|条例|規則|基準" if DEEP else r"概要|案|骨子|ポイント"
        cands = det.get("files", [])
        if DEEP:   # 保存された資料一覧がなくても、ページにある PDF などへのリンクを拾う
            cands = cands + page_files(it["url"])
        seen, files = set(), []
        for f in cands:
            if f["url"] in seen or not re.search(pat, f["name"]) or re.search(r"様式|用紙|提出|要領|募集について|チラシ", f["name"]):
                continue
            seen.add(f["url"])
            files.append(f)
        files.sort(key=lambda f: 0 if re.search(r"概要|ポイント|骨子", f["name"]) else 1)   # 概要を先に
        for f in files[:4 if DEEP else 2]:
            show(f["name"], f["url"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 2 and sys.argv[1] == "missing":
        missing()
    elif len(sys.argv) >= 4 and sys.argv[1] == "read" and sys.argv[2] in LEVELS:
        for pid in sys.argv[3:]:   # 案件番号はいくつでも並べられる
            print(f"\n########## {pid} ##########")
            read(sys.argv[2], pid)
    else:
        print(__doc__)

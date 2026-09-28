"""e-Gov パブリックコメントから「募集中」の案件を集めて data.json に保存する。

使い方:  python fetch.py
"""
import html
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
DATA_FILE = HERE / "data.json"
KEYWORDS_FILE = HERE / "keywords.json"

JST = timezone(timedelta(hours=9))
BASE = "https://public-comment.e-gov.go.jp"
LIST_START = BASE + "/servlet/Public?CLASSNAME=PCMMSTLIST&Mode=0"
LIST_POST = BASE + "/pcm/list"
RSS_URL = BASE + "/rss/pcm_list.xml"
DETAIL_URL = BASE + "/servlet/Public?CLASSNAME=PCMMSTDETAIL&id={id}&Mode=0"
PER_PAGE = 100
MAX_PAGES = 6
UA = "Mozilla/5.0 (pubcome-board; +https://github.com/)"


def now_jst():
    return datetime.now(JST)


def parse_jp_datetime(text):
    """'2026年10月26日17時0分' や '2026/10/26 17:00' を ISO 形式の文字列にする。"""
    text = (text or "").strip()
    m = re.search(r"(\d{4})[年/](\d{1,2})[月/](\d{1,2})日?(?:\s*(\d{1,2})[時:](\d{1,2})分?)?", text)
    if not m:
        return None
    y, mo, d, h, mi = m.groups()
    dt = datetime(int(y), int(mo), int(d), int(h or 23), int(mi or 59), tzinfo=JST)
    return dt.isoformat()


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


# ---------- 一覧ページから取得（メイン） ----------

def fetch_list_pages():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA)]
    opener.open(LIST_START, timeout=60).read()  # 最初に一度開いて通行証（Cookie）をもらう

    items = []
    now = now_jst().isoformat()
    for page in range(1, MAX_PAGES + 1):
        # 「次へ」ボタンは Page の次のページを表示するので、1ページ目は「最初へ」で取る
        form = {
            "CLASSNAME": "PCMMSTLIST", "LastPage": "1", "Mode": "0", "Type": "0",
            "Bunya": "", "Husho": "", "bMode": "0", "sortItem": "0", "sortButton": "1",
            "dspcnt": str(PER_PAGE), "keywordOr": "0",
            "Page": "1" if page == 1 else str(page - 1),
            "button": "first" if page == 1 else "next",
        }
        body = urllib.parse.urlencode(form).encode()
        page_html = opener.open(LIST_POST, data=body, timeout=60).read().decode("utf-8", "replace")
        page_items = parse_list_html(page_html)
        if not page_items:
            break
        items.extend(page_items)
        # このページに募集中（締切前）の案件が1件もなければ、それ以降は古いので終了
        if not any(it["deadline"] and it["deadline"] >= now for it in page_items):
            break
    return items


def parse_list_html(page_html):
    items = []
    for block in page_html.split('<li class="egovui-flex-column">')[1:]:
        m = re.search(r"PCMMSTDETAIL&amp;id=(\d+)", block)
        if not m:
            continue
        pid = m.group(1)

        def field(label):
            mm = re.search(r"<span>" + label + r"</span>(?:<span>)?([^<]*)", block)
            return clean(mm.group(1)) if mm else ""

        title = re.search(r'<a href="javascript:void\(0\)" class="egovui-link">(.*?)</a>', block, re.S)
        cat = re.search(r'<span class="egovui-badge egovui-large[^>]*>([^<]*)</span>', block)
        items.append({
            "id": pid,
            "title": clean(title.group(1)) if title else "",
            "category": clean(cat.group(1)) if cat else "",
            "ministry": field("所管省庁"),
            "published": parse_jp_datetime(field("案の公示日")),
            "deadline": parse_jp_datetime(field("受付締切日時")),
            "url": DETAIL_URL.format(id=pid),
        })
    return items


# ---------- RSS から取得（予備） ----------

def fetch_rss():
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": UA})
    xml = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    items = []
    for block in re.findall(r"<item [^>]*>(.*?)</item>", xml, re.S):
        link = html.unescape(re.search(r"<link>(.*?)</link>", block).group(1))
        pid = re.search(r"id=(\d+)", link).group(1)
        desc = html.unescape(re.search(r"<description>(.*?)</description>", block, re.S).group(1))

        def field(label):
            mm = re.search(label + r"：([^<]*)", desc)
            return mm.group(1).strip() if mm else ""

        ministry = field(r"問合せ先（所管省庁・部局名等）")
        mm = re.match(r"(.*?(?:委員会|省|庁|府))", ministry)
        ministry = mm.group(1) if mm else ministry
        items.append({
            "id": pid,
            "title": clean(re.search(r"<title>(.*?)</title>", block, re.S).group(1)),
            "category": field("カテゴリー"),
            "ministry": ministry,
            "published": parse_jp_datetime(field("案の公示日")),
            "deadline": parse_jp_datetime(field("受付締切日時")),
            "url": DETAIL_URL.format(id=pid),
        })
    return items


# ---------- 案件ごとの詳しい情報（資料・問合せ先など） ----------

def fetch_detail(pid):
    req = urllib.request.Request(DETAIL_URL.format(id=pid), headers={"User-Agent": UA})
    page_html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    return parse_detail_html(page_html)


def parse_detail_html(page_html):
    rows = {}
    for th, td in re.findall(r"<th>(.*?)</th>\s*<td>(.*?)</td>", page_html, re.S):
        rows[clean(th).replace(" ", "")] = td

    def text(label):
        td = rows.get(label, "")
        lines = [clean(x) for x in re.split(r"<br\s*/?>", td)]
        return "\n".join(x for x in lines if x and x != "-")

    def files(label):
        return [{"name": clean(name), "url": urllib.parse.urljoin(BASE, html.unescape(href))}
                for href, name in re.findall(r'<a class="file" href="([^"]+)"[^>]*>(.*?)</a>', rows.get(label, ""), re.S)]

    return {
        "rule_name": text("定めようとする命令などの題名"),
        "law": text("根拠法令条項"),
        "guide_files": files("意見募集要領（提出先を含む）"),
        "draft_files": files("命令などの案"),
        "other_files": files("関連資料、その他"),
        "note": text("備考"),
        "contact": text("問合せ先（所管省庁・部局名等）"),
    }


# ---------- タグ付け・保存 ----------

def tag_item(item, tag_defs):
    text = " ".join([item.get("title", ""), item.get("category", ""), item.get("ministry", "")])
    return [t["name"] for t in tag_defs if any(k in text for k in t["keywords"])]


def main():
    tag_defs = json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))["tags"]
    old = {}
    if DATA_FILE.exists():
        old = {it["id"]: it for it in json.loads(DATA_FILE.read_text(encoding="utf-8"))["items"]}

    try:
        fetched = fetch_list_pages()
        source = "list"
    except Exception as e:  # 一覧ページが取れないときは RSS で補う
        print(f"一覧ページの取得に失敗しました（{e}）。RSSで代わりに取得します。", file=sys.stderr)
        fetched = fetch_rss()
        source = "rss"
    if not fetched:
        print("案件を1件も取得できませんでした。前回のデータをそのまま使います。", file=sys.stderr)
        return 1

    today = now_jst().date().isoformat()
    merged = dict(old)
    new_count = 0
    for it in fetched:
        prev = old.get(it["id"])
        it["first_seen"] = prev["first_seen"] if prev else today
        if not prev:
            new_count += 1
        merged[it["id"]] = it
    for it in merged.values():
        it["tags"] = tag_item(it, tag_defs)

    # 募集中の案件のうち、まだ詳しい情報を取っていないものだけ取りに行く
    now = now_jst().isoformat()
    need = [it for it in merged.values()
            if it["deadline"] and it["deadline"] >= now and "detail" not in (old.get(it["id"]) or {})]
    for it in merged.values():
        if "detail" in (old.get(it["id"]) or {}) and "detail" not in it:
            it["detail"] = old[it["id"]]["detail"]
    for n, it in enumerate(need, 1):
        try:
            it["detail"] = fetch_detail(it["id"])
        except Exception as e:
            print(f"  詳細の取得に失敗: {it['id']}（{e}）", file=sys.stderr)
        time.sleep(1)  # e-Gov に負担をかけないよう1秒ずつ間をあける
    if need:
        print(f"詳しい情報を {len(need)} 件取得しました")

    # 締切から90日以上たった古い案件は捨てる（ファイルが大きくなりすぎないように）
    cutoff = (now_jst() - timedelta(days=90)).isoformat()
    items = [it for it in merged.values() if not it["deadline"] or it["deadline"] >= cutoff]
    items.sort(key=lambda it: it["deadline"] or "9999")

    DATA_FILE.write_text(json.dumps({
        "updated": now_jst().isoformat(timespec="minutes"),
        "source": source,
        "items": items,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    open_items = [it for it in items if it["deadline"] and it["deadline"] >= now]
    print(f"取得 {len(fetched)} 件（新しく見つけた案件 {new_count} 件）／ 募集中 {len(open_items)} 件")
    for t in tag_defs:
        n = sum(1 for it in open_items if t["name"] in it["tags"])
        print(f"  {t['name']}: {n} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())

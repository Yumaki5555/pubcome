"""47都道府県のホームページから「意見募集中」のパブリックコメントを集めて data.json に保存する。

県ごとにページの作りがバラバラなので、次のやり方で共通に読み取る:
  1. prefectures.json に書いた「パブコメ一覧ページ」を開く
  2. 「令和8年度」「募集中」などの一覧ページへのリンクがあれば、1〜2段奥まで開く
  3. 案件らしいリンクを開き、本文の「募集期間」「締切」などから締切日を読み取る
  4. 締切がまだ来ていないものだけを「募集中」として一覧にする

一度開いた案件ページは data.json に覚えておき、毎日すべてを開き直さないようにする。

使い方:  python fetch.py            （47都道府県すべて）
         python fetch.py 東京都 大阪府   （一部の県だけ試す）
"""
import hashlib
import html
import json
import os
import re
import ssl
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).parent
DATA_FILE = HERE / "data.json"
PREF_FILE = HERE / "prefectures.json"
KEYWORDS_FILE = HERE.parent / "keywords.json"   # 注目テーマは国版と共通の表を使う

JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "ja,en;q=0.8"}

MAX_DEPTH = 2        # 一覧ページから何段奥まで「一覧の一覧」をたどるか
MAX_HUBS = 8         # 1つの県でたどる一覧ページの数の上限
MAX_CASES = 80       # 1つの県で新しく開く案件ページの数の上限
WAIT = 0.5           # 同じ県のサイトに続けてアクセスするときの間隔（秒）
RECHECK_DAYS = 3     # 締切が読み取れなかったページを何日ごとに見直すか
KEEP_DAYS = 90       # 締切から何日たった記録を捨てるか
DEBUG = os.environ.get("DEBUG")   # DEBUG=1 で、どのページを見て何と判断したかを表示する


def now_jst():
    return datetime.now(JST)


# ---------- ページの取得 ----------

_insecure = ssl.create_default_context()
_insecure.check_hostname = False
_insecure.verify_mode = ssl.CERT_NONE


def fetch(url):
    """ページを開いて (最終的なURL, 文字列) を返す。証明書の設定が古い県のサイトにも対応する。"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        res = urllib.request.urlopen(req, timeout=40)
    except urllib.error.URLError as e:
        if "CERTIFICATE" not in str(e):
            raise
        res = urllib.request.urlopen(req, timeout=40, context=_insecure)
    body = res.read()
    ctype = res.headers.get("Content-Type", "")
    if "html" not in ctype and ctype:
        return res.geturl(), ""
    m = re.search(r"charset=([\w-]+)", ctype) or re.search(rb'charset=["\']?([\w-]+)', body[:4000])
    enc = m.group(1) if m else "utf-8"
    enc = enc.decode() if isinstance(enc, bytes) else enc
    if enc.lower() in ("shift_jis", "sjis", "x-sjis", "shift-jis"):
        enc = "cp932"
    try:
        return res.geturl(), body.decode(enc)
    except (UnicodeDecodeError, LookupError):
        return res.geturl(), body.decode("utf-8", "replace")


# ---------- ページの読み取り（メニューや足元の部分は読み飛ばす） ----------

SKIP_TAGS = {"script", "style", "header", "footer", "nav", "aside", "noscript", "select"}
SKIP_CLASS = re.compile(r"^(g?nav(i|igation)?|header|footer|sidebar|side_?(menu|nav|column|area|box|contents?)|l?menu"
                        r"|breadcrumbs?|pankuzu|topic_?path|banner|sns|share|skip)([-_].*)?$", re.I)
NEVER_SKIP = {"html", "body", "main", "article"}
BLOCK_TAGS = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "td", "th", "table", "section", "article"}
VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "area", "base", "col", "embed", "source", "wbr"}


class PageReader(HTMLParser):
    def __init__(self, lenient=False):
        super().__init__(convert_charrefs=True)
        self.lenient = lenient  # True なら script/style だけ読み飛ばす
        self.in_main = 0        # <main> や <article> の中にいるか
        self.skip = []          # 読み飛ばし中のタグ [タグ名, 入れ子の深さ]
        self.text = []
        self.links = []         # (href, 文字)
        self.rows = []          # 表の各行 {"cells": [...], "links": [(href, 文字)]}
        self.row = None
        self.cell = None
        self.cur_link = None
        self.title = ""
        self.h1 = ""
        self._in = None

    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:
            if tag == "br" and not self.skip:
                self.text.append("\n")
            return
        if self.skip:
            if tag == self.skip[0][0]:
                self.skip[0][1] += 1
            return
        a = dict(attrs)
        tokens = (a.get("class") or "").split() + [a.get("id") or ""]
        if tag in ("main", "article"):
            self.in_main += 1
        if self.lenient:
            skip = tag in ("script", "style", "noscript", "select")
        elif tag in ("header", "footer"):
            skip = not self.in_main
        else:
            skip = tag in SKIP_TAGS or (tag not in NEVER_SKIP and any(t and SKIP_CLASS.match(t) for t in tokens))
        if skip:
            self.skip = [[tag, 1]]
            return
        if tag in BLOCK_TAGS:
            self.text.append("\n")
        if tag == "a" and a.get("href"):
            self.cur_link = [a["href"], ""]
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        if tag in ("td", "th") and self.row is not None:
            self.cell = ""
        if tag in ("title", "h1"):
            self._in = tag

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[0][0]:
                self.skip[0][1] -= 1
                if self.skip[0][1] == 0:
                    self.skip = []
            return
        if tag in ("main", "article") and self.in_main:
            self.in_main -= 1
        if tag == "a" and self.cur_link:
            self.links.append((self.cur_link[0], squash(self.cur_link[1])))
            if self.row is not None:
                self.row["links"].append(self.links[-1])
            self.cur_link = None
        if tag in ("td", "th") and self.row is not None and self.cell is not None:
            self.row["cells"].append(squash(self.cell))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag in BLOCK_TAGS:
            self.text.append("\n")
        if tag == self._in:
            self._in = None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        if self.skip:
            return
        if self._in == "h1":
            self.h1 += data
        self.text.append(data)
        if self.cell is not None:
            self.cell += data
        if self.cur_link is not None:
            self.cur_link[1] += data


def squash(s):
    return re.sub(r"\s+", " ", s or "").strip()


def read_page(page_html, lenient=False):
    r = PageReader(lenient)
    try:
        r.feed(page_html)
    except Exception:
        pass
    if not lenient and len(squash("".join(r.text))) < 300:
        return read_page(page_html, lenient=True)   # 読み飛ばしすぎたときはやり直す
    text = unicodedata.normalize("NFKC", "".join(r.text))
    text = re.sub(r"[ \t　]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    rows = [{"cells": [unicodedata.normalize("NFKC", c) for c in row["cells"]], "links": row["links"]}
            for row in r.rows]
    return {"title": squash(r.title), "h1": squash(r.h1), "text": text, "links": r.links, "rows": rows}


# ---------- 日付の読み取り ----------

ERA = {"令和": 2018, "R": 2018, "平成": 1988, "H": 1988}
D_ERA = re.compile(r"(令和|平成|R|H)\s*(\d{1,2}|元)\s*[年.．/]\s*(\d{1,2})\s*[月.．/]\s*(\d{1,2})\s*日?")
D_WEST = re.compile(r"(20\d\d)\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})\s*日?")
D_MD = re.compile(r"(?<![\d年/.])(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def find_dates(text, today):
    """文中の日付を (位置, 終わりの位置, date) の並びで返す。年がない日付は前後から年を補う。"""
    found = []
    for m in D_ERA.finditer(text):
        n = 1 if m.group(2) == "元" else int(m.group(2))
        found.append((m.start(), m.end(), ERA[m.group(1)] + n, int(m.group(3)), int(m.group(4))))
    for m in D_WEST.finditer(text):
        found.append((m.start(), m.end(), int(m.group(1)), int(m.group(2)), int(m.group(3))))
    taken = [(s, e) for s, e, *_ in found]
    for m in D_MD.finditer(text):
        if any(s <= m.start() < e for s, e in taken):
            continue
        found.append((m.start(), m.end(), None, int(m.group(1)), int(m.group(2))))
    found.sort()
    years = [(s, y) for s, e, y, mo, d in found if y]
    # ページのどこにも年が書かれておらず、今年の年も出てこないなら、年のない日付は信用しない
    this_year = str(today.year) in text or f"令和{today.year - 2018}" in text
    out, last_year = [], None
    for s, e, y, mo, d in found:
        if y is None and not years and not this_year:
            continue
        if y is None:
            # 年が書かれていない日付は、前（なければ後ろ）に書かれた年を使う
            after = next((yy for ss, yy in years if ss > s), None)
            y = last_year or after or today.year
            if not (last_year or after) and (datetime(y, mo, 1).date() - today).days < -180:
                y += 1
        try:
            dt = datetime(y, mo, d).date()
        except ValueError:
            continue
        last_year = y
        out.append((s, e, dt))
    return out


PERIOD_WORDS = re.compile(
    r"(意見(の)?(募集|提出|受付|公募)期間|募集期間|提出期間|受付期間|公募期間|実施期間|応募期間|意見募集期限"
    r"|提出期限|募集期限|受付期限|提出締切|締切日?|締め切り|〆切)")
RANGE_SEP = re.compile(r"^[\s()（）月火水木金土日曜祝・\d:時分]*(から|~|〜|～|－|-|―|ー|–|—)")
MAX_SPAN = 120   # 募集期間がこれより長いものは、パブコメではない（計画期間など）とみなす


def find_period(text, today):
    """本文から (募集開始日, 締切日, 見つけた位置) を読み取る。読み取れなければ (None, None, None)。"""
    ds = find_dates(text, today)

    def ok(start, end):
        return not start or 0 <= (end - start).days <= MAX_SPAN

    for m in PERIOD_WORDS.finditer(text):
        near = [d for s, _, d in ds if m.end() <= s < m.end() + 160]
        if not near:
            continue
        if len(near) >= 2:
            start, end = min(near[:2]), max(near[:2])
        else:
            start, end = None, near[0]
        if ok(start, end):
            return (start, end, m.start())
    # 「○月○日～○月○日」の形がどこかにあればそれを使う
    for (s1, e1, d1), (s2, e2, d2) in zip(ds, ds[1:]):
        if RANGE_SEP.match(text[e1:s2]) and s2 - e1 < 20 and d1 <= d2 and ok(d1, d2):
            return (d1, d2, s1)
    return (None, None, None)


PUBCOME = re.compile(r"パブリック・?コメント|パブコメ|意見(の)?(募集|公募|提出|を募集)|ご?御?意見を(募集|お寄せ|伺)"
                     r"|(県|道|都|府)民(の|から)?(御|ご)?意見|意見提出手続|意見公募|いけん")
NOT_PUBCOME = re.compile(r"終了|修了|締め切りました|結果|補助金|助成金|プロポーザル|募金|セミナー|奨学生|入寮|研修|広告"
                         r"|ネーミングライツ|公聴会|職員|講座|教室|参加者|出店|協力店|受講|説明会|支援事業")


def looks_like_pubcome(link_text, page, pos):
    """意見募集（パブコメ）のページらしいかどうか。"""
    head = " ".join([link_text, page.get("h1", ""), page.get("title", "")])
    if NOT_PUBCOME.search(link_text) or NOT_PUBCOME.search(page.get("h1", "")):
        return False
    around = page["text"][max(0, pos - 400): pos + 400] if pos is not None else ""
    return bool(PUBCOME.search(head) or PUBCOME.search(around))


# ---------- リンクの見分け方 ----------

NG_LINK = re.compile(
    r"結果|要綱|要領|制度の概要|流れ|Q\s*&\s*A|とは|問い?合わ?せ|サイトマップ|ホーム|トップページ|アクセシビリティ|プライバシー"
    r"|指定管理|事業者(の)?募集|委員(の)?募集|職員(の)?(採用|募集)|採用試験|入札|アンケート|イベント|前へ|次へ|戻る|PDF|キロバイト|KB\)|過去"
    r"|平成|終了|済|ご意見・|ご意見箱|提言|県政ポスト|予告|予定|実施しなかった|閲覧場所|実施せず|反映状況|提出状況|考え方")
HUB_LINK = re.compile(r"募集中|実施中|現在|今年度|実施状況|実施案件|案件一覧|(意見|コメント|募集|案件).*一覧|一覧.*(意見|コメント)")
YEAR_LINK = re.compile(r"(令和\s*(\d+|元)|20\d\d)\s*年度")
CASE_LINK = re.compile(r"案|計画|条例|規則|方針|ビジョン|プラン|戦略|指針|構想|評価書|基準|意見|募集|改正|改定|見直し|について|コメント")
FILE_EXT = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|csv|jpg|png)(\?|#|$)", re.I)


def base_domain(host):
    parts = host.split(".")
    return ".".join(parts[-4:] if host.endswith(".lg.jp") else parts[-3:])


def current_years(today):
    """いまの年度（4月始まり）を「令和◯年度」と西暦で。4〜5月は前の年度も含める。"""
    fy = today.year if today.month >= 4 else today.year - 1
    fys = [fy, fy - 1] if today.month in (4, 5) else [fy]
    return fys


def is_current_year_link(text, today):
    fys = current_years(today)
    m = re.search(r"令和\s*(\d+|元)\s*年度", text)
    if m and 2018 + (1 if m.group(1) == "元" else int(m.group(1))) not in fys:
        return False
    m = re.search(r"(20\d\d)\s*年度", text)
    if m and int(m.group(1)) not in fys:
        return False
    return True


def classify_links(page, page_url, today):
    """ページのリンクを「一覧ページ」と「案件ページ」に分ける。"""
    host = base_domain(urllib.parse.urlparse(page_url).hostname or "")
    hubs, cases, seen = [], [], set()
    for href, text in page["links"]:
        text = unicodedata.normalize("NFKC", text)
        if href.startswith(("mailto:", "tel:", "javascript:", "#")) or len(text) < 5:
            continue
        url = urllib.parse.urljoin(page_url, html.unescape(href)).split("#")[0]
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https") or base_domain(u.hostname or "") != host:
            continue
        if FILE_EXT.search(u.path) or url in seen or url.rstrip("/") == page_url.rstrip("/"):
            continue
        if NG_LINK.search(text) or not is_current_year_link(text, today):
            continue
        seen.add(url)
        if HUB_LINK.search(text) or (YEAR_LINK.search(text) and not re.search(r"案|について", text)):
            hubs.append((url, text))
        elif CASE_LINK.search(text):
            cases.append((url, text))
    return hubs, cases


def row_items(page, page_url, today):
    """一覧表の各行に募集期間が書いてあれば、案件ページを開かずにそのまま読み取る。
    戻り値: [(住所, 題名, 開始日, 締切日)]"""
    out = []
    for row in page.get("rows", []):
        cells = [c for c in row["cells"] if c]
        if len(cells) < 2:
            continue
        start, end, _ = find_period(" ".join(cells), today)
        if not end:
            # 「公表日」「提出期限」のように別々のマスに書かれている表（京都府など）
            ds = sorted(d for c in cells for _, _, d in find_dates(c, today))
            if len(ds) >= 2 and (ds[-1] - ds[0]).days <= MAX_SPAN:
                start, end = ds[0], ds[-1]
        if not end:
            continue
        # 日付を含まない一番長いマスを題名とみなす
        names = [c for c in cells if not find_dates(c, today) and len(c) >= 8
                 and not re.search(r"TEL|電話|〒|@|FAX|ファクス|課|室|係|担当", c[-20:] + c[:12])]
        if not names:
            continue
        title = max(names, key=len)[:150]
        if not CASE_LINK.search(title) or NG_ROW.search(title) or NOT_PUBCOME.search(title):
            continue
        link = page_url
        for href, text in row["links"]:
            if not href.startswith(("mailto:", "javascript:", "#")):
                link = urllib.parse.urljoin(page_url, html.unescape(href))
                break
        out.append((link, title, start, end))
    return out


NG_ROW = re.compile(r"実施しな|実施せず|予告|予定")


# ---------- スマホ用まとめに載せる情報（資料・出し方・問い合わせ先） ----------

HOWTO_HEAD = re.compile(r"^\s*[\d()（）①-⑩.、\s]*(意見の?)?(提出|応募|送付)(の)?(方法|先|手続)|^\s*[\d()（）①-⑩.、\s]*意見の?出し方")
CONTACT_HEAD = re.compile(r"^\s*[\d()（）①-⑩.、\s]*(お?問い?合わ?せ(先)?|担当(課|部署)?|このページに関するお問い合わせ)\s*[:：]?\s*$")
JUNK_LINE = re.compile(r"^送信$|役に立|見つけやす|ページの先頭|ページトップ|このページを印刷|^PDF|Adobe|Acrobat"
                       r"|より良いウェブサイト|おすすめコンテンツ|このページの作成所属|Copyright|個人情報について|^メールでのお問い合わせ")


def take_lines(lines, start, max_lines, max_chars):
    out, total = [], 0
    for line in lines[start: start + max_lines]:
        line = line.strip()
        if not line or JUNK_LINE.search(line):
            continue
        if re.match(r"^(関連情報|関連リンク|目的別|このページを見ている人|よくある質問|SNS|シェア|ツイート|アンケート)", line):
            break   # ページの飾り部分に来たら終わり
        if out and (HOWTO_HEAD.search(line) or CONTACT_HEAD.search(line) or re.match(r"^\d{1,2}[.．\s]", line)):
            break   # 次の見出しに来たら終わり
        out.append(line)
        total += len(line)
        if total >= max_chars:
            break
    return "\n".join(out)


def read_detail(page, page_url):
    """案件ページから、資料のリンク・意見の出し方・問い合わせ先を抜き出す。"""
    files, seen = [], set()
    for href, text in page["links"]:
        url = urllib.parse.urljoin(page_url, html.unescape(href))
        if FILE_EXT.search(urllib.parse.urlparse(url).path) and url not in seen:
            seen.add(url)
            files.append({"name": TITLE_TAIL.sub("", text).strip() or "資料", "url": url})
    lines = page["text"].split("\n")
    howto = contact = ""
    for n, line in enumerate(lines):
        if not howto and HOWTO_HEAD.search(line):
            rest = HOWTO_HEAD.sub("", line).strip(" :：")
            rest = re.sub(r"^[、,・\s]*(及び|は、|、)?[、,・\s]*((提出|応募)?(先|方法|様式)[、,及びび\s]*)*[:：、,\s]*", "", rest)
            howto = ((rest + "\n") if len(rest) > 3 else "") + take_lines(lines, n + 1, 12, 400)
        if CONTACT_HEAD.search(line):
            contact = take_lines(lines, n + 1, 8, 250)   # 最後に出てくる問い合わせ先を使う
    return {"files": files[:20], "howto": howto.strip(), "contact": contact.strip()}


# ---------- 1つの県を調べる ----------

TITLE_TAIL = re.compile(r"\s*[(（](PDF|pdf|Word|Excel)[^)）]*[)）]\s*$")


def clean_title(link_text, page):
    t = TITLE_TAIL.sub("", link_text).strip()
    h1 = TITLE_TAIL.sub("", page.get("h1", "")).strip()
    if len(t) < 8 and len(h1) >= len(t):
        t = h1
    t = re.sub(r"\s*[\[［(（]\s*20\d\d年.*?[\]］)）]\s*", "", t)   # 新潟県のように題名に期間が付いていれば外す
    t = re.sub(r"\s*[(（]\s*\d{1,2}月\d{1,2}日.*?まで\s*[)）]\s*$", "", t)
    t = re.sub(r"\s*[<＜][^>＞]*[>＞]\s*$", "", t).strip() or h1 or link_text
    # かぎかっこの開き・閉じの数をそろえる
    if t.count("「") < t.count("」"):
        t = "「" + t
    elif t.count("「") > t.count("」"):
        t += "」"
    return t


def item_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:10]


def crawl_prefecture(pref, cache, today, log):
    name, start_url = pref["name"], pref["url"]
    results = {}          # url → 記録
    stats = {"hubs": 0, "new_cases": 0, "error": None}

    def get(url):
        time.sleep(WAIT)
        return fetch(url)

    def visit_case(url, link_text, depth, queue):
        prev = cache.get(url)
        today_s = today.isoformat()
        if prev:
            # 締切が過ぎたもの・最近見たものは開き直さない
            if prev.get("deadline") and prev["deadline"] < today_s:
                results[url] = prev
                return
            if (prev.get("deadline") and "detail" in prev) or (not prev.get("deadline") and prev.get("checked", "") > (today - timedelta(days=RECHECK_DAYS)).isoformat()):
                results[url] = prev
                return
        if stats["new_cases"] >= MAX_CASES:
            return
        stats["new_cases"] += 1
        try:
            final, page_html = get(url)
        except Exception as e:
            log(f"    開けませんでした: {url}（{e}）")
            return
        page = read_page(page_html)
        body = page["text"]
        start, end, pos = find_period(body, today)
        # 募集期間が2つ以上書かれているページは、個別の案件ではなく一覧ページとみなして奥へ進む
        period_hits = sum(1 for m in PERIOD_WORDS.finditer(body)
                          if find_dates(body[m.end(): m.end() + 160], today))
        if (period_hits >= 3 or not end) and depth < MAX_DEPTH:
            hubs, cases = classify_links(page, final, today)
            hub_like = PUBCOME.search(link_text + page.get("h1", "")) and HUB_LINK.search(link_text + page.get("h1", ""))
            if cases and (period_hits >= 3 or (len(cases) >= 3 and hub_like)):
                queue.append((final, depth + 1, page))
        if period_hits >= 3 or (end and not looks_like_pubcome(link_text, page, pos)):
            start = end = None      # 一覧ページや、意見募集ではないページ（職員募集など）は案件として数えない
        if DEBUG:
            log(f"    案件? {end} {'' if end else '×'} {link_text[:50]} ({period_hits}) {url}")
        results[url] = {
            "id": item_id(url),
            "pref": name,
            "title": clean_title(link_text, page),
            "url": url,
            "start": start.isoformat() if start else None,
            "deadline": end.isoformat() if end else None,
            "checked": today_s,
            "first_seen": (prev or {}).get("first_seen", today_s),
        }
        if end:
            results[url]["detail"] = read_detail(page, final)

    try:
        final, page_html = get(start_url)
    except Exception as e:
        stats["error"] = str(e)[:120]
        log(f"  {name}: 一覧ページが開けませんでした（{e}）")
        return results, stats

    def add_rows(page, url):
        for link, title, start, end in row_items(page, url, today):
            key = link + "#" + item_id(title)
            prev = cache.get(key) or {}
            results[key] = {
                "id": item_id(key), "pref": name, "title": title, "url": link,
                "start": start.isoformat() if start else None, "deadline": end.isoformat(),
                "checked": today.isoformat(), "first_seen": prev.get("first_seen", today.isoformat()),
            }

    queue = [(final, 0, read_page(page_html))]
    visited = {final}
    while queue:
        url, depth, page = queue.pop(0)
        add_rows(page, url)
        hubs, cases = classify_links(page, url, today)
        for c_url, c_text in cases:
            if c_url not in visited:
                visited.add(c_url)
                visit_case(c_url, c_text, depth, queue)
        if depth >= MAX_DEPTH:
            continue
        for h_url, h_text in hubs:
            if h_url in visited or stats["hubs"] >= MAX_HUBS:
                continue
            visited.add(h_url)
            stats["hubs"] += 1
            try:
                h_final, h_html = get(h_url)
            except Exception as e:
                log(f"    開けませんでした: {h_url}（{e}）")
                continue
            h_page = read_page(h_html)
            if DEBUG:
                log(f"  一覧 {h_text[:50]} {h_url}")
            # 一覧ページのように見えて実は1件の案件ページだった、という場合にも対応する
            start, end, _ = find_period(h_page["text"], today)
            h_hubs, h_cases = classify_links(h_page, h_final, today)
            if end and len(h_cases) < 3:
                visit_case(h_url, h_text, MAX_DEPTH, queue)
            else:
                queue.append((h_final, depth + 1, h_page))
    return results, stats


# ---------- タグ付け・保存 ----------

def tag_item(item, tag_defs):
    return [t["name"] for t in tag_defs if any(k in item["title"] for k in t["keywords"])]


def main():
    only = set(sys.argv[1:])
    prefs = [p for p in json.loads(PREF_FILE.read_text(encoding="utf-8"))["prefectures"]
             if not only or p["name"] in only]
    tag_defs = json.loads(KEYWORDS_FILE.read_text(encoding="utf-8"))["tags"]
    old = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}
    cache = old.get("pages", {})
    today = now_jst().date()
    logs = []

    def run(pref):
        lines = []
        res, stats = crawl_prefecture(pref, cache, today, lines.append)
        return pref, res, stats, lines

    pages = {u: r for u, r in cache.items() if r["pref"] not in {p["name"] for p in prefs}}
    status = old.get("status", {})
    with ThreadPoolExecutor(max_workers=10) as ex:
        for pref, res, stats, lines in ex.map(run, prefs):
            pages.update(res)
            n_open = sum(1 for r in res.values() if r.get("deadline") and r["deadline"] >= today.isoformat())
            status[pref["name"]] = {"url": pref["url"], "error": stats["error"], "open": n_open,
                                    "checked": today.isoformat()}
            print(f"{pref['name']}: 募集中 {n_open} 件（新しく開いたページ {stats['new_cases']}、一覧 {stats['hubs']}）"
                  + (f" ※{stats['error']}" if stats["error"] else ""))
            for line in lines:
                print(line, file=sys.stderr)

    # 締切から時間がたった記録と、締切が読み取れないまま古くなった記録は捨てる
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    pages = {u: r for u, r in pages.items()
             if (r.get("deadline") or r.get("checked", "")) >= cutoff}

    items = []
    for r in pages.values():
        if r.get("deadline") and r["deadline"] >= today.isoformat():
            it = dict(r)
            it["tags"] = tag_item(it, tag_defs)
            if it.get("start") and it["start"] > today.isoformat():
                continue    # まだ募集が始まっていないもの（読み間違いも多いので載せない）
            items.append(it)
    # 同じ案件が別の住所で2回見つかったときは1つにまとめる
    def same_key(it):
        t = re.sub(r"[「」『』()（）\s]|案|素案|について.*$|への.*$|に(対|関)する.*$", "", it["title"])
        return (it["pref"], it["deadline"], t[:12])
    uniq = {}
    for it in sorted(items, key=lambda it: len(it["url"])):
        uniq.setdefault(same_key(it), it)
    items = sorted(uniq.values(), key=lambda it: (it["deadline"], it["pref"]))

    DATA_FILE.write_text(json.dumps({
        "updated": now_jst().isoformat(timespec="minutes"),
        "status": status,
        "items": items,
        "pages": pages,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n合計 募集中 {len(items)} 件（{len({it['pref'] for it in items})} 都道府県）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

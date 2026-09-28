"""data.json から都道府県版の一覧ページ（../docs/pref/index.html）とスマホ用まとめを作る。
市区町村版（../市区町村レベル/build.py）も、言葉と置き場所を config.json で差し替えてこの仕組みを使う。

使い方:  python build.py
"""
import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
BASE = HERE   # データや設定を読むフォルダ（市区町村版では 市区町村レベル/ になる）
sys.path.insert(0, str(HERE.parent))
from build import SHARE_JS, short_title  # 国版と共通の部品を使う


def load_plain_titles():
    """plain_titles.json（案件番号 → わかりやすい言い換え）を読む。"""
    path = BASE / "plain_titles.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def display_title(item):
    """わかりやすい言い換えがあればそれを、なければ正式名称を短くしたものを使う。"""
    return item.get("plain") or short_title(item["title"])

OUT_DIR = HERE.parent / "docs" / "pref"   # 国版と同じ公開フォルダの中の pref/ に置く（config の out_dir で変わる）
JST = timezone(timedelta(hours=9))

REGIONS = [
    ("北海道・東北", ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"]),
    ("関東", ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県"]),
    ("中部", ["新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県"]),
    ("近畿", ["三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"]),
    ("中国・四国", ["鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県"]),
    ("九州・沖縄", ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]),
]


def summary_path(item):
    """案件ごとのスマホ用まとめページの場所（サイト内の相対パス）。"""
    return f"p/{item['id']}.html"


def share_text(item, main_hashtag, hashtag_of, site_url):
    """1件ごとの投稿の定型文（国版と同じ形）。リンク（23字として数える）込みで140字以内にする。"""
    d = datetime.fromisoformat(item["deadline"])
    tags = " ".join([main_hashtag, "#" + item["pref"]] + [hashtag_of[t] for t in item["tags"]])
    make = lambda title: (f"📣【パブコメ募集】{d.month}/{d.day}まで\n\n"
                          f"「{title}」について、{item['pref']}が意見募集中です。\n\n"
                          f"ひとことからでも、誰でも送れます🙆\n{tags}\n\n")
    title = display_title(item)
    while len(make(title)) + 23 > 140 and len(title) > 8:
        title = title[:-2].rstrip("…") + "…"
    return make(title) + site_url + summary_path(item)


def main(base=HERE):
    global BASE, OUT_DIR
    BASE = base
    config = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    OUT_DIR = HERE.parent / "docs" / config.get("out_dir", "pref")
    tags = json.loads((HERE.parent / "keywords.json").read_text(encoding="utf-8"))["tags"]
    data = json.loads((BASE / "data.json").read_text(encoding="utf-8"))

    today = datetime.now(JST).date().isoformat()
    open_items = [it for it in data["items"] if it["deadline"] >= today]
    hashtag_of = {t["name"]: t["hashtag"] for t in tags}
    plain = load_plain_titles()
    items = []
    for it in open_items:
        if it["id"] in plain:
            it["plain"] = plain[it["id"]]
        it["share"] = share_text(it, config["main_hashtag"], hashtag_of, config["site_url"])
        items.append({
            "pref": it["pref"], "title": it["title"], "short": display_title(it),
            "url": it["url"], "deadline": it["deadline"], "tags": it["tags"],
            "share": it["share"], "page": summary_path(it),
        })
    build_summary_pages(open_items, tags, config)
    listed = json.loads((BASE / config.get("list_file", "prefectures.json")).read_text(encoding="utf-8"))
    prefs = listed.get("prefectures") or listed.get("areas")
    if "pref" in prefs[0]:
        # 市区町村版：都道府県ごとにまとめる（都道府県の並びは REGIONS の順）
        order = [n for _, names in REGIONS for n in names]
        groups = [(pn, [a["name"] for a in prefs if a["pref"] == pn]) for pn in order]
        groups = [g for g in groups if g[1]]
    else:
        groups = REGIONS
    status = data.get("status", {})
    payload = {
        "updated": data["updated"],
        "items": items,
        "tags": [{"name": t["name"], "color": t["color"]} for t in tags],
        "regions": groups,
        "prefs": [{"name": p["name"], "url": p["url"],
                   "error": bool((status.get(p["name"]) or {}).get("error"))} for p in prefs],
        "urgentDays": config["urgent_days"],
    }
    page = TEMPLATE
    for key, value in {
        "__SWITCH__": config.get("switch_html", ""),
        "__ABOUT__": config.get("about_html", ""),
        "__CAUTION__": config.get("caution_html", ""),
        "__SITE_NAME__": html.escape(config["site_name"]),
        "__SITE_DESC__": html.escape(config["site_description"]),
        "__SITE_URL__": html.escape(config["site_url"]),
        "__NATIONAL_URL__": html.escape(config["national_url"]),
        "__COUNT__": str(len(items)),
        "__SHARE_JS__": SHARE_JS,
        "__DATA__": json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(key, value)

    page = words(page, config)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    print(f"docs/{config.get('out_dir', 'pref')}/index.html を作りました"
          f"（募集中 {len(items)} 件、{len({i['pref'] for i in items})} {config.get('area_label', '都道府県')}）")


def words(page, config):
    """ひな形の「__UNIT__（県）」「__AREA__（都道府県）」を、都道府県版・市区町村版の言葉に置き換える。"""
    return page.replace("__UNIT__", config.get("unit", "県")).replace("__AREA__", config.get("area_label", "都道府県"))


def build_summary_pages(items, tag_defs, config):
    """案件ごとのスマホ用まとめページ（docs/p/番号.html）を作る。締切を過ぎたページは消す。"""
    out = OUT_DIR / "p"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.html"):
        old.unlink()
    color_of = {t["name"]: t["color"] for t in tag_defs}
    e = html.escape
    lines = lambda text: "<br>".join(e(x) for x in text.split("\n"))

    for it in items:
        d = datetime.fromisoformat(it["deadline"])
        det = it.get("detail") or {}
        files = "".join(f'<li><a href="{e(f["url"])}" target="_blank" rel="noopener">📄 {e(f["name"])}</a></li>'
                        for f in det.get("files", []))
        start = ""
        if it.get("start"):
            s0 = datetime.fromisoformat(it["start"])
            start = f"{s0.month}月{s0.day}日から"
        howto = (f'<p class="quote">{lines(det["howto"])}</p>'
                 f'<p class="sub">※__UNIT__のページから自動で抜き出した文です。くわしくは__UNIT__のページでご確認ください。</p>'
                 if det.get("howto") else
                 '<p class="sub">意見の出し方（メール・入力フォーム・郵送など）は、__UNIT__のページでご確認ください。</p>')
        replace = {
            "__TITLE__": e(display_title(it)),
            "__OFFICIAL__": e(it["title"]),
            "__TAGS__": "".join(f'<span class="tag" style="background:{color_of[t]}">{e(t)}</span>' for t in it["tags"]),
            "__PREF__": e(it["pref"]),
            "__DEADLINE__": f"{start}{d.year}年{d.month}月{d.day}日まで",
            "__DEADLINE_ISO__": e(it["deadline"]),
            "__OFFICIAL_URL__": e(it["url"]),
            "__HOWTO__": howto,
            "__FILES__": f'<ul class="files">{files}</ul>' if files else '<p class="sub">資料は__UNIT__のページでご確認ください。</p>',
            "__CONTACT__": lines(det["contact"]) if det.get("contact") else "__UNIT__のページでご確認ください。",
            "__SHARE__": json.dumps(it["share"], ensure_ascii=False).replace("</", "<\\/"),
            "__SHARE_JS__": SHARE_JS,
            "__SITE_NAME__": e(config["site_name"]),
            "__PAGE_URL__": e(config["site_url"] + summary_path(it)),
            "__DESC__": e(f"{d.month}/{d.day}まで意見募集中（{it['pref']}）。ひとことからでも、誰でも意見を送れます。"),
        }
        page = SUMMARY_TEMPLATE
        for k, v in replace.items():
            page = page.replace(k, v)
        (out / f"{it['id']}.html").write_text(words(page, config), encoding="utf-8")


SUMMARY_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__｜__SITE_NAME__</title>
<meta name="description" content="__DESC__">
<meta property="og:type" content="article">
<meta property="og:title" content="【パブコメ募集・__PREF__】__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__PAGE_URL__">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🗾</text></svg>">
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1c1b19;--sub:#5f5c56;--line:#e3e0d9;--accent:#1d4ed8;--urgent:#dc2626;--urgent-bg:#fef2f2;--chip:#efede8;--pref:#0f766e;--pref-bg:#e6f4f1}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#16161a;--card:#202026;--ink:#ecebe8;--sub:#a8a59f;--line:#34343c;--accent:#7aa2ff;--urgent:#f87171;--urgent-bg:#3a1e1e;--chip:#2c2c33;--pref:#5eead4;--pref-bg:#15302c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI","Meiryo",sans-serif;line-height:1.7}
a{color:var(--accent);overflow-wrap:anywhere}
.wrap{max-width:640px;margin:0 auto;padding:12px 16px 40px}
.back{font-size:.88rem;text-decoration:none}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 6px;font-size:.8rem}
.tag{color:#fff;padding:1px 8px;border-radius:6px;font-weight:600}
.pref{font-weight:700;padding:1px 8px;border-radius:6px;background:var(--pref-bg);color:var(--pref)}
h1{font-size:1.35rem;line-height:1.5;margin:4px 0 6px}
.official{font-size:.82rem;color:var(--sub);margin:0 0 14px}
.deadline{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.left{font-weight:800;font-size:1.1rem;padding:2px 10px;border-radius:8px;background:var(--chip)}
.left.urgent{background:var(--urgent-bg);color:var(--urgent)}
.deadline small{color:var(--sub);display:block;font-size:.78rem}
.btns{display:flex;flex-direction:column;gap:8px;margin:14px 0}
.btn{display:block;text-align:center;text-decoration:none;border-radius:12px;padding:14px;font-size:1.05rem;font-weight:700;border:0;font-family:inherit;cursor:pointer;width:100%}
.btn.go{background:var(--accent);color:#fff}
.btn.x{background:var(--ink);color:var(--bg)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:12px 0}
h2{font-size:1rem;margin:0 0 6px}
ol{padding-left:1.3em;margin:4px 0}
ol li{margin:4px 0}
ul.files{list-style:none;padding:0;margin:0}
ul.files li{margin:4px 0}
ul.files a{display:block;padding:8px 10px;border:1px solid var(--line);border-radius:8px;text-decoration:none}
.quote{border-left:3px solid var(--line);padding-left:10px;margin:6px 0;font-size:.92rem}
.sub{color:var(--sub);font-size:.85rem}
footer{font-size:.78rem;color:var(--sub);margin-top:20px}
</style>
</head>
<body>
<div class="wrap">
<a class="back" href="../">← 募集中のパブコメ一覧（__SITE_NAME__）</a>
<div class="meta"><span class="pref">__PREF__</span>__TAGS__</div>
<h1>__TITLE__</h1>
<p class="official">正式名：__OFFICIAL__</p>

<div class="deadline"><span class="left" id="left"></span><span><small>意見の募集期間</small>__DEADLINE__</span></div>

<div class="btns">
  <a class="btn go" href="__OFFICIAL_URL__" target="_blank" rel="noopener">__PREF__のページで意見を出す</a>
  <button type="button" class="btn x" id="share">𝕏でシェアして広める</button>
</div>

<section>
  <h2>✍️ 意見の出し方</h2>
  <ol>
    <li>下の「資料」を開いて、どんな案か読む（概要だけでもOK）</li>
    <li>下の「この案件の出し方」を確認する（メール・入力フォーム・郵送など、__UNIT__によって違います）</li>
    <li>意見を書いて送る（ひとことでも大丈夫）</li>
  </ol>
  <h2 style="margin-top:12px">📮 この案件の出し方</h2>
  __HOWTO__
</section>

<section>
  <h2>📚 資料</h2>
  __FILES__
</section>

<section>
  <h2>☎️ 問い合わせ先</h2>
  <p>__CONTACT__</p>
</section>

<footer>このページは <a href="__OFFICIAL_URL__" target="_blank" rel="noopener">__PREF__の公式ページ</a> の情報を自動で集め、スマホで読みやすくまとめたものです。読み取りの誤りがある場合があるので、正式な内容は必ず県の公式ページでご確認ください。</footer>
</div>
<script>
__SHARE_JS__
const ymd = d => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
const dl = Math.round((ymd(new Date('__DEADLINE_ISO__T00:00:00')) - ymd(new Date())) / 86400000);
const left = document.getElementById('left');
left.textContent = dl < 0 ? '募集終了' : dl === 0 ? '本日締切' : `あと${dl}日`;
if (dl <= 7) left.classList.add('urgent');
document.getElementById('share').onclick = () => shareX(__SHARE__);
</script>
</body>
</html>
"""


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__SITE_NAME__｜いま意見を出せる__AREA__の案件一覧</title>
<meta name="description" content="__SITE_DESC__">
<meta property="og:type" content="website">
<meta property="og:title" content="__SITE_NAME__｜募集中のパブコメ __COUNT__件">
<meta property="og:description" content="__SITE_DESC__">
<meta property="og:url" content="__SITE_URL__">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🗾</text></svg>">
<style>
:root{
  --bg:#f6f5f2;--card:#fff;--ink:#1c1b19;--sub:#5f5c56;--line:#e3e0d9;
  --accent:#1d4ed8;--urgent:#dc2626;--urgent-bg:#fef2f2;--chip:#efede8;--pref:#0f766e;--pref-bg:#e6f4f1;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#16161a;--card:#202026;--ink:#ecebe8;--sub:#a8a59f;--line:#34343c;
    --accent:#7aa2ff;--urgent:#f87171;--urgent-bg:#3a1e1e;--chip:#2c2c33;--pref:#5eead4;--pref-bg:#15302c;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI","Meiryo",sans-serif;line-height:1.6}
a{color:var(--accent)}
.wrap{max-width:860px;margin:0 auto;padding:0 16px}
header{padding:28px 0 12px}
.switch{font-size:.85rem;margin:0 0 10px}
h1{font-size:1.6rem;margin:0 0 4px;letter-spacing:.02em}
.lead{color:var(--sub);margin:0 0 12px;font-size:.95rem}
.stats{display:flex;gap:10px;flex-wrap:wrap;font-size:.85rem;color:var(--sub)}
.stats b{color:var(--ink);font-size:1.1rem}
details.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:12px 0;font-size:.92rem}
details.box summary{cursor:pointer;font-weight:600}
details.box ol{margin:8px 0 4px;padding-left:1.3em}
.filters{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line)}
.tagbar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.tagbtn{border:1.5px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;
  padding:5px 12px;font-size:.88rem;cursor:pointer;font-family:inherit}
.tagbtn .n{opacity:.7;margin-left:4px;font-size:.8em}
.tagbtn[aria-pressed="true"]{color:#fff;border-color:transparent}
.row{display:flex;gap:6px;flex-wrap:wrap}
.row input,.row select{flex:1 1 180px;min-width:0;padding:7px 10px;border:1px solid var(--line);border-radius:8px;
  background:var(--card);color:var(--ink);font-size:.92rem;font-family:inherit}
.count{font-size:.85rem;color:var(--sub);margin:10px 0 4px}
ul.list{list-style:none;padding:0;margin:0 0 30px}
.item{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0;
  border-left:5px solid var(--line)}
.item.focus{border-left-color:var(--tagc)}
.meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.8rem;color:var(--sub);margin-bottom:4px}
.left{font-weight:700;padding:1px 8px;border-radius:6px;background:var(--chip);color:var(--ink)}
.left.urgent{background:var(--urgent-bg);color:var(--urgent)}
.pref{font-weight:700;padding:1px 8px;border-radius:6px;background:var(--pref-bg);color:var(--pref)}
.tag{color:#fff;padding:1px 8px;border-radius:6px;font-weight:600}
.item h2{font-size:1rem;margin:4px 0 8px;font-weight:600;line-height:1.5}
.item h2 a{color:var(--ink);text-decoration:none}
.item h2 a:hover{text-decoration:underline}
.official{font-size:.8rem;color:var(--sub);margin:-4px 0 8px;line-height:1.5}
.foot{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;font-size:.82rem;color:var(--sub)}
.actions{display:flex;gap:6px;flex-wrap:wrap}
.btn{display:inline-block;border:0;cursor:pointer;font-family:inherit;text-decoration:none;border-radius:8px;padding:5px 12px;font-size:.82rem;font-weight:600}
.btn.go{background:var(--accent);color:#fff}
.btn.sum{background:var(--chip);color:var(--ink)}
.btn.x{background:var(--ink);color:var(--bg)}
.empty{text-align:center;color:var(--sub);padding:30px 0}
h3.sec{font-size:1.05rem;margin:10px 0 4px}
.region{margin:10px 0}
.region b{font-size:.85rem;color:var(--sub);display:block;margin-bottom:4px}
.prefgrid{display:flex;flex-wrap:wrap;gap:6px}
.pchip{display:inline-flex;gap:4px;align-items:center;border:1px solid var(--line);background:var(--card);border-radius:8px;
  padding:3px 9px;font-size:.85rem;text-decoration:none;color:var(--ink)}
.pchip .n{font-weight:700;color:var(--pref)}
.pchip.zero .n{color:var(--sub);font-weight:400}
.pchip.err{border-style:dashed}
footer{font-size:.8rem;color:var(--sub);padding:20px 0 40px;border-top:1px solid var(--line)}
</style>
</head>
<body>
<div class="wrap">
<header>
  <p class="switch">__SWITCH__</p>
  <h1>📣 __SITE_NAME__</h1>
  <p class="lead">__SITE_DESC__</p>
  <div class="stats"><span>募集中 <b id="total">__COUNT__</b> 件</span><span id="npref"></span><span id="soon"></span><span id="updated"></span></div>
  <details class="box">
    <summary>__AREA__のパブコメってなに？ 意見の出し方</summary>
    <p>__ABOUT__</p>
    <ol>
      <li>気になる案件の「スマホ用まとめ」で、中身と意見の出し方を確認する</li>
      <li>__UNIT__のページで、案の内容と「意見の出し方（メール・フォーム・郵送など）」を確認</li>
      <li>書かれている方法で意見を送る（ひとことでも大丈夫）</li>
    </ol>
  </details>
  <details class="box">
    <summary>⚠️ このページの注意（自動で集めています）</summary>
    <p>__CAUTION__</p>
  </details>
</header>

<div class="filters">
  <div class="tagbar" id="tagbar" role="group" aria-label="注目テーマで絞り込み"></div>
  <div class="row">
    <input id="q" type="search" placeholder="キーワードで探す（例：子ども、条例）">
    <select id="pref"><option value="">すべての__AREA__</option></select>
  </div>
</div>

<p class="count" id="count"></p>
<ul class="list" id="list"></ul>

<h3 class="sec">__AREA__ごとの公式ページ</h3>
<p class="official">数字は、このページで見つけた募集中の件数です。0件でも、__UNIT__のページに載っていることがあります。</p>
<div id="prefs"></div>

<footer>
  出典：各__AREA__の公式ホームページ（毎日自動で更新）。
  テーマ分けは案件名に含まれる言葉で自動判定しているため、漏れや誤りがある場合があります。必ず各__AREA__の公式ページで内容をご確認ください。
</footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
__SHARE_JS__
const D = JSON.parse(document.getElementById('data').textContent);
const tagColor = Object.fromEntries(D.tags.map(t => [t.name, t.color]));
const now = new Date();
const state = { tag: '', q: '', pref: '' };

function ymd(d){ return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()); }
function daysLeft(iso){ return Math.round((ymd(new Date(iso + 'T00:00:00')) - ymd(now)) / 86400000); }
function fmt(iso){ const d = new Date(iso + 'T00:00:00'); return `${d.getMonth()+1}/${d.getDate()}`; }
function esc(s){ return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

const countOf = {};
D.items.forEach(i => countOf[i.pref] = (countOf[i.pref] || 0) + 1);

// 都道府県の選択肢（地方ごと）
const sel = document.getElementById('pref');
D.regions.forEach(([region, names]) => {
  const g = document.createElement('optgroup'); g.label = region;
  names.forEach(n => {
    const o = document.createElement('option'); o.value = n;
    o.textContent = `${n}（${countOf[n] || 0}）`;
    g.appendChild(o);
  });
  sel.appendChild(g);
});

// テーマボタン
const tagbar = document.getElementById('tagbar');
[{name:'', label:'すべて', color:'#444'}, ...D.tags.map(t => ({...t, label:t.name}))].forEach(t => {
  const b = document.createElement('button');
  b.className = 'tagbtn'; b.type = 'button';
  const n = t.name ? D.items.filter(i => i.tags.includes(t.name)).length : D.items.length;
  b.innerHTML = `${esc(t.label)}<span class="n">${n}</span>`;
  b.dataset.tag = t.name; b.dataset.color = t.color;
  b.onclick = () => { state.tag = t.name; render(); };
  tagbar.appendChild(b);
});

document.getElementById('q').oninput = e => { state.q = e.target.value.trim(); render(); };
sel.onchange = e => { state.pref = e.target.value; render(); };

function render(){
  tagbar.querySelectorAll('.tagbtn').forEach(b => {
    const on = b.dataset.tag === state.tag;
    b.setAttribute('aria-pressed', on);
    b.style.background = on ? b.dataset.color : '';
  });
  const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = D.items.filter(i =>
    (!state.tag || i.tags.includes(state.tag)) &&
    (!state.pref || i.pref === state.pref) &&
    words.every(w => (i.title + i.pref).toLowerCase().includes(w)));
  document.getElementById('count').textContent = `${shown.length} 件を表示（締切が近い順）`;
  const list = document.getElementById('list');
  if (!shown.length){ list.innerHTML = '<li class="empty">条件に合う案件はありません</li>'; return; }
  list.innerHTML = shown.map((i, n) => {
    const dl = daysLeft(i.deadline);
    const leftText = dl === 0 ? '本日締切' : `あと${dl}日`;
    const tagc = i.tags.length ? tagColor[i.tags[0]] : '';
    const official = i.short !== i.title ? `<p class="official">正式名：${esc(i.title)}</p>` : '';
    return `<li class="item${i.tags.length ? ' focus' : ''}" style="--tagc:${tagc}">
      <div class="meta"><span class="left${dl <= D.urgentDays ? ' urgent' : ''}">${leftText}</span>
        <span class="pref">${esc(i.pref)}</span>
        ${i.tags.map(t => `<span class="tag" style="background:${tagColor[t]}">${esc(t)}</span>`).join('')}</div>
      <h2><a href="${esc(i.page)}">${esc(i.short)}</a></h2>${official}
      <div class="foot"><span>締切 ${fmt(i.deadline)}</span>
        <span class="actions"><a class="btn sum" href="${esc(i.page)}">スマホ用まとめ</a>
        <a class="btn go" href="${esc(i.url)}" target="_blank" rel="noopener">__UNIT__のページへ</a>
        <button class="btn x" type="button" data-n="${D.items.indexOf(i)}">𝕏でシェア</button></span></div>
    </li>`;
  }).join('');
  list.querySelectorAll('button.x').forEach(b => b.onclick = () => shareX(D.items[+b.dataset.n].share));
}

// 都道府県ごとの公式ページ
document.getElementById('prefs').innerHTML = D.regions.map(([region, names]) => {
  const chips = names.map(n => {
    const p = D.prefs.find(p => p.name === n) || {url:'#'};
    const c = countOf[n] || 0;
    return `<a class="pchip${c ? '' : ' zero'}${p.error ? ' err' : ''}" href="${esc(p.url)}" target="_blank" rel="noopener"
      title="${p.error ? '今日はページが開けませんでした' : ''}">${esc(n)}<span class="n">${c}</span></a>`;
  }).join('');
  return `<div class="region"><b>${esc(region)}</b><div class="prefgrid">${chips}</div></div>`;
}).join('');

const soon = D.items.filter(i => daysLeft(i.deadline) <= D.urgentDays).length;
document.getElementById('npref').textContent = `（${Object.keys(countOf).length}__AREA__）`;
document.getElementById('soon').textContent = soon ? `・${D.urgentDays}日以内に締切 ${soon} 件` : '';
document.getElementById('updated').textContent = `・${D.updated.slice(0,10).replace(/-/g,'/')} 更新`;
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()

"""data.json から公開用の一覧ページ（docs/index.html）を作る。

使い方:  python build.py
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "docs"
JST = timezone(timedelta(hours=9))


TAIL = re.compile(
    r"[」』]?\s*(（案）)?(に関する|についての|に係る|に対する|への)?\s*"
    r"(御|ご)?(意見|パブリックコメント)(・情報)?(の)?(公募|募集|提出)?(手続(き)?)?(の実施)?(について|の募集について)?$"
)


def short_title(title, limit=70):
    """X投稿用に「〜に関する御意見の募集について」などの決まり文句を削って短くする。"""
    t = TAIL.sub("", title).strip()
    t = t or title
    # かぎかっこの開き・閉じの数をそろえる
    if t.count("「") > t.count("」"):
        t += "」"
    elif t.count("「") < t.count("」"):
        t = "「" + t
    if t.startswith("「") and t.endswith("」") and t.count("「") == 1:
        t = t[1:-1]
    return t if len(t) <= limit else t[: limit - 1] + "…"


def load_plain_titles():
    """plain_titles.json（案件番号 → わかりやすい言い換え）を読む。"""
    path = HERE / "plain_titles.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def display_title(item):
    """わかりやすい言い換えがあればそれを、なければ正式名称を短くしたものを使う。"""
    return item.get("plain") or short_title(item["title"])


def summary_path(item):
    """案件ごとのスマホ用まとめページの場所（サイト内の相対パス）。"""
    return f"p/{item['id']}.html"


def share_text(item, main_hashtag, hashtag_of, site_url):
    """1件ごとの投稿の定型文（一覧ページの「Xでシェア」と投稿文ページで共通）。
    リンク（23字として数える）込みで140字以内にする。"""
    d = datetime.fromisoformat(item["deadline"])
    tags = " ".join([main_hashtag] + [hashtag_of[t] for t in item["tags"]])
    make = lambda title: (f"📣【パブコメ募集】{d.month}/{d.day}まで\n\n"
                          f"「{title}」\n国（{item['ministry']}）\n\n"
                          f"ひとことからでも、誰でも送れます🙆\n{tags}\n\n")
    title = display_title(item)
    while len(make(title)) + 23 > 140 and len(title) > 8:
        title = title[:-2].rstrip("…") + "…"
    return make(title) + site_url + summary_path(item)


SHARE_JS = r"""
// スマホではXアプリを直接開く（アプリ内ブラウザで毎回ログインを求められないように）。
// アプリが開かなかったときだけ、1.5秒後にブラウザ版Xを開く。
function shareX(text){
  const web = 'https://x.com/intent/post?text=' + encodeURIComponent(text);
  if (!/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) { window.open(web, '_blank', 'noopener'); return; }
  const fallback = setTimeout(() => { if (!document.hidden) location.href = web; }, 1500);
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearTimeout(fallback); }, { once: true });
  location.href = 'twitter://post?message=' + encodeURIComponent(text);
}
"""


def main():
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    tags = json.loads((HERE / "keywords.json").read_text(encoding="utf-8"))["tags"]
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))

    now = datetime.now(JST).isoformat()
    open_items = [it for it in data["items"] if it["deadline"] and it["deadline"] >= now]
    hashtag_of = {t["name"]: t["hashtag"] for t in tags}
    plain = load_plain_titles()
    for it in open_items:
        if it["id"] in plain:
            it["plain"] = plain[it["id"]]
        it["share"] = share_text(it, config["main_hashtag"], hashtag_of, config["site_url"])
        it["page"] = summary_path(it)
    build_summary_pages(open_items, tags, config)
    payload = {
        "updated": data["updated"],
        "items": [{k: v for k, v in it.items() if k != "detail"} for it in open_items],
        "tags": [{"name": t["name"], "color": t["color"], "hashtag": t["hashtag"]} for t in tags],
        "siteUrl": config["site_url"],
        "mainHashtag": config["main_hashtag"],
        "urgentDays": config["urgent_days"],
        "newDays": config.get("new_days", 7),
    }
    page = TEMPLATE
    for key, value in {
        "__SITE_NAME__": html.escape(config["site_name"]),
        "__SITE_DESC__": html.escape(config["site_description"]),
        "__SITE_URL__": html.escape(config["site_url"]),
        "__COUNT__": str(len(open_items)),
        "__SHARE_JS__": SHARE_JS,
        "__DATA__": json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(key, value)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"docs/index.html を作りました（募集中 {len(open_items)} 件）")


def build_summary_pages(items, tag_defs, config):
    """案件ごとのスマホ用まとめページ（docs/p/案件番号.html）を作る。締切を過ぎたページは消す。"""
    out = OUT_DIR / "p"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.html"):
        old.unlink()
    color_of = {t["name"]: t["color"] for t in tag_defs}
    e = html.escape

    def file_list(files):
        return "".join(f'<li><a href="{e(f["url"])}" target="_blank" rel="noopener">📄 {e(f["name"])}</a></li>'
                       for f in files)

    for it in items:
        d = datetime.fromisoformat(it["deadline"])
        det = it.get("detail") or {}
        groups = [("まず読む：意見募集要領（出し方・提出先）", det.get("guide_files", [])),
                  ("案の中身", det.get("draft_files", [])),
                  ("関連資料", det.get("other_files", []))]
        files_html = "".join(f'<h3>{e(label)}</h3><ul class="files">{file_list(fs)}</ul>' for label, fs in groups if fs)
        n_files = sum(len(fs) for _, fs in groups[:2])
        note = e(det.get("note", "")).replace("\n", "<br>")
        replace = {
            "__TITLE__": e(display_title(it)),
            "__OFFICIAL__": e(it["title"]),
            "__TAGS__": "".join(f'<span class="tag" style="background:{color_of[t]}">{e(t)}</span>' for t in it["tags"]),
            "__CATEGORY__": e(it.get("category") or ""),
            "__MINISTRY__": e(it["ministry"]),
            "__DEADLINE__": f"{d.year}年{d.month}月{d.day}日 {d.hour}:{d.minute:02d}",
            "__DEADLINE_ISO__": e(it["deadline"]),
            "__EGOV__": e(it["url"]),
            "__FILES__": files_html or '<p class="sub">資料はe-Govのページでご確認ください。</p>',
            "__N_FILES__": str(n_files),
            "__CONTACT__": e(det.get("contact", "")).replace("\n", "<br>") or "e-Govのページでご確認ください。",
            "__NOTE__": f"<section><h2>備考</h2><p>{note}</p></section>" if note else "",
            "__SHARE__": json.dumps(it["share"], ensure_ascii=False).replace("</", "<\\/"),
            "__SHARE_JS__": SHARE_JS,
            "__SITE_NAME__": e(config["site_name"]),
            "__PAGE_URL__": e(config["site_url"] + summary_path(it)),
            "__DESC__": e(f"{d.month}/{d.day}まで意見募集中（{it['ministry']}）。ひとことからでも、誰でも意見を送れます。"),
        }
        page = SUMMARY_TEMPLATE
        for k, v in replace.items():
            page = page.replace(k, v)
        (out / f"{it['id']}.html").write_text(page, encoding="utf-8")


SUMMARY_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__｜__SITE_NAME__</title>
<meta name="description" content="__DESC__">
<meta property="og:type" content="article">
<meta property="og:title" content="【パブコメ募集】__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__PAGE_URL__">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📣</text></svg>">
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1c1b19;--sub:#5f5c56;--line:#e3e0d9;--accent:#1d4ed8;--urgent:#dc2626;--urgent-bg:#fef2f2;--chip:#efede8}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#16161a;--card:#202026;--ink:#ecebe8;--sub:#a8a59f;--line:#34343c;--accent:#7aa2ff;--urgent:#f87171;--urgent-bg:#3a1e1e;--chip:#2c2c33}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI","Meiryo",sans-serif;line-height:1.7}
a{color:var(--accent)}
.wrap{max-width:640px;margin:0 auto;padding:12px 16px 40px}
.back{font-size:.88rem;text-decoration:none}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 6px;font-size:.8rem}
.tag{color:#fff;padding:1px 8px;border-radius:6px;font-weight:600}
.cat{background:var(--chip);padding:1px 8px;border-radius:6px;color:var(--sub)}
h1{font-size:1.35rem;line-height:1.5;margin:4px 0 6px}
.official{font-size:.82rem;color:var(--sub);margin:0 0 14px}
.deadline{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.left{font-weight:800;font-size:1.1rem;padding:2px 10px;border-radius:8px;background:var(--chip)}
.left.urgent{background:var(--urgent-bg);color:var(--urgent)}
.deadline small{color:var(--sub);display:block;font-size:.78rem}
.btns{display:flex;flex-direction:column;gap:8px;margin:14px 0}
.btn{display:block;text-align:center;text-decoration:none;border-radius:12px;padding:14px;font-size:1.05rem;font-weight:700;border:0;font-family:inherit;cursor:pointer;width:100%}
.btn.go{background:var(--accent);color:#fff}
.btn.sum{background:var(--chip);color:var(--ink)}
.btn.x{background:var(--ink);color:var(--bg)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:12px 0}
h2{font-size:1rem;margin:0 0 6px}
h3{font-size:.88rem;margin:10px 0 4px;color:var(--sub)}
ol{padding-left:1.3em;margin:4px 0}
ol li{margin:4px 0}
ul.files{list-style:none;padding:0;margin:0}
ul.files li{margin:4px 0}
ul.files a{display:block;padding:8px 10px;border:1px solid var(--line);border-radius:8px;text-decoration:none}
.sub{color:var(--sub);font-size:.85rem}
.warn{background:var(--urgent-bg);border-radius:8px;padding:8px 10px;font-size:.88rem;margin:8px 0 0}
footer{font-size:.78rem;color:var(--sub);margin-top:20px}
</style>
</head>
<body>
<div class="wrap">
<a class="back" href="../">← 募集中のパブコメ一覧（__SITE_NAME__）</a>
<div class="meta">__TAGS__<span class="cat">__CATEGORY__</span><span class="cat">__MINISTRY__</span></div>
<h1>__TITLE__</h1>
<p class="official">正式名：__OFFICIAL__</p>

<div class="deadline"><span class="left" id="left"></span><span><small>意見の締切</small>__DEADLINE__</span></div>

<div class="btns">
  <a class="btn go" href="__EGOV__" target="_blank" rel="noopener">e-Gov（国のページ）で意見を出す</a>
  <button type="button" class="btn x" id="share">𝕏でシェアして広める</button>
</div>

<section>
  <h2>✍️ 意見の出し方</h2>
  <ol>
    <li>下の「資料」を開いて、どんな案か読む（概要だけでもOK）</li>
    <li>上の青いボタンでe-Govを開く</li>
    <li>e-Govのページで、資料をひとつずつ開く</li>
    <li>「全部を確認しました」にチェック →「意見入力へ」</li>
    <li>意見を書いて送信（ひとことでも大丈夫）</li>
  </ol>
  <p class="warn">⚠️ e-Govでは、資料（この案件は__N_FILES__個）を<b>すべて一度開かないと</b>チェックが入れられない仕組みになっています。</p>
</section>

<section>
  <h2>📚 資料</h2>
  __FILES__
</section>

__NOTE__

<section>
  <h2>☎️ 問い合わせ先</h2>
  <p>__CONTACT__</p>
</section>

<footer>このページは <a href="__EGOV__" target="_blank" rel="noopener">e-Govパブリック・コメント</a> の情報をスマホで読みやすくまとめたものです。わかりやすい名前は当サイトが付けたもので、正式な内容は必ず国の公式ページでご確認ください。</footer>
</div>
<script>
__SHARE_JS__
const ymd = d => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
const dl = Math.round((ymd(new Date('__DEADLINE_ISO__')) - ymd(new Date())) / 86400000);
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
<title>__SITE_NAME__｜いま意見を出せる国の案件一覧</title>
<meta name="description" content="__SITE_DESC__">
<meta property="og:type" content="website">
<meta property="og:title" content="__SITE_NAME__｜募集中のパブコメ __COUNT__件">
<meta property="og:description" content="__SITE_DESC__">
<meta property="og:url" content="__SITE_URL__">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📣</text></svg>">
<style>
:root{
  --bg:#f6f5f2;--card:#fff;--ink:#1c1b19;--sub:#5f5c56;--line:#e3e0d9;
  --accent:#1d4ed8;--urgent:#dc2626;--urgent-bg:#fef2f2;--chip:#efede8;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#16161a;--card:#202026;--ink:#ecebe8;--sub:#a8a59f;--line:#34343c;
    --accent:#7aa2ff;--urgent:#f87171;--urgent-bg:#3a1e1e;--chip:#2c2c33;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Hiragino Sans","Noto Sans JP","Yu Gothic UI","Meiryo",sans-serif;line-height:1.6}
a{color:var(--accent)}
.wrap{max-width:860px;margin:0 auto;padding:0 16px}
header{padding:28px 0 12px}
h1{font-size:1.6rem;margin:0 0 4px;letter-spacing:.02em}
.lead{color:var(--sub);margin:0 0 12px;font-size:.95rem}
.stats{display:flex;gap:10px;flex-wrap:wrap;font-size:.85rem;color:var(--sub)}
.stats b{color:var(--ink);font-size:1.1rem}
details.howto{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:12px 0;font-size:.92rem}
details.howto summary{cursor:pointer;font-weight:600}
details.howto ol{margin:8px 0 4px;padding-left:1.3em}
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
ul.list{list-style:none;padding:0;margin:0 0 40px}
.item{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0;
  border-left:5px solid var(--line)}
.item.focus{border-left-color:var(--tagc)}
.meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.8rem;color:var(--sub);margin-bottom:4px}
.left{font-weight:700;padding:1px 8px;border-radius:6px;background:var(--chip);color:var(--ink)}
.left.urgent{background:var(--urgent-bg);color:var(--urgent)}
.new{font-weight:700;padding:1px 8px;border-radius:6px;background:#fef3c7;color:#b45309}
.tagbtn.newbtn[aria-pressed="true"]{background:#d97706}
.tag{color:#fff;padding:1px 8px;border-radius:6px;font-weight:600}
.cat{background:var(--chip);padding:1px 8px;border-radius:6px}
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
.empty{text-align:center;color:var(--sub);padding:40px 0}
footer{font-size:.8rem;color:var(--sub);padding:20px 0 40px;border-top:1px solid var(--line)}
</style>
</head>
<body>
<div class="wrap">
<header>
  <p style="font-size:.85rem;margin:0 0 10px"><b>🏛️ 国</b> ／ <a href="pref/">🗾 都道府県</a> ／ <a href="city/">🏙️ 市区町村</a>　｜　<a href="posts.html">📣 X投稿文ページ</a></p>
  <h1>📣 __SITE_NAME__</h1>
  <p class="lead">__SITE_DESC__</p>
  <div class="stats"><span>募集中 <b id="total">__COUNT__</b> 件</span><span id="soon"></span><span id="updated"></span></div>
  <details class="howto">
    <summary>パブコメ（意見公募）ってなに？ 意見の出し方</summary>
    <p>国が新しいルール（政令・省令など）を作る前に、国民から広く意見を聞く制度です。年齢や国籍を問わず誰でも無料で意見を出せます（氏名などの記入が任意の案件も多くあります）。</p>
    <ol>
      <li>気になる案件の「スマホ用まとめ」で内容と資料を確認（「e-Govへ」で国の公式ページに直接進むこともできます）</li>
      <li>「意見募集要領」や「案の概要」を読む</li>
      <li>ページ内の「意見を提出する」から、フォームに意見を書いて送信</li>
    </ol>
    <p>短い一言でも大丈夫です。締切を過ぎると受け付けられないので、お早めに。</p>
  </details>
</header>

<div class="filters">
  <div class="tagbar" id="tagbar" role="group" aria-label="注目テーマで絞り込み"></div>
  <div class="row">
    <input id="q" type="search" placeholder="キーワードで探す（例：年金、保育）">
    <select id="ministry"><option value="">すべての省庁</option></select>
    <select id="sort" aria-label="並び替え"><option value="deadline">締切が近い順</option><option value="new">新しく始まった順</option></select>
  </div>
</div>

<p class="count" id="count"></p>
<ul class="list" id="list"></ul>

<footer>
  出典：<a href="https://public-comment.e-gov.go.jp/" target="_blank" rel="noopener">e-Govパブリック・コメント</a>（毎日自動で更新）。
  テーマ分けは案件名などに含まれる言葉で自動判定しているため、漏れや誤りがある場合があります。必ず公式ページで内容をご確認ください。
</footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const tagColor = Object.fromEntries(D.tags.map(t => [t.name, t.color]));
const now = new Date();
const state = { tag: '', q: '', ministry: '', onlyNew: false, sort: 'deadline' };

// 締切日と今日の「日付」の差（時刻は見ない）。今日が締切なら0
function ymd(d){ return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()); }
function daysLeft(iso){ return Math.round((ymd(new Date(iso)) - ymd(now)) / 86400000); }
// 募集が始まってからの日数（新着の判定用）
function daysSince(iso){ return Math.round((ymd(now) - ymd(new Date(iso))) / 86400000); }
const isNew = i => i.published && daysSince(i.published) < D.newDays;
function fmt(iso){ const d = new Date(iso); return `${d.getMonth()+1}/${d.getDate()}`; }
function esc(s){ return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// 省庁の選択肢
[...new Set(D.items.map(i => i.ministry).filter(Boolean))].sort().forEach(m => {
  const o = document.createElement('option'); o.value = o.textContent = m;
  document.getElementById('ministry').appendChild(o);
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
// 新着だけ表示するボタン（テーマとは別に、重ねて使える）
const newN = D.items.filter(isNew).length;
const newBtn = document.createElement('button');
newBtn.className = 'tagbtn newbtn'; newBtn.type = 'button';
newBtn.innerHTML = `🆕 新着（${D.newDays}日以内）<span class="n">${newN}</span>`;
newBtn.onclick = () => { state.onlyNew = !state.onlyNew; render(); };
tagbar.appendChild(newBtn);
document.getElementById('sort').onchange = e => { state.sort = e.target.value; render(); };

document.getElementById('q').oninput = e => { state.q = e.target.value.trim(); render(); };
document.getElementById('ministry').onchange = e => { state.ministry = e.target.value; render(); };

const soonN = D.items.filter(i => daysLeft(i.deadline) <= D.urgentDays).length;
document.getElementById('soon').innerHTML = `${D.urgentDays}日以内に締切 <b>${soonN}</b> 件　🆕 ${D.newDays}日以内の新着 <b>${newN}</b> 件`;
document.getElementById('updated').textContent = '最終更新：' + D.updated.replace('T', ' ').slice(0, 16);

function render(){
  tagbar.querySelectorAll('.tagbtn').forEach(b => {
    const on = b.dataset.tag === state.tag;
    b.setAttribute('aria-pressed', on);
    b.style.background = on ? b.dataset.color : '';
  });
  newBtn.setAttribute('aria-pressed', state.onlyNew);
  const items = D.items.filter(i =>
    (!state.onlyNew || isNew(i)) &&
    (!state.tag || i.tags.includes(state.tag)) &&
    (!state.ministry || i.ministry === state.ministry) &&
    (!state.q || (i.title + (i.plain || '') + i.category + i.ministry).includes(state.q))
  );
  if (state.sort === 'new') items.sort((a, b) => (b.published || '').localeCompare(a.published || '') || a.deadline.localeCompare(b.deadline));
  document.getElementById('count').textContent = `${items.length} 件を表示中（${state.sort === 'new' ? '新しく始まった順' : '締切が近い順'}）`;
  const list = document.getElementById('list');
  if (!items.length){ list.innerHTML = '<li class="empty">条件に合う募集中の案件はありません</li>'; return; }
  list.innerHTML = items.map(i => {
    const dl = daysLeft(i.deadline);
    const urgent = dl <= D.urgentDays;
    const leftTxt = dl <= 0 ? '本日締切' : `あと${dl}日`;
    const tagsHtml = i.tags.map(t => `<span class="tag" style="background:${tagColor[t]}">${esc(t)}</span>`).join('');
    const first = i.tags[0];
    return `<li class="item${first ? ' focus' : ''}" style="${first ? '--tagc:' + tagColor[first] : ''}">
      <div class="meta"><span class="left${urgent ? ' urgent' : ''}">${leftTxt}</span>${isNew(i) ? '<span class="new">🆕 新着</span>' : ''}${tagsHtml}<span class="cat">${esc(i.category || '')}</span></div>
      <h2><a href="${esc(i.page)}">${esc(i.plain || i.title)}</a></h2>
      ${i.plain ? `<p class="official">正式名：${esc(i.title)}</p>` : ''}
      <div class="foot"><span>${esc(i.ministry)}｜${i.published ? fmt(i.published) + '開始・' : ''}締切 ${fmt(i.deadline)} ${new Date(i.deadline).toTimeString().slice(0,5)}</span>
        <span class="actions"><a class="btn sum" href="${esc(i.page)}">スマホ用まとめ</a>
        <a class="btn go" href="${esc(i.url)}" target="_blank" rel="noopener">e-Govへ</a>
        <button type="button" class="btn x" data-id="${esc(i.id)}">𝕏でシェア</button></span></div>
    </li>`;
  }).join('');
}
render();
__SHARE_JS__
document.getElementById('list').addEventListener('click', e => {
  const b = e.target.closest('button.x'); if (!b) return;
  const i = D.items.find(x => x.id === b.dataset.id);
  shareX(i.share);
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()

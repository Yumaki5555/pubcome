"""国・都道府県・市区町村の3つの版で共通に使う、ページの見た目と動き（デザイン・上部の切り替えボタン・検索・共有）。

build.py（国版）と 都道府県レベル/build.py（都道府県版・市区町村版）が、ここの部品を組み合わせてページを作る。
"""
import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
JST = timezone(timedelta(hours=9))
WEEK = "月火水木金土日"

# 上部の切り替えボタン（キー, 名前, 公開フォルダ内の場所, データのフォルダ）
LEVELS = [
    ("national", "国", "", HERE),
    ("pref", "都道府県", "pref/", HERE / "都道府県レベル"),
    ("city", "市区町村", "city/", HERE / "市区町村レベル"),
]
LEVEL_NAME = {key: name for key, name, _, _ in LEVELS}

EGOV_TOP = "https://public-comment.e-gov.go.jp/"


def esc(text):
    return html.escape(str(text or ""))


def today_jst():
    return datetime.now(JST).date().isoformat()


def effective_deadline(iso):
    """締切を (日付 'YYYY-MM-DD', 時刻 'HH:MM' または '') にする。
    e-Gov の「10月30日0時0分」締切は、実際には10月29日の終わりまでなので「10月29日 24:00」として扱う。"""
    iso = iso or ""
    day, clock = iso[:10], iso[11:16]
    if clock == "00:00":
        day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        clock = "24:00"
    return day, clock


def date_ja(day, with_year=True):
    """'2026-10-26' → '2026年10月26日（月）'"""
    d = date.fromisoformat(day[:10])
    head = f"{d.year}年" if with_year else ""
    return f"{head}{d.month}月{d.day}日（{WEEK[d.weekday()]}）"


def updated_ja(iso):
    """data.json の updated（'2026-10-25T09:00+09:00'）を '2026年10月25日（日）9:00' にする。"""
    if not iso:
        return ""
    d = datetime.fromisoformat(iso)
    return f"{date_ja(d.date().isoformat())} {d.hour}:{d.minute:02d}"


def level_counts():
    """国・都道府県・市区町村それぞれの、締切日ごとの募集中の件数（上部ボタンの件数に使う）。
    ページを開いた日に締切が過ぎたものを画面側で数えないように、締切日ごとに数を持たせておく。"""
    today = today_jst()
    out = {}
    for key, _, _, folder in LEVELS:
        counts = {}
        try:
            data = json.loads((folder / "data.json").read_text(encoding="utf-8"))
            ex_path = folder / "exclude.json"
            excluded = json.loads(ex_path.read_text(encoding="utf-8")) if ex_path.exists() else {}
        except (OSError, ValueError):
            out[key] = counts
            continue
        for it in data.get("items", []):
            day, _ = effective_deadline(it.get("deadline"))
            if day and day >= today and it["id"] not in excluded:
                counts[day] = counts.get(day, 0) + 1
        out[key] = counts
    return out


def count_open(counts, key):
    today = today_jst()
    return sum(n for day, n in counts.get(key, {}).items() if day >= today)


# 自治体のページから抜き出した「意見の出し方」の文から、書かれている提出方法を拾う（書いてある言葉だけで判断する）
METHODS = [
    ("入力フォーム", r"フォーム|電子申請|オンライン申請|LoGo"),
    ("メール", r"(?<!フォーム)メール(?!アドレス)"),
    ("郵送", r"郵送|郵便"),
    ("FAX", r"(ファクシミリ|ファックス|ファクス|ＦＡＸ|FAX|Fax|fax)(?!番号)"),
    ("持参", r"持参|直接(提出|持ち|お持ち)"),
]


def submit_methods(howto):
    return [name for name, pat in METHODS if re.search(pat, howto or "")]


def split_summary(summary):
    """かんたん要約を (ひとこと, 箇条書きのリスト) に分ける。1行目＝ひとこと、「・」で始まる行＝箇条書き。"""
    lines = [x.strip() for x in (summary or "").strip().split("\n") if x.strip()]
    head = " ".join(x for x in lines if not x.startswith("・"))
    points = [x[1:].strip() for x in lines if x.startswith("・")]
    return head, points


def summary_block(summary, source):
    """案件ページの「どんな案？」欄。要約がなければ空。"""
    head, points = split_summary(summary)
    if not head and not points:
        return ""
    body = f"<p>{esc(head)}</p>" if head else ""
    if points:
        body += "<h3>主な内容</h3><ul>" + "".join(f"<li>{esc(x)}</li>" for x in points) + "</ul>"
    return (f'<section class="box" aria-labelledby="gist-h"><h2 id="gist-h">📝 どんな案？（かんたん要約）</h2>{body}'
            f'<p class="note">※{esc(source)}の資料をもとにAIがまとめたものです。正確な内容は、下の「資料」や公式ページでご確認ください。</p></section>')


# ---------- 上部の切り替えボタン ----------

def nav_html(current, root, counts, posts=False):
    """全ページ共通の上部（サイト名・X投稿文ページへのリンク・国／都道府県／市区町村の切り替えボタン）。
    root はそのページから公開フォルダの一番上までの道のり（'' / '../' / '../../'）。
    counts が None のときは件数を書かず、ページを開いたときに counts.json から読み込む。"""
    links = []
    for key, name, path, _ in LEVELS:
        href = (root + path) or "./"
        cur = ""
        if key == current and not posts:
            cur = ' aria-current="page"'
        links.append(
            f'<a class="lv" href="{href}" data-base="{href}" data-level="{key}"{cur}>'
            f'<span class="lv-name">{name}</span>'
            + (f'<span class="lv-n">募集中 <b data-count="{key}">{count_open(counts, key)}</b>件</span></a>' if counts is not None else
               f'<span class="lv-n" hidden>募集中 <b data-count="{key}"></b>件</span></a>'))
    level_path = dict((k, p) for k, _, p, _ in LEVELS).get(current, "")
    xcur = ' aria-current="page"' if posts else ""
    return (
        '<a class="skip" href="#main">本文へ移動</a>'
        '<header class="site-head"><div class="wrap head-row">'
        f'<a class="brand" href="{root or "./"}">📣 パブコメ掲示板</a>'
        f'<a class="xlink" href="{root}{level_path}posts.html"{xcur}>X投稿文ページ</a></div>'
        f'<nav class="wrap levels" aria-label="国・都道府県・市区町村の切り替え">{"".join(links)}</nav>'
        '</header>')


GUIDE_HTML = """<details class="guide">
<summary>はじめての方へ：くわしい説明と、意見の出し方（3ステップ）</summary>
<div class="guide-body">
<p>国や自治体は、法律にもとづく細かいルール（政令・省令など）や、条例・計画などを決める前に、案を公表して意見を募集します。これを「意見公募手続」「パブリックコメント（パブコメ）」といいます。</p>
<h3>どうやって意見を出す？</h3>
<ol class="steps">
<li><b>案件を探す</b><span>キーワード・テーマ・地域・締切で、気になる案件をしぼりこみます。</span></li>
<li><b>「内容を見る」で中身を確かめる</b><span>かんたんな要約と、公式の資料へのリンクがあります。</span></li>
<li><b>「意見を提出する」から公式ページで送る</b><span>国の案件はe-Govの入力画面など、自治体の案件はメール・入力フォーム・郵送など、公式ページに書かれた方法で送ります。</span></li>
</ol>
<h3>知っておいてほしいこと</h3>
<ul>
<li><b>出せる人や出し方は、案件ごとに違います。</b>国の案件は広く一般から受け付けています。自治体の案件は「住んでいる人・通勤や通学をしている人」などに限られることがあります。必ず公式ページで確かめてください。</li>
<li><b>出した意見が、必ず採用されるわけではありません。</b>寄せられた意見は、案を決める前に検討されます。多くの場合、結果と「意見に対する考え方」が後日公表されます。</li>
<li>締切を過ぎると受け付けてもらえません。締切の時刻にも気をつけてください。</li>
</ul>
</div>
</details>"""


SHARE_DIALOG = """<dialog id="share-dialog" class="share-dlg" aria-labelledby="share-h">
<div class="dlg-in">
<h2 id="share-h">Xで共有する</h2>
<p class="note">投稿する文章です。内容を確かめてから投稿してください。</p>
<label class="sr" for="share-text">投稿する文章</label>
<textarea id="share-text" rows="9" readonly></textarea>
<div class="dlg-btns">
<button type="button" class="btn primary" id="share-post">Xで投稿する</button>
<button type="button" class="btn outline" id="share-copy">文章をコピー</button>
</div>
<p class="copy-msg" id="share-msg" role="status" aria-live="polite"></p>
<p class="note">Xの画面が開かないときは「文章をコピー」を押して、Xアプリに貼り付けてください。</p>
<button type="button" class="btn ghost" id="share-close">閉じる</button>
</div>
</dialog>
<button type="button" class="totop" id="totop" aria-label="ページの上に戻る" hidden>▲<br>上へ</button>"""


CSS = r"""
:root{
  --bg:#ffffff;--soft:#f4f7f5;--ink:#1b2420;--sub:#4b5751;--line:#d3dcd6;
  --green:#1f6e46;--green-dk:#16553a;--green-soft:#e8f3ec;--green-line:#9fcbb1;
  --red:#b42318;--red-soft:#fdeceb;--orange:#9a4b00;--orange-soft:#fff1df;--orange-line:#e08a2c;
  --focus:#d08700;
  color-scheme:light;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-size:16px;line-height:1.75;overflow-wrap:anywhere;
  font-family:"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic UI","Meiryo",sans-serif}
a{color:var(--green-dk)}
h1,h2,h3{line-height:1.45}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:-9999px;top:8px;z-index:50;background:#fff;padding:10px 14px;border:2px solid var(--green)}
.skip:focus{left:16px}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
.note{font-size:.875rem;color:var(--sub);margin:4px 0 0}

/* 上部 */
.site-head{background:#fff;border-bottom:1px solid var(--line)}
.head-row{display:flex;align-items:center;justify-content:space-between;gap:8px 12px;flex-wrap:wrap;padding-top:10px;padding-bottom:10px}
.brand{font-weight:800;font-size:1.1875rem;color:var(--ink);text-decoration:none;min-height:44px;display:inline-flex;align-items:center}
.xlink{display:inline-flex;align-items:center;min-height:44px;padding:6px 14px;border:1.5px solid var(--line);border-radius:10px;
  background:var(--soft);color:var(--ink);text-decoration:none;font-size:.9375rem;font-weight:700}
.xlink:hover{border-color:var(--green)}
.xlink[aria-current]{background:var(--green-soft);border-color:var(--green);color:var(--green-dk)}
.xlink[aria-current]::before{content:"✓ "}
.levels{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding-bottom:14px}
.lv{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:66px;padding:6px 4px;
  border:2px solid var(--green);border-radius:12px;background:#fff;color:var(--green-dk);text-decoration:none;text-align:center;line-height:1.35}
.lv-name{font-size:1.1875rem;font-weight:800}
.lv-n{font-size:.9375rem}
.lv:hover{background:var(--green-soft)}
.lv[aria-current]{background:var(--green);color:#fff}
.lv[aria-current]:hover{background:var(--green-dk)}
.lv[aria-current] .lv-name::before{content:"✓ "}

/* ボタン */
.btn{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;min-height:48px;padding:8px 14px;
  border:2px solid transparent;border-radius:10px;font:inherit;font-size:1rem;font-weight:700;line-height:1.35;text-align:center;
  text-decoration:none;cursor:pointer}
.btn small{display:block;font-size:.875rem;font-weight:500;margin-top:2px}
.btn.primary{background:var(--green);border-color:var(--green);color:#fff}
.btn.primary:hover{background:var(--green-dk);border-color:var(--green-dk)}
.btn.outline{background:#fff;border-color:var(--green);color:var(--green-dk)}
.btn.outline:hover{background:var(--green-soft)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.btn[disabled]{opacity:.5;cursor:default}

/* ページ冒頭 */
.intro{padding:16px 0 2px}
.intro h1{font-size:1.375rem;margin:0 0 4px}
@media (min-width:600px){.intro h1{font-size:1.5rem}}
.lead{margin:0 0 8px;font-size:1rem}
.sub{color:var(--sub)}
details.guide{border:1px solid var(--green-line);background:var(--green-soft);border-radius:12px;margin:8px 0 4px}
details.guide summary{cursor:pointer;font-weight:700;padding:10px 14px;min-height:44px;list-style-position:inside}
.guide-body{padding:0 16px 12px;background:#fff;border-radius:0 0 12px 12px;border-top:1px solid var(--green-line)}
.guide-body h3{font-size:1.0625rem;margin:14px 0 6px}
.guide-body ul{padding-left:1.2em;margin:4px 0}
.guide-body li{margin:6px 0}
ol.steps{list-style:none;counter-reset:s;padding:0;margin:6px 0;display:grid;gap:8px}
ol.steps li{counter-increment:s;display:grid;grid-template-columns:36px 1fr;column-gap:10px;align-items:start}
ol.steps li::before{content:counter(s);grid-row:span 2;width:36px;height:36px;border-radius:50%;background:var(--green);color:#fff;
  font-weight:800;display:flex;align-items:center;justify-content:center}
ol.steps li b{display:block}
ol.steps li span{color:var(--sub)}

/* 検索 */
.search{background:var(--soft);border:1px solid var(--line);border-radius:14px;padding:14px 16px 16px;margin:14px 0 20px}
.search-label{display:block;font-weight:800;font-size:1.125rem;margin-bottom:6px}
.qrow{display:flex;gap:8px}
.qrow input{flex:1;min-width:0;min-height:52px;padding:10px 14px;border:2px solid var(--green);border-radius:10px;background:#fff;color:var(--ink);
  font:inherit;font-size:1.0625rem}
.qrow .btn{min-width:84px}
.frow{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:10px;margin:14px 0 6px}
.field{display:flex;flex-direction:column;gap:4px;font-weight:700;font-size:.9375rem}
select{min-height:48px;width:100%;padding:8px 10px;border:1.5px solid var(--line);border-radius:10px;background:#fff;color:var(--ink);font:inherit;font-size:1rem}
fieldset.chips{border:0;margin:12px 0 0;padding:0;min-width:0}
fieldset.chips legend{font-weight:700;font-size:.9375rem;padding:0;margin-bottom:6px}
fieldset.chips legend .note{font-weight:400;margin-left:6px}
.chip-row{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:6px 14px;border:1.5px solid var(--line);border-radius:999px;
  background:#fff;color:var(--ink);font:inherit;font-size:.9375rem;cursor:pointer}
.chip:hover{border-color:var(--green)}
.chip[aria-pressed="true"]{background:var(--green);border-color:var(--green);color:#fff;font-weight:700}
.chip[aria-pressed="true"]::before{content:"✓"}
.chip .n{font-size:.875rem;opacity:.85}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--c);flex:none}
.chip[aria-pressed="true"] .dot{box-shadow:0 0 0 2px #fff}
.srow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;margin-top:14px}

/* 検索結果 */
.result-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:2px 16px;margin:0 0 6px;scroll-margin-top:12px}
.result-head h2{font-size:1.25rem;margin:0}
.updated{margin:0;color:var(--sub);font-size:.9375rem}
.scope{margin:0 0 10px;color:var(--sub);font-size:.9375rem}
.nw{white-space:nowrap}
.active{margin:0 0 10px;font-size:.9375rem;display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}
.active:empty{display:none}
.active .btn{min-height:44px;padding:4px 12px}
.related{margin:0 0 12px}
.related:empty{display:none}
.state{padding:18px;border-radius:12px;background:var(--soft);text-align:center}
.state:empty{display:none}
.error{background:var(--red-soft);color:var(--red);border-radius:12px;padding:14px 16px}
.empty{text-align:left;background:var(--soft);border-radius:14px;padding:16px 18px}
.empty .empty-h{font-weight:800;font-size:1.125rem;margin:0 0 6px}
.empty ul{margin:4px 0 10px;padding-left:1.2em}
.cards{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:minmax(0,1fr);gap:16px}
@media (min-width:900px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
.card{container-type:inline-size;display:flex;flex-direction:column;gap:8px;background:#fff;border:1px solid var(--line);border-radius:14px;
  padding:16px 18px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card.red{border-top:6px solid var(--red)}
.card.orange{border-top:6px solid var(--orange-line)}
.card-top{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.due{display:inline-flex;align-items:center;font-weight:800;font-size:1rem;padding:2px 10px;border-radius:8px;background:var(--soft);color:var(--ink)}
.due.red{background:var(--red-soft);color:var(--red)}
.due.orange{background:var(--orange-soft);color:var(--orange)}
.new{font-weight:700;font-size:.9375rem;padding:2px 10px;border-radius:8px;border:1.5px solid var(--green);color:var(--green-dk)}
.who{margin:0;font-size:.9375rem;color:var(--sub);font-weight:700}
.who .cat{font-weight:400;margin-left:8px}
.card h3{font-size:1.25rem;margin:0}
.card h3 a{color:var(--ink);text-decoration:none}
.card h3 a:hover{text-decoration:underline}
.official{margin:0;font-size:.9375rem;color:var(--sub)}
.deadline{margin:0;font-weight:700;font-size:1.0625rem}
.about{background:var(--soft);border-radius:10px;padding:10px 12px}
.about .lbl{margin:0;font-weight:700;font-size:.9375rem;color:var(--green-dk)}
.about p{margin:0 0 4px}
.about ul{margin:2px 0 0;padding-left:1.2em}
.about li{margin:2px 0}
.facts{margin:0;font-size:.9375rem}
.facts b{font-weight:700}
.themes{margin:0;font-size:.9375rem;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center}
.themes .t{display:inline-flex;align-items:center;gap:5px}
.actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:auto;padding-top:6px}
.actions .share{grid-column:1/-1}
@container (min-width:560px){.actions{grid-template-columns:repeat(3,minmax(0,1fr))}.actions .share{grid-column:auto}}
.src{margin:0;font-size:.875rem;color:var(--sub)}
.more-wrap{text-align:center;margin:18px 0 8px}
.more-wrap .btn{min-width:min(100%,320px)}
.more-wrap .btn[hidden]{display:none}

/* 下の情報欄 */
.info{margin:36px 0 0;border-top:1px solid var(--line);padding-top:12px}
.info h2{font-size:1.25rem;margin:8px 0}
.info dl{margin:0}
.info dl div{padding:10px 0;border-bottom:1px solid var(--line)}
.info dt{font-weight:700}
.info dd{margin:2px 0 0}
details.areas{margin:14px 0}
details.areas summary{cursor:pointer;font-weight:700;min-height:44px;display:flex;align-items:center}
.region{margin:10px 0}
.region b{display:block;font-size:.9375rem;color:var(--sub);margin-bottom:4px}
.pgrid{display:flex;flex-wrap:wrap;gap:6px}
.pchip{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:4px 12px;border:1px solid var(--line);border-radius:10px;
  background:#fff;color:var(--ink);text-decoration:none;font-size:.9375rem}
.pchip:hover{border-color:var(--green)}
.pchip .n{font-weight:700;color:var(--green-dk)}
.pchip.zero .n{color:var(--sub);font-weight:400}
.pchip.err{border-style:dashed}
.pchip .e{color:var(--red);font-size:.875rem}

.site-foot{margin-top:36px;background:var(--soft);border-top:1px solid var(--line);color:var(--sub);font-size:.9375rem;padding:18px 0 96px}
.site-foot p{margin:4px 0}

/* 案件ページ */
.detail{max-width:780px}
.back{display:inline-flex;align-items:center;gap:4px;min-height:44px;margin-top:8px;font-weight:700;text-decoration:none}
.back:hover{text-decoration:underline}
.detail h1{font-size:1.5rem;margin:6px 0 4px}
.detail .who{margin-top:6px}
.dl-box{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;border:2px solid var(--line);border-radius:14px;padding:12px 16px;margin:14px 0}
.dl-box.red{border-color:var(--red);background:var(--red-soft)}
.dl-box.orange{border-color:var(--orange-line);background:var(--orange-soft)}
.dl-box .due{font-size:1.125rem;background:#fff}
.dl-main{font-size:1.125rem;font-weight:800}
.dl-main small{display:block;font-size:.875rem;font-weight:400;color:var(--sub)}
.closed{background:var(--red-soft);color:var(--red);border-radius:12px;padding:12px 16px;font-weight:700;margin:12px 0}
.big-actions{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;margin:14px 0}
@media (min-width:600px){.big-actions{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}}
.big-actions .btn{min-height:56px;font-size:1.0625rem}
section.box{border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin:16px 0;background:#fff}
section.box h2{font-size:1.1875rem;margin:0 0 8px}
section.box h3{font-size:1rem;margin:14px 0 4px}
section.box ul{padding-left:1.2em;margin:4px 0}
section.box li{margin:4px 0}
ul.files{list-style:none;padding:0;margin:0}
ul.files li{margin:6px 0}
ul.files a{display:flex;align-items:center;min-height:48px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;text-decoration:none}
ul.files a:hover{border-color:var(--green);background:var(--green-soft)}
.quote{border-left:4px solid var(--green-line);padding:4px 0 4px 12px;margin:8px 0}
.warn{background:var(--orange-soft);border-radius:10px;padding:10px 12px;margin:10px 0 0}
.basic{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0}
.basic dt{font-weight:700;color:var(--sub)}
.basic dd{margin:0}

/* 共有の小窓・上へ戻る */
dialog.share-dlg{border:0;border-radius:16px;padding:0;width:min(520px,calc(100% - 24px));max-height:calc(100% - 24px);color:var(--ink)}
dialog.share-dlg::backdrop{background:rgba(0,0,0,.5)}
.dlg-in{padding:18px 18px 16px}
.dlg-in h2{font-size:1.25rem;margin:0}
.dlg-in textarea{width:100%;margin:10px 0;padding:10px 12px;border:1.5px solid var(--line);border-radius:10px;font:inherit;font-size:1rem;
  line-height:1.6;resize:vertical;background:var(--soft);color:var(--ink)}
.dlg-btns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.copy-msg{min-height:1.5em;margin:8px 0 0;font-weight:700;color:var(--green-dk)}
.dlg-in .ghost{width:100%;margin-top:10px}
.totop{position:fixed;right:12px;bottom:calc(12px + env(safe-area-inset-bottom));z-index:20;width:56px;height:56px;padding:0;
  border:2px solid var(--green);border-radius:50%;background:#fff;color:var(--green-dk);font:inherit;font-size:.875rem;font-weight:700;line-height:1.2;
  cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.18)}
.totop[hidden]{display:none}

/* X投稿文ページ */
.subtabs{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 14px}
.post{border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:12px 0;background:#fff}
.post h2{font-size:1.0625rem;margin:0 0 6px}
.post h2 small{font-weight:400;color:var(--sub);margin-left:6px}
.post pre{white-space:pre-wrap;word-break:break-all;font-family:inherit;font-size:1rem;line-height:1.65;margin:0 0 10px;background:var(--soft);
  border-radius:10px;padding:10px 12px}
.post .dlg-btns{margin-top:4px}
.post.gone{background:var(--soft)}
"""


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


COMMON_JS = SHARE_JS + r"""
// 日付は日本時間で数える（スマホの時計の設定によらず同じ結果にする）
const PC = (() => {
  const WD = '日月火水木金土';
  const jst = () => new Date(Date.now() + 9 * 3600e3);
  const today = () => jst().toISOString().slice(0, 10);
  const utc = s => { const p = s.slice(0, 10).split('-').map(Number); return Date.UTC(p[0], p[1] - 1, p[2]); };
  const days = s => Math.round((utc(s) - utc(today())) / 864e5);
  const dateJa = s => { const p = s.slice(0, 10).split('-').map(Number); return `${p[0]}年${p[1]}月${p[2]}日（${WD[new Date(utc(s)).getUTCDay()]}）`; };
  // 締切の表示。残り1〜3日（と当日）は赤、4〜7日はオレンジ。色だけに頼らないよう、文字でも伝える
  function due(dl, time){
    const n = days(dl);
    const closed = n < 0 || (n === 0 && !!time && jst().toISOString().slice(11, 16) > time);
    if (n < 0) return { n, cls: 'red', label: '募集は終了しました', closed };
    if (closed) return { n, cls: 'red', label: `本日${time}で受付終了`, closed };
    if (n === 0) return { n, cls: 'red', label: time ? `⚠ 今日が締切（${time}まで）` : '⚠ 今日が締切', closed };
    if (n <= 3) return { n, cls: 'red', label: `⚠ 締切間近：あと${n}日`, closed };
    if (n <= 7) return { n, cls: 'orange', label: `⏰ もうすぐ締切：あと${n}日`, closed };
    return { n, cls: '', label: `締切まで あと${n}日`, closed };
  }
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ss = {
    get(k){ try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v){ try { sessionStorage.setItem(k, v); } catch (e) {} },
  };
  // 上部ボタンの件数（締切日ごとの数から、今日以降のものだけ数え直す）
  function navCounts(C){
    const t = today();
    document.querySelectorAll('[data-count]').forEach(el => {
      const c = (C || {})[el.dataset.count];
      if (!c) return;
      el.textContent = Object.keys(c).reduce((s, d) => s + (d >= t ? c[d] : 0), 0);
      el.parentNode.hidden = false;
    });
  }
  // いちばん新しい件数（毎朝の更新の最後に作られる counts.json）で、上部ボタンの件数を数え直す
  const root = document.documentElement.dataset.root;
  if (root != null && window.fetch && location.protocol !== 'file:') {
    fetch(root + 'counts.json', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null)
      .then(j => { if (j) navCounts(j.counts); }).catch(() => {});
  }
  // Xで共有の小窓
  const dlg = document.getElementById('share-dialog');
  const box = document.getElementById('share-text');
  const msg = document.getElementById('share-msg');
  function openShare(text){
    box.value = text; box.scrollTop = 0; msg.textContent = '';
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
    document.getElementById('share-post').focus();
  }
  function closeShare(){ if (dlg.close) dlg.close(); else dlg.removeAttribute('open'); }
  // 文章のコピー。新しいしくみが使えないブラウザでは、昔ながらの方法でコピーする
  function copyText(text){
    const legacy = () => {
      const ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.top = '0'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, text.length);
      let ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
      ta.remove(); return ok;
    };
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, legacy);
    return Promise.resolve(legacy());
  }
  if (dlg) {
    document.getElementById('share-post').onclick = () => shareX(box.value);
    document.getElementById('share-copy').onclick = () => copyText(box.value).then(ok => {
      msg.textContent = ok ? 'コピーしました。Xアプリなどに貼り付けてください。' : 'コピーできませんでした。上の文章を長押し（または選択）してコピーしてください。';
      if (!ok) { box.focus(); box.select(); }
    });
    document.getElementById('share-close').onclick = closeShare;
    dlg.addEventListener('click', e => { if (e.target === dlg) closeShare(); });
  }
  // ページの上へ戻るボタン
  const top = document.getElementById('totop');
  if (top) {
    const f = () => { top.hidden = window.scrollY < 600; };
    window.addEventListener('scroll', f, { passive: true }); f();
    top.onclick = () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      const h = document.querySelector('h1'); if (h) { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); }
    };
  }
  return { today, days, dateJa, due, esc, ss, navCounts, openShare, copyText };
})();
"""


def asset_tags(root):
    """共通のデザイン（site.css）と動き（site.js）を読み込むタグ。中身が変わったときだけ ?v= が変わり、古いものが使われない。"""
    v = lambda text: hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return (f'<link rel="stylesheet" href="{root}assets/site.css?v={v(CSS)}">',
            f'<script src="{root}assets/site.js?v={v(COMMON_JS)}"></script>')


def write_shared(counts):
    """全ページ共通のデザイン・動き（docs/assets/）と、上部ボタンの件数（docs/counts.json）を書き出す。
    各版の build.py が毎回呼ぶ。最後に動いた版（市区町村版）の件数がいちばん新しい。"""
    assets = HERE / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "site.css").write_text(CSS, encoding="utf-8")
    (assets / "site.js").write_text(COMMON_JS, encoding="utf-8")
    (HERE / "docs" / "counts.json").write_text(json.dumps({"counts": counts}, ensure_ascii=False), encoding="utf-8")


# ---------- 一覧（検索）ページ ----------

LIST_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja" data-root="__ROOT__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<meta property="og:type" content="website">
<meta property="og:title" content="__OG_TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__URL__">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📣</text></svg>">
__ASSET_CSS__
</head>
<body>
__NAV__
<main id="main" class="wrap">
<section class="intro">
  <h1>__H1__</h1>
  <p class="lead"><b>パブコメとは？</b> 国や自治体がルールや計画を決める前に、広くみんなの意見を聞く仕組みです。</p>
  __GUIDE__
</section>

<form class="search" id="search" role="search" aria-label="案件をさがす">
  <label class="search-label" for="q">🔍 キーワードで探す</label>
  <div class="qrow">
    <input id="q" type="search" placeholder="__PLACEHOLDER__" autocomplete="off" enterkeyhint="search">
    <button type="submit" class="btn primary">検索</button>
  </div>
  <div class="frow">__FIELDS__
    <label class="field">並び順<select id="sort"><option value="deadline">締切が近い順</option><option value="new">新しく始まった順</option></select></label>
  </div>
  <fieldset class="chips"><legend>テーマ<span class="note">（案件名などの言葉で自動分類）</span></legend><div class="chip-row" id="themes"></div></fieldset>
  <fieldset class="chips"><legend>締切</legend><div class="chip-row" id="dues"></div></fieldset>
  <div class="srow"><span class="note">条件は組み合わせて使えます。このページのアドレスで、検索条件ごと共有できます。</span>
    <button type="button" class="btn outline" id="clear">条件をクリア</button></div>
</form>

<section id="results" aria-labelledby="result-h">
  <div class="result-head"><h2 id="result-h" tabindex="-1">募集中の案件</h2><p class="updated">データ最終更新：__UPDATED__</p></div>
  <p class="scope">__INTRO__</p>
  <p class="active" id="active"></p>
  <p class="related" id="related"></p>
  <div class="state" id="state" role="status">読み込み中です…</div>
  <noscript><p class="error">このページの検索にはJavaScriptが必要です。ブラウザの設定でJavaScriptを有効にするか、__NOSCRIPT__</p></noscript>
  <ul class="cards" id="list"></ul>
  <div class="more-wrap"><button type="button" class="btn outline" id="more" hidden>もっと見る</button></div>
</section>

__INFO__
</main>
<footer class="site-foot"><div class="wrap">__FOOTER__</div></footer>
__DIALOG__
<script id="data" type="application/json">__DATA__</script>
__ASSET_JS__
<script>
__LIST_JS__
</script>
</body>
</html>
"""


LIST_JS = r"""
(function(){
  const $ = s => document.querySelector(s);
  const esc = PC.esc;
  const list = $('#list'), stateEl = $('#state'), moreBtn = $('#more');
  let D;
  try { D = JSON.parse($('#data').textContent); }
  catch (e) {
    stateEl.innerHTML = '<p class="error">データを読み込めませんでした。時間をおいて、ページを再読み込みしてください。</p>';
    return;
  }
  PC.navCounts(D.counts);
  const LV = D.level, PAGE = 20;
  const norm = s => String(s || '').normalize('NFKC').toLowerCase();
  // 締切の日を過ぎた案件は出さない（日付で判定するので、締切当日の案件は1日中残る）
  const items = D.items.filter(i => PC.days(i.dl) >= 0);
  items.forEach(i => { i._s = norm([i.t, i.o, i.gist, (i.pts || []).join(' '), i.body, i.area, i.cat].join(' ')); });
  const byId = {}; items.forEach(i => { byId[i.id] = i; });
  const tagColor = {}; D.tags.forEach(t => { tagColor[t.name] = t.color; });
  const isNew = i => !!i.since && -PC.days(i.since) < D.newDays;
  const DUE = [['', 'すべて'], ['3', '3日以内'], ['7', '7日以内'], ['30', '30日以内']];
  const S = { q: '', theme: '', due: '', onlyNew: false, sort: 'deadline', ministry: '', pref: '', city: '' };
  let shown = PAGE;

  // ---- 地域・省庁の選択肢 ----
  const selMin = $('#ministry'), selPref = $('#pref'), selCity = $('#city'), selSort = $('#sort');
  const countBy = key => { const m = {}; items.forEach(i => { m[i[key]] = (m[i[key]] || 0) + 1; }); return m; };
  if (selMin) {
    const c = countBy('body');
    Object.keys(c).sort((a, b) => a.localeCompare(b, 'ja')).forEach(m => selMin.add(new Option(`${m}（${c[m]}件）`, m)));
  }
  if (selPref) {
    const c = countBy(LV === 'city' ? 'area' : 'body');
    D.regions.forEach(([group, names]) => {
      if (LV === 'city') { selPref.add(new Option(`${group}（${c[group] || 0}件）`, group)); return; }
      const g = document.createElement('optgroup'); g.label = group;
      names.forEach(n => g.appendChild(new Option(`${n}（${c[n] || 0}件）`, n)));
      selPref.appendChild(g);
    });
  }
  function fillCities(){
    if (!selCity) return;
    const c = countBy('body');
    while (selCity.children.length > 1) selCity.removeChild(selCity.lastChild);
    D.regions.filter(([p]) => !S.pref || p === S.pref).forEach(([p, names]) => {
      const g = document.createElement('optgroup'); g.label = p;
      names.forEach(n => g.appendChild(new Option(`${n}（${c[n] || 0}件）`, n)));
      selCity.appendChild(g);
    });
    setSel(selCity, S.city);
  }
  // 選択肢にない地域（収集の対象外・知らない名前）は、空にして全件を出すのではなく、「対象外」として選んだ状態にする
  function setSel(sel, v){
    sel.value = v;
    if (sel.value === v) return;
    sel.insertBefore(new Option(`${v}（収集の対象外）`, v), sel.children[1] || null);
    sel.value = v;
  }
  const PREFS = D.prefs || [];
  const cityPref = {};   // 市区町村版：市区 → 都道府県
  if (LV === 'city') D.regions.forEach(([p, names]) => names.forEach(n => { cityPref[n] = p; }));
  // アドレスの地域名を選択肢の名前にそろえる（全角半角のゆれや、「東京」「横浜」のような短い名前も受け付ける）
  const fixName = (v, names, ends) => {
    v = String(v || '').normalize('NFKC').trim();
    return !v || names.includes(v) ? v : (ends.map(e => v + e).find(n => names.includes(n)) || v);
  };
  // 指定された地域が、この版の収集対象外なら、その名前と理由を返す
  function outside(){
    const notPref = n => `都道府県の名前として「${esc(n)}」は見つかりませんでした。「東京都」のように、都道府県の名前で指定してください。`;
    if (LV === 'pref' && S.pref && !PREFS.includes(S.pref)) return { name: `「${S.pref}」`, why: notPref(S.pref) };
    if (LV !== 'city') return null;
    if (S.pref && !PREFS.includes(S.pref)) return { name: `「${S.pref}」`, why: notPref(S.pref) };
    if (S.city && !cityPref[S.city]) return { name: S.city, why: `市区町村版で集めているのは、政令指定都市・中核市・東京23区の計105か所だけです。${esc(S.city)}の意見募集は、公式ホームページでご確認ください。` };
    if (S.pref && !D.regions.some(([p]) => p === S.pref)) return { name: `${S.pref}の市区町村`, why: `${esc(S.pref)}には、市区町村版で集めている市区（政令指定都市・中核市・東京23区）がありません。` };
    return null;
  }

  // ---- テーマ・締切のボタン ----
  const themeBox = $('#themes'), dueBox = $('#dues');
  const chip = (label, attr, color) => `<button type="button" class="chip" ${attr} aria-pressed="false">` +
    (color ? `<i class="dot" style="--c:${esc(color)}" aria-hidden="true"></i>` : '') + `<span>${esc(label)}</span><span class="n"></span></button>`;
  themeBox.innerHTML = chip('すべて', 'data-theme=""') + D.tags.map(t => chip(t.name, `data-theme="${esc(t.name)}"`, t.color)).join('');
  dueBox.innerHTML = DUE.map(([v, l]) => chip(l, `data-due="${v}"`)).join('') + chip(`🆕 新着（${D.newDays}日以内）`, 'data-new="1"');

  // ---- 検索条件とアドレス（URL）----
  function readURL(){
    const p = new URLSearchParams(location.search);
    S.q = (p.get('q') || '').trim();
    S.theme = D.tags.some(t => t.name === p.get('theme')) ? p.get('theme') : '';
    S.due = ['3', '7', '30'].includes(p.get('due')) ? p.get('due') : '';
    S.onlyNew = p.get('new') === '1';
    S.sort = p.get('sort') === 'new' ? 'new' : 'deadline';
    S.ministry = p.get('ministry') || '';
    S.pref = fixName(p.get('pref'), PREFS, ['都', '道', '府', '県']);
    S.city = fixName(p.get('city'), Object.keys(cityPref), ['市', '区']);
    if (cityPref[S.city]) S.pref = cityPref[S.city];   // 都道府県は、指定された市区のある都道府県に合わせる
  }
  function sync(){
    $('#q').value = S.q; selSort.value = S.sort;
    if (selMin) { selMin.value = S.ministry; S.ministry = selMin.value; } else S.ministry = '';
    if (selPref) setSel(selPref, S.pref); else S.pref = '';
    if (selCity) fillCities(); else S.city = '';
  }
  function params(shared){
    const p = new URLSearchParams();
    if (S.q) p.set('q', S.q);
    if (S.theme) p.set('theme', S.theme);
    if (S.due) p.set('due', S.due);
    if (S.onlyNew) p.set('new', '1');
    if (S.sort === 'new') p.set('sort', 'new');
    if (!shared && S.ministry) p.set('ministry', S.ministry);
    if (S.pref) p.set('pref', S.pref);
    if (!shared && S.city) p.set('city', S.city);
    return p.toString();
  }
  function writeURL(){
    const qs = params(false);
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '')); } catch (e) {}
    PC.ss.set('pubcome:list:' + LV, location.href);
    // ほかの版（国・都道府県・市区町村）へ切り替えても、キーワードなどの条件を引き継ぐ
    const shared = params(true);
    document.querySelectorAll('.lv').forEach(a => {
      let q = shared;
      if (a.dataset.level === 'national' && S.pref) { const p = new URLSearchParams(q); p.delete('pref'); q = p.toString(); }
      a.href = a.dataset.base + (q ? '?' + q : '');
    });
  }

  // ---- しぼりこみ ----
  function test(i, W, skip){
    return (skip === 'theme' || !S.theme || i.tags.includes(S.theme)) &&
      (skip === 'due' || !S.due || PC.days(i.dl) <= +S.due) &&
      (skip === 'new' || !S.onlyNew || isNew(i)) &&
      (!S.ministry || i.body === S.ministry) &&
      (!S.pref || (LV === 'city' ? i.area : i.body) === S.pref) &&
      (!S.city || i.body === S.city) &&
      W.every(w => i._s.includes(w));
  }
  const byDeadline = (a, b) => a.dl.localeCompare(b.dl) || (a.time || '99').localeCompare(b.time || '99') || (b.since || '').localeCompare(a.since || '');
  const byNew = (a, b) => (b.since || '').localeCompare(a.since || '') || byDeadline(a, b);

  function card(i){
    const due = PC.due(i.dl, i.time);
    const where = LV === 'national' ? `国｜${esc(i.body)}` : LV === 'pref' ? `都道府県｜${esc(i.body)}` : `市区町村｜${esc(i.body)}（${esc(i.area)}）`;
    const pts = (i.pts || []).slice(0, 2);
    const rest = (i.pts || []).length - pts.length;
    const about = i.gist ? `<div class="about"><p class="lbl">どんな案？</p><p>${esc(i.gist)}</p>` +
      (pts.length ? `<p class="lbl">主な内容</p><ul>${pts.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '') +
      (rest > 0 ? `<p class="note">ほか${rest}点は「内容を見る」でご覧ください。</p>` : '') +
      `<p class="note">※公式の資料をもとにAIがまとめた要約です。</p></div>` : '';
    const how = LV === 'national'
      ? `<p class="facts"><b>提出先：</b>e-Gov（国の意見募集サイト）</p>`
      : (i.how && i.how.length ? `<p class="facts"><b>提出方法：</b>${i.how.map(esc).join('・')}<span class="note">（公式ページの記載から自動で抜き出し。ほかの方法がある場合もあります）</span></p>` : '');
    const themes = i.tags.length ? `<p class="themes"><span class="note">テーマ（自動分類）：</span>` +
      i.tags.map(t => `<span class="t"><i class="dot" style="--c:${esc(tagColor[t])}" aria-hidden="true"></i>${esc(t)}</span>`).join('') + '</p>' : '';
    const submit = !i.url ? '' : due.closed
      ? `<a class="btn primary" href="${esc(i.url)}" target="_blank" rel="noopener">公式ページを見る<small>受付時刻を過ぎています</small></a>`
      : `<a class="btn primary" href="${esc(i.url)}" target="_blank" rel="noopener">意見を提出する<small>${LV === 'national' ? 'e-Gov（国の公式ページ）へ' : '公式ページで提出方法を確認'}</small></a>`;
    return `<li class="card ${due.cls}">
      <div class="card-top"><span class="due ${due.cls}">${esc(due.label)}</span>${isNew(i) ? '<span class="new">🆕 新着</span>' : ''}</div>
      <p class="who">${where}${i.cat ? `<span class="cat">分野：${esc(i.cat)}</span>` : ''}</p>
      <h3><a href="${esc(i.page)}">${esc(i.t)}</a></h3>
      ${i.o ? `<p class="official">正式名称：${esc(i.o)}</p>` : ''}
      <p class="deadline">締切：${PC.dateJa(i.dl)}<span class="nw">${i.time ? esc(i.time) : ''}まで</span></p>
      ${about}${how}${themes}
      <div class="actions">
        <a class="btn primary" href="${esc(i.page)}">内容を見る</a>${submit}
        ${due.closed ? '' : `<button type="button" class="btn outline share" data-id="${esc(i.id)}">Xで共有</button>`}
      </div>
      <p class="src">出典：${LV === 'national' ? 'e-Govパブリック・コメント' : esc(i.body) + 'の公式ホームページ'}</p>
    </li>`;
  }

  function emptyHTML(){
    let official = '';
    if (LV === 'national') {
      official = `<p><a href="https://public-comment.e-gov.go.jp/" target="_blank" rel="noopener">e-Govパブリック・コメント（国の公式サイト）で探す</a></p>`;
    } else if (S.city || S.pref) {
      const hits = D.officials.filter(o => S.city ? o.name === S.city : (LV === 'pref' ? o.name === S.pref : o.pref === S.pref));
      if (hits.length) official = '<p>公式ページで直接確かめる：</p><p class="pgrid">' + hits.map(o =>
        `<a class="pchip" href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.name)}の意見募集ページ</a>`).join('') + '</p>';
    }
    return `<div class="empty"><p class="empty-h">条件に合う募集中の案件は見つかりませんでした</p>
      <ul><li>キーワードを短くする、別の言葉に変える</li><li>テーマ・締切・地域の条件を外す</li></ul>
      <p><button type="button" class="btn outline" data-clear>条件をクリア</button></p>${official}
      <p class="note">このサイトに載っていなくても、実際には募集している場合があります。</p></div>`;
  }
  function outsideHTML(out){
    return `<div class="empty"><p class="empty-h">${esc(out.name)}は収集の対象外です</p><p>${out.why}</p>
      <p><button type="button" class="btn outline" data-clear>条件をクリア</button></p></div>`;
  }

  function render(){
    const W = norm(S.q).split(/\s+/).filter(Boolean);
    const out = outside();
    const hits = out ? [] : items.filter(i => test(i, W)).sort(S.sort === 'new' ? byNew : byDeadline);
    themeBox.querySelectorAll('[data-theme]').forEach(b => {
      const t = b.dataset.theme;
      b.setAttribute('aria-pressed', String(t === S.theme));
      b.querySelector('.n').textContent = items.filter(i => test(i, W, 'theme') && (!t || i.tags.includes(t))).length + '件';
    });
    dueBox.querySelectorAll('button').forEach(b => {
      if (b.dataset.new) {
        b.setAttribute('aria-pressed', String(S.onlyNew));
        b.querySelector('.n').textContent = items.filter(i => test(i, W, 'new') && isNew(i)).length + '件';
      } else {
        const v = b.dataset.due;
        b.setAttribute('aria-pressed', String(v === S.due));
        b.querySelector('.n').textContent = items.filter(i => test(i, W, 'due') && (!v || PC.days(i.dl) <= +v)).length + '件';
      }
    });
    const conds = [];
    if (S.q) conds.push(`「${esc(S.q)}」`);
    if (S.pref) conds.push(esc(S.pref));
    if (S.city) conds.push(esc(S.city));
    if (S.ministry) conds.push(esc(S.ministry));
    if (S.theme) conds.push('テーマ：' + esc(S.theme));
    if (S.due) conds.push(`締切${S.due}日以内`);
    if (S.onlyNew) conds.push('新着のみ');
    $('#result-h').textContent = conds.length ? `${hits.length}件 見つかりました（募集中 ${items.length}件のうち）` : `募集中の案件 ${items.length}件`;
    $('#active').innerHTML = conds.length ? `<span>しぼりこみ中：${conds.join('・')}</span><button type="button" class="btn outline" data-clear>条件をクリア</button>` : '';
    let rel = '';
    if (LV === 'pref' && S.pref && (D.related || []).includes(S.pref)) rel = `<a href="../city/?pref=${encodeURIComponent(S.pref)}">${esc(S.pref)}の市区（政令市・中核市・23区）の案件も見る →</a>`;
    if (LV === 'city' && PREFS.includes(S.pref)) rel = `<a href="../pref/?pref=${encodeURIComponent(S.pref)}">${esc(S.pref)}（都道府県）の案件も見る →</a>`;
    $('#related').innerHTML = rel;
    if (!hits.length) { stateEl.innerHTML = out ? outsideHTML(out) : emptyHTML(); list.innerHTML = ''; moreBtn.hidden = true; return; }
    stateEl.innerHTML = '';
    list.innerHTML = hits.slice(0, shown).map(card).join('');
    const left = hits.length - Math.min(shown, hits.length);
    moreBtn.hidden = left <= 0;
    moreBtn.textContent = `もっと見る（あと${left}件）`;
  }
  function update(){ shown = PAGE; render(); writeURL(); }
  function clearAll(){
    Object.assign(S, { q: '', theme: '', due: '', onlyNew: false, sort: 'deadline', ministry: '', pref: '', city: '' });
    sync(); update(); $('#q').focus();
  }

  // ---- 操作 ----
  const q = $('#q'); let timer;
  q.addEventListener('input', e => {
    if (e.isComposing) return;
    clearTimeout(timer); timer = setTimeout(() => { S.q = q.value.trim(); update(); }, 250);
  });
  q.addEventListener('compositionend', () => { S.q = q.value.trim(); update(); });
  $('#search').addEventListener('submit', e => {
    e.preventDefault(); clearTimeout(timer); S.q = q.value.trim(); update(); q.blur();
    const h = $('#result-h'); h.scrollIntoView({ behavior: 'smooth', block: 'start' }); h.focus({ preventScroll: true });
  });
  themeBox.addEventListener('click', e => { const b = e.target.closest('[data-theme]'); if (b) { S.theme = b.dataset.theme; update(); } });
  dueBox.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.new) S.onlyNew = !S.onlyNew; else S.due = b.dataset.due;
    update();
  });
  selSort.onchange = () => { S.sort = selSort.value; update(); };
  if (selMin) selMin.onchange = () => { S.ministry = selMin.value; update(); };
  if (selPref) selPref.onchange = () => {
    S.pref = selPref.value;
    if (S.pref && cityPref[S.city] !== S.pref) S.city = '';   // ほかの都道府県の市区の指定は外す
    fillCities(); update();
  };
  if (selCity) selCity.onchange = () => { S.city = selCity.value; update(); };
  $('#clear').onclick = clearAll;
  document.addEventListener('click', e => { if (e.target.closest('[data-clear]')) clearAll(); });
  list.addEventListener('click', e => {
    const b = e.target.closest('button.share'); if (!b) return;
    const i = byId[b.dataset.id]; if (i) PC.openShare(i.share);
  });
  moreBtn.onclick = () => {
    const first = shown; shown += PAGE; render();
    const a = list.children[first] && list.children[first].querySelector('h3 a'); if (a) a.focus();
  };

  readURL(); sync(); render(); writeURL();
})();
"""


def list_page(*, level, title, og_title, desc, url, h1, intro, placeholder, fields, info, footer, updated, payload, noscript):
    """一覧（検索）ページの HTML を作る。"""
    root = "" if level == "national" else "../"
    page = LIST_TEMPLATE
    for key, value in {
        "__ROOT__": root, "__ASSET_CSS__": asset_tags(root)[0], "__ASSET_JS__": asset_tags(root)[1],
        "__NAV__": nav_html(level, root, payload["counts"]),
        "__GUIDE__": GUIDE_HTML,
        "__DIALOG__": SHARE_DIALOG,
        "__TITLE__": esc(title), "__OG_TITLE__": esc(og_title), "__DESC__": esc(desc), "__URL__": esc(url),
        "__H1__": esc(h1), "__INTRO__": intro, "__PLACEHOLDER__": esc(placeholder), "__FIELDS__": fields,
        "__INFO__": info, "__FOOTER__": footer, "__UPDATED__": esc(updated_ja(updated)), "__NOSCRIPT__": noscript,
        "__LIST_JS__": LIST_JS,
        "__DATA__": json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(key, value)
    return page


def area_list_html(regions, officials, counts_by_name, label):
    """都道府県・市区町村ごとの公式ページの一覧（件数つき）。今日ページを開けなかったところは点線で、文字でも示す。"""
    by_name = {o["name"]: o for o in officials}
    blocks = []
    for group, names in regions:
        chips = []
        for n in names:
            o = by_name.get(n, {})
            c = counts_by_name.get(n, 0)
            cls = "pchip" + ("" if c else " zero") + (" err" if o.get("error") else "")
            err = '<span class="e">今日は取得できず</span>' if o.get("error") else ""
            href = esc(o.get("url")) if o.get("url") else "#"
            chips.append(f'<a class="{cls}" href="{href}" target="_blank" rel="noopener">{esc(n)}<span class="n">{c}件</span>{err}</a>')
        blocks.append(f'<div class="region"><b>{esc(group)}</b><div class="pgrid">{"".join(chips)}</div></div>')
    return (f'<details class="areas"><summary>{esc(label)}ごとの公式ページ（件数はこのサイトで見つけた募集中の数）</summary>'
            f'{"".join(blocks)}</details>')


# ---------- 案件ページ ----------

DETAIL_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja" data-root="__ROOT__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__｜パブコメ掲示板</title>
<meta name="description" content="__DESC__">
<meta property="og:type" content="article">
<meta property="og:title" content="__OG_TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:url" content="__PAGE_URL__">
<meta name="twitter:card" content="summary">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📣</text></svg>">
__ASSET_CSS__
</head>
<body>
__NAV__
<main id="main" class="wrap detail">
<a class="back" id="back" href="../">← <span>__BACK_LABEL__</span></a>
<p class="who">__WHO__</p>
<h1>__TITLE__</h1>
__OFFICIAL__
<div class="dl-box" id="dl-box"><span class="due" id="due">__DUE_TEXT__</span>
  <span class="dl-main"><small>意見の締切</small>__DEADLINE__</span></div>
<p class="closed" id="closed" hidden>この案件の受付は終了しました。新しく意見を出すことはできません。</p>
<div class="big-actions" id="actions">
  __SUBMIT__
  <button type="button" class="btn outline" id="share">Xで共有</button>
</div>
__THEMES__
__SUMMARY__
__HOWTO__
<section class="box" aria-labelledby="files-h"><h2 id="files-h">📚 資料（公式）</h2>__FILES__</section>
__EXTRA__
<section class="box" aria-labelledby="contact-h"><h2 id="contact-h">☎️ 問い合わせ先</h2><p>__CONTACT__</p></section>
<section class="box" aria-labelledby="src-h"><h2 id="src-h">ℹ️ この情報について</h2>__SOURCE__</section>
</main>
<footer class="site-foot"><div class="wrap detail"><p>パブコメ掲示板は、国や自治体の意見募集を見つけやすくまとめた個人のサイトです。正式な内容は、必ず各公式ページでご確認ください。</p></div></footer>
__DIALOG__
<script id="meta" type="application/json">__META__</script>
__ASSET_JS__
<script>
(function(){
  const M = JSON.parse(document.getElementById('meta').textContent);
  const due = PC.due(M.dl, M.time);
  const el = document.getElementById('due');
  el.textContent = due.label; el.className = 'due ' + due.cls;
  document.getElementById('dl-box').className = 'dl-box ' + due.cls;
  const share = document.getElementById('share');
  if (due.closed) {
    document.getElementById('closed').hidden = false;
    share.remove();
    const s = document.getElementById('submit');
    if (s) s.innerHTML = '公式ページを見る<small>受付は終了しています</small>';
  } else {
    share.onclick = () => PC.openShare(M.share);
  }
  // 「検索結果に戻る」：一覧で最後に使った検索条件のページへ戻る（一覧から来たときは、見ていた位置にも戻る）
  const saved = PC.ss.get('pubcome:list:' + M.level);
  const back = document.getElementById('back');
  if (saved) { back.href = saved; back.querySelector('span').textContent = '検索結果に戻る'; }
  back.addEventListener('click', e => {
    if (saved && document.referrer && document.referrer.split('#')[0] === saved.split('#')[0] && history.length > 1) {
      e.preventDefault(); history.back();
    }
  });
})();
</script>
</body>
</html>
"""


def detail_page(*, level, root, title, og_title, desc, page_url, who, official, deadline_text, dl, time,
                submit_url, submit_note, themes, summary, howto, files, extra, contact, source, share):
    """案件ごとのページ（スマホ用まとめ）の HTML を作る。"""
    submit = ""
    if submit_url:
        submit = (f'<a class="btn primary" id="submit" href="{esc(submit_url)}" target="_blank" rel="noopener">'
                  f'意見を提出する<small>{esc(submit_note)}</small></a>')
    meta = {"level": level, "dl": dl, "time": time, "share": share}
    page = DETAIL_TEMPLATE
    for key, value in {
        "__ROOT__": root, "__ASSET_CSS__": asset_tags(root)[0], "__ASSET_JS__": asset_tags(root)[1],
        "__NAV__": nav_html(level, root, None),
        "__DIALOG__": SHARE_DIALOG,
        "__TITLE__": esc(title), "__OG_TITLE__": esc(og_title), "__DESC__": esc(desc), "__PAGE_URL__": esc(page_url),
        "__BACK_LABEL__": f"一覧を見る（{LEVEL_NAME[level]}の案件）",
        "__WHO__": who, "__OFFICIAL__": official,
        "__DUE_TEXT__": "締切", "__DEADLINE__": deadline_text,
        "__SUBMIT__": submit, "__THEMES__": themes, "__SUMMARY__": summary, "__HOWTO__": howto,
        "__FILES__": files, "__EXTRA__": extra, "__CONTACT__": contact, "__SOURCE__": source,
        "__META__": json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(key, value)
    return page


def themes_line(tags, color_of):
    """案件ページのテーマ表示（自動分類であることを明記）。"""
    if not tags:
        return ""
    chips = "".join(f'<span class="t"><i class="dot" style="--c:{esc(color_of[t])}" aria-hidden="true"></i>{esc(t)}</span>'
                    for t in tags)
    return f'<p class="themes"><span class="note">テーマ（案件名などの言葉で自動分類）：</span>{chips}</p>'


def official_line(display, official):
    """わかりやすい名前と正式名称が違うときだけ、正式名称を出す。"""
    if not official or official == display:
        return ""
    return f'<p class="official">正式名称：{esc(official)}</p>'


# ---------- X投稿文ページ ----------

POSTS_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja" data-root="__ROOT__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>X投稿文（__AREA__）｜パブコメ掲示板</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📣</text></svg>">
__ASSET_CSS__
</head>
<body>
__NAV__
<main id="main" class="wrap detail">
<section class="intro">
<h1>X投稿文（__AREA__の案件）</h1>
<div class="subtabs" role="group" aria-label="投稿文の種類">__SUBTABS__</div>
<p class="lead">__UPDATED__ 更新。「Xで投稿する」を押すと、文章が入った状態でXの投稿画面が開きます。内容を確かめてから投稿してください。</p>
<p class="note">Xの画面が開かないとき（アプリの中のブラウザなど）は、「文章をコピー」を押してXアプリに貼り付けてください。締切が過ぎた案件の投稿文は、自動で隠します。</p>
</section>
__CARDS__
</main>
<footer class="site-foot"><div class="wrap detail"><p>投稿文は毎朝自動で作り直しています。</p></div></footer>
__DIALOG__
__ASSET_JS__
<script>
(function(){
  PC.navCounts(__COUNTS__);
  document.querySelectorAll('.post[data-dl]').forEach(sec => {
    if (PC.days(sec.dataset.dl) < 0) {
      sec.classList.add('gone');
      sec.querySelector('pre').hidden = true;
      sec.querySelector('.dlg-btns').hidden = true;
      sec.insertAdjacentHTML('beforeend', '<p class="note">締切が過ぎたため、この投稿文は隠しています（次の更新で作り直されます）。</p>');
    }
  });
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    const text = b.closest('.post').querySelector('pre').textContent;
    if (b.dataset.act === 'post') { shareX(text); return; }
    PC.copyText(text).then(ok => {
      b.textContent = ok ? 'コピーしました' : 'コピーできませんでした（文章を長押ししてコピー）';
      setTimeout(() => { b.textContent = '文章をコピー'; }, 2500);
    });
  });
})();
</script>
</body>
</html>
"""


def posts_page(posts, *, level, updated, counts, length, limit):
    """X投稿文ページの HTML を作る。posts は (見出し, 本文, 関係する締切日 'YYYY-MM-DD' または '') のリスト。"""
    root = "" if level == "national" else "../"
    cards = []
    for label, body, dl in posts:
        attr = f' data-dl="{esc(dl)}"' if dl else ""
        cards.append(
            f'<section class="post"{attr}><h2>{esc(label)}<small>{length(body)}/{limit}字</small></h2>'
            f'<pre>{esc(body)}</pre>'
            '<div class="dlg-btns"><button type="button" class="btn primary" data-act="post">Xで投稿する</button>'
            '<button type="button" class="btn outline" data-act="copy">文章をコピー</button></div></section>')
    tabs = []
    for key, name, path, _ in LEVELS:
        cur = ' aria-current="page"' if key == level else ""
        tabs.append(f'<a class="xlink" href="{root}{path}posts.html"{cur}>{name}</a>')
    page = POSTS_TEMPLATE
    for key, value in {
        "__ROOT__": root, "__ASSET_CSS__": asset_tags(root)[0], "__ASSET_JS__": asset_tags(root)[1],
        "__NAV__": nav_html(level, root, counts, posts=True),
        "__DIALOG__": SHARE_DIALOG,
        "__AREA__": LEVEL_NAME[level],
        "__SUBTABS__": "".join(tabs),
        "__UPDATED__": esc(updated_ja(updated)),
        "__CARDS__": "\n".join(cards) or '<p class="state">今日の投稿文はありません。</p>',
        "__COUNTS__": json.dumps(counts, ensure_ascii=False),
    }.items():
        page = page.replace(key, value)
    return page

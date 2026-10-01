"""data.json から X 投稿文を作る。

- posts.txt        … 投稿文をテキストで保存（コピー用）
- docs/posts.html  … スマホで開いて「Xで投稿」を押すだけで投稿画面が開くページ

使い方:  python post.py
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build import SHARE_JS, load_plain_titles, share_text

HERE = Path(__file__).parent
JST = timezone(timedelta(hours=9))
LIMIT = 140        # 投稿文の上限（リンク込みで140字）
URL_WEIGHT = 23    # X ではリンクはどんな長さでも23字として数えられる
CLOSING_DAYS = 3   # 「締切間近」とみなす日数
NEW_DAYS = 3       # 公示から何日以内を「新着」とするか


def length(text):
    """リンクを23字として、投稿文の文字数を数える。"""
    urls = re.findall(r"https?://\S+", text)
    rest = re.sub(r"https?://\S+", "", text)
    return len(urls) * URL_WEIGHT + len(rest)


def mmdd(iso):
    d = datetime.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def main():
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    tag_defs = json.loads((HERE / "keywords.json").read_text(encoding="utf-8"))["tags"]
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    tag_of = {t["name"]: t for t in tag_defs}
    site, main_tag = config["site_url"], config["main_hashtag"]

    now = datetime.now(JST)
    excluded = json.loads((HERE / "exclude.json").read_text(encoding="utf-8")) if (HERE / "exclude.json").exists() else {}
    open_items = [it for it in data["items"] if it["deadline"] and it["deadline"] >= now.isoformat()
                  and it["id"] not in excluded]
    # 締切日と今日の「日付」の差（今日が締切なら0）。一覧ページと同じ数え方
    days_left = lambda it: (datetime.fromisoformat(it["deadline"]).date() - now.date()).days
    new_since = (now - timedelta(days=NEW_DAYS)).isoformat()
    is_new = lambda it: (it.get("published") or "") >= new_since
    plain = load_plain_titles()
    for it in open_items:
        if it["id"] in plain:
            it["plain"] = plain[it["id"]]
    focus = [it for it in open_items if it["tags"]]

    posts = []  # (見出し, 本文)

    # 1) 毎日のまとめ
    posts.append(("今日のまとめ", (
        f"いま国が「みんなの意見を聞かせて」と募集しているテーマが{len(open_items)}件あります📣\n"
        f"子育て・年金・外国人のことなど、暮らしに身近な話も。\n"
        f"ひとことからでも送れます🙆\n"
        f"{site}\n{main_tag}"
    )))

    # 2) 注目テーマの新着（1件ごとの定型文）
    hashtag_of = {t["name"]: t["hashtag"] for t in tag_defs}
    for it in sorted([it for it in focus if is_new(it)], key=lambda it: it["published"], reverse=True):
        posts.append((f"新着｜{'・'.join(it['tags'])}", share_text(it, main_tag, hashtag_of, site)))

    # 3) 注目テーマの締切間近（1件ごとの定型文）
    for it in sorted([it for it in focus if days_left(it) <= CLOSING_DAYS], key=lambda it: it["deadline"]):
        posts.append((f"締切間近｜{'・'.join(it['tags'])}", share_text(it, main_tag, hashtag_of, site)))

    # 4) 注目テーマごとの紹介
    for t in tag_defs:
        its = [it for it in open_items if t["name"] in it["tags"]]
        if not its:
            continue
        posts.append((f"テーマ紹介｜{t['name']}", (
            f"{t['emoji']}{t['friendly']}について、国が意見を募集している案が{len(its)}件あります。\n"
            f"いちばん近い締切は{mmdd(its[0]['deadline'])}。\n"
            f"どんな案か、ちょっとのぞいてみませんか？\n"
            f"{site}\n{main_tag} {t['hashtag']}"
        )))

    write_outputs(posts, data["updated"], config)


def write_outputs(posts, updated, config):
    txt = [f"X投稿文（{updated[:16].replace('T', ' ')} 更新）", ""]
    for i, (label, body) in enumerate(posts, 1):
        txt += [f"===== {i}. {label}（{length(body)}/{LIMIT}字） =====", body, ""]
    (HERE / "posts.txt").write_text("\n".join(txt), encoding="utf-8")

    cards = []
    for label, body in posts:
        cards.append(
            f'<section><h2>{html.escape(label)} <small>{length(body)}/{LIMIT}字</small></h2>'
            f'<pre>{html.escape(body)}</pre>'
            f'<div class="btns"><button type="button" class="x" onclick="post(this)">𝕏アプリで投稿</button>'
            f'<button type="button" onclick="copy(this)">コピー</button></div></section>'
        )
    page = POSTS_TEMPLATE.replace("__UPDATED__", html.escape(updated[:16].replace("T", " ")))
    page = page.replace("<h1>X投稿文</h1>", '<h1>X投稿文</h1>\n<p>投稿文ページ：<b>🏛️ 国</b> ／ '
                        '<a href="pref/posts.html">🗾 都道府県</a> ／ <a href="city/posts.html">🏙️ 市区町村</a></p>')
    page = page.replace("__SHARE_JS__", SHARE_JS)
    page = page.replace("__SITE_NAME__", html.escape(config["site_name"])).replace("__CARDS__", "\n".join(cards))
    (HERE / "docs").mkdir(exist_ok=True)
    (HERE / "docs" / "posts.html").write_text(page, encoding="utf-8")
    print(f"posts.txt と docs/posts.html を作りました（投稿文 {len(posts)} 本）")


POSTS_TEMPLATE = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>X投稿文｜__SITE_NAME__</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1c1b19;--sub:#5f5c56;--line:#e3e0d9}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#16161a;--card:#202026;--ink:#ecebe8;--sub:#a8a59f;--line:#34343c}}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Hiragino Sans","Noto Sans JP","Meiryo",sans-serif}
.wrap{max-width:640px;margin:0 auto;padding:16px}
h1{font-size:1.3rem;margin:8px 0 2px}
p{color:var(--sub);font-size:.88rem;margin:0 0 12px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:12px 0}
h2{font-size:.95rem;margin:0 0 6px}
h2 small{color:var(--sub);font-weight:400}
pre{white-space:pre-wrap;word-break:break-all;font-family:inherit;font-size:.9rem;margin:0 0 10px;line-height:1.6}
.btns{display:flex;gap:8px}
.btns a,.btns button{flex:1;text-align:center;padding:9px;border-radius:8px;font-size:.9rem;font-weight:700;
  text-decoration:none;border:1px solid var(--line);font-family:inherit;cursor:pointer}
.x{background:var(--ink);color:var(--bg)}
.tip{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
button{background:var(--card);color:var(--ink)}
</style></head>
<body><div class="wrap">
<h1>X投稿文</h1>
<p>__UPDATED__ 更新。「𝕏アプリで投稿」を押すと、文章が入った状態でXアプリの投稿画面が開きます。内容を確認してから投稿してください。</p>
<p class="tip">💡 GitHubアプリなどの中で開くと、Xアプリに切り替わらないことがあります。うまくいかないときは、このページを <b>Safari や Chrome で開き</b>、「ホーム画面に追加」しておくと次から便利です。</p>
__CARDS__
</div>
<script>
__SHARE_JS__
function post(btn){ shareX(btn.closest('section').querySelector('pre').textContent); }
function copy(btn){
  const text = btn.closest('section').querySelector('pre').textContent;
  navigator.clipboard.writeText(text).then(() => { btn.textContent = 'コピーしました'; setTimeout(() => btn.textContent = 'コピー', 1500); });
}
</script>
</body></html>
"""

if __name__ == "__main__":
    main()

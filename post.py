"""data.json から X 投稿文を作る。

- posts.txt        … 投稿文をテキストで保存（コピー用）
- docs/posts.html  … スマホで開いて「Xで投稿」を押すだけで投稿画面が開くページ

使い方:  python post.py
"""
import html
import json
import math
import re
import unicodedata
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build import short_title

HERE = Path(__file__).parent
JST = timezone(timedelta(hours=9))
X_LIMIT = 280      # X の上限（日本語は1文字=2として数える）
URL_WEIGHT = 23    # URL はどんな長さでも23として数えられる
CLOSING_DAYS = 3   # 「締切間近」とみなす日数
NEW_DAYS = 3       # 公示から何日以内を「新着」とするか


def x_length(text):
    """X の数え方で文字数を数える（URL は23、全角は2、半角は1）。"""
    urls = re.findall(r"https?://\S+", text)
    rest = re.sub(r"https?://\S+", "", text)
    return len(urls) * URL_WEIGHT + sum(2 if unicodedata.east_asian_width(c) in "WFA" else 1 for c in rest)


def fit(head, title, tail):
    """投稿が上限を超えるときは案件名を短くしてはみ出さないようにする。"""
    while x_length(head + title + tail) > X_LIMIT and len(title) > 10:
        title = title[:-2].rstrip("…") + "…"
    return head + title + tail


def mmdd(iso):
    d = datetime.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def main():
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    tag_defs = json.loads((HERE / "keywords.json").read_text(encoding="utf-8"))["tags"]
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    hashtag_of = {t["name"]: t["hashtag"] for t in tag_defs}
    site, main_tag = config["site_url"], config["main_hashtag"]

    now = datetime.now(JST)
    open_items = [it for it in data["items"] if it["deadline"] and it["deadline"] >= now.isoformat()]
    # 一覧ページと同じく「あと◯日」は切り上げで数える
    days_left = lambda it: math.ceil((datetime.fromisoformat(it["deadline"]) - now).total_seconds() / 86400)
    new_since = (now - timedelta(days=NEW_DAYS)).isoformat()
    is_new = lambda it: (it.get("published") or "") >= new_since
    focus = [it for it in open_items if it["tags"]]

    posts = []  # (見出し, 本文)

    # 1) 毎日のまとめ
    soon = sum(1 for it in open_items if days_left(it) <= config["urgent_days"])
    counts = "・".join(
        f"{t['name']}{sum(1 for it in open_items if t['name'] in it['tags'])}"
        for t in tag_defs
    )
    posts.append(("今日のまとめ", (
        f"📣国が意見を募集中のパブコメ {len(open_items)}件\n"
        f"うち{config['urgent_days']}日以内に締切 {soon}件\n\n"
        f"注目テーマ：{counts}\n\n"
        f"締切が近い順に一覧できます👇\n{site}\n{main_tag}"
    )))

    # 2) 注目テーマの新着
    for it in sorted([it for it in focus if is_new(it)], key=lambda it: it["published"], reverse=True):
        tags = " ".join(hashtag_of[t] for t in it["tags"])
        posts.append((f"新着｜{'・'.join(it['tags'])}", fit(
            f"🆕【意見募集スタート】{it['tags'][0]}\n\n",
            short_title(it["title"]),
            f"\n（{it['ministry']}・{mmdd(it['deadline'])}締切）\n\n意見はこちら👇\n{it['url']}\n{main_tag} {tags}",
        )))

    # 3) 注目テーマの締切間近
    for it in sorted([it for it in focus if days_left(it) <= CLOSING_DAYS], key=lambda it: it["deadline"]):
        d = days_left(it)
        when = "本日締切" if d <= 0 else f"締切まであと{d}日"
        tags = " ".join(hashtag_of[t] for t in it["tags"])
        posts.append((f"締切間近｜{'・'.join(it['tags'])}", fit(
            f"⏰【{when}・{mmdd(it['deadline'])}】{it['tags'][0]}\n\n",
            short_title(it["title"]),
            f"\n（{it['ministry']}）\n\n意見はこちら👇\n{it['url']}\n{main_tag} {tags}",
        )))

    # 4) 注目テーマごとの一覧（募集中のものを3件まで）
    for t in tag_defs:
        its = [it for it in open_items if t["name"] in it["tags"]][:3]
        if not its:
            continue
        lines = "\n".join(f"・{mmdd(it['deadline'])}締切 {short_title(it['title'], 38)}" for it in its)
        more = sum(1 for it in open_items if t["name"] in it["tags"]) - len(its)
        body = f"【{t['name']}】に関するパブコメ募集中\n\n{lines}\n" + (f"ほか{more}件\n" if more > 0 else "")
        body += f"\n一覧👇\n{site}\n{main_tag} {t['hashtag']}"
        while x_length(body) > X_LIMIT and len(its) > 1:
            its = its[:-1]
            lines = "\n".join(f"・{mmdd(it['deadline'])}締切 {short_title(it['title'], 38)}" for it in its)
            more = sum(1 for it in open_items if t["name"] in it["tags"]) - len(its)
            body = f"【{t['name']}】に関するパブコメ募集中\n\n{lines}\nほか{more}件\n\n一覧👇\n{site}\n{main_tag} {t['hashtag']}"
        posts.append((f"テーマ一覧｜{t['name']}", body))

    write_outputs(posts, data["updated"], config)


def write_outputs(posts, updated, config):
    txt = [f"X投稿文（{updated[:16].replace('T', ' ')} 更新）", ""]
    for i, (label, body) in enumerate(posts, 1):
        txt += [f"===== {i}. {label}（{x_length(body)}/{X_LIMIT}） =====", body, ""]
    (HERE / "posts.txt").write_text("\n".join(txt), encoding="utf-8")

    cards = []
    for label, body in posts:
        intent = "https://x.com/intent/post?text=" + urllib.parse.quote(body)
        cards.append(
            f'<section><h2>{html.escape(label)} <small>{x_length(body)}/{X_LIMIT}</small></h2>'
            f'<pre>{html.escape(body)}</pre>'
            f'<div class="btns"><a class="x" href="{html.escape(intent)}" target="_blank" rel="noopener">𝕏で投稿する</a>'
            f'<button type="button" onclick="copy(this)">コピー</button></div></section>'
        )
    page = POSTS_TEMPLATE.replace("__UPDATED__", html.escape(updated[:16].replace("T", " ")))
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
button{background:var(--card);color:var(--ink)}
</style></head>
<body><div class="wrap">
<h1>X投稿文</h1>
<p>__UPDATED__ 更新。「𝕏で投稿する」を押すと、文章が入った状態でXの投稿画面が開きます。内容を確認してから投稿してください。</p>
__CARDS__
</div>
<script>
function copy(btn){
  const text = btn.closest('section').querySelector('pre').textContent;
  navigator.clipboard.writeText(text).then(() => { btn.textContent = 'コピーしました'; setTimeout(() => btn.textContent = 'コピー', 1500); });
}
</script>
</body></html>
"""

if __name__ == "__main__":
    main()

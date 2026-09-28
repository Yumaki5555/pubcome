"""data.json から X 投稿文のページ（../docs/pref/posts.html）を作る。国版の post.py の都道府県版。
市区町村版（../市区町村レベル/post.py）も、config.json で言葉と置き場所を差し替えてこの仕組みを使う。

使い方:  python 都道府県レベル/post.py（ふだんは build.py が一緒に作るので不要）
"""
import html
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from post import POSTS_TEMPLATE, LIMIT, length, mmdd  # 国版と共通の部品を使う
from build import SHARE_JS

spec = importlib.util.spec_from_file_location("pref_build", HERE / "build.py")
pref_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pref_build)

JST = timezone(timedelta(hours=9))
CLOSING_DAYS = 3   # 「締切間近」とみなす日数
NEW_DAYS = 3       # 募集開始（または見つけた日）から何日以内を「新着」とするか


def main(base=HERE):
    config = json.loads((base / "config.json").read_text(encoding="utf-8"))
    pref_build.BASE = base
    tag_defs = json.loads((HERE.parent / "keywords.json").read_text(encoding="utf-8"))["tags"]
    data = json.loads((base / "data.json").read_text(encoding="utf-8"))
    site, main_tag = config["site_url"], config["main_hashtag"]
    area = config.get("area_label", "都道府県")
    hashtag_of = {t["name"]: t["hashtag"] for t in tag_defs}

    today = datetime.now(JST).date()
    items = [it for it in data["items"] if it["deadline"] >= today.isoformat()]
    plain = pref_build.load_plain_titles()
    for it in items:
        if it["id"] in plain:
            it["plain"] = plain[it["id"]]
    days_left = lambda it: (datetime.fromisoformat(it["deadline"]).date() - today).days
    new_since = (today - timedelta(days=NEW_DAYS)).isoformat()
    is_new = lambda it: (it.get("start") or it.get("first_seen") or "") >= new_since
    share = lambda it: pref_build.share_text(it, main_tag, hashtag_of, site)

    posts = []  # (見出し, 本文)

    # 1) 毎日のまとめ
    n_area = len({it["pref"] for it in items})
    posts.append(("今日のまとめ", (
        f"いま{n_area}の{area}が「みんなの意見を聞かせて」と募集しているテーマが{len(items)}件あります📣\n"
        f"子育て・福祉・まちづくりなど、暮らしに身近な話も。\n"
        f"ひとことからでも送れます🙆\n"
        f"{site}\n{main_tag}"
    )))

    # 2) 新着（1件ごとの定型文）
    for it in sorted([it for it in items if is_new(it)], key=lambda it: it.get("start") or "", reverse=True):
        label = "・".join(it["tags"]) or it["pref"]
        posts.append((f"新着｜{label}", share(it)))

    # 3) 締切間近（1件ごとの定型文）
    for it in sorted([it for it in items if days_left(it) <= CLOSING_DAYS], key=lambda it: it["deadline"]):
        label = "・".join(it["tags"]) or it["pref"]
        posts.append((f"締切間近｜{label}", share(it)))

    # 4) 注目テーマごとの紹介
    for t in tag_defs:
        its = [it for it in items if t["name"] in it["tags"]]
        if not its:
            continue
        names = "・".join(dict.fromkeys(it["pref"] for it in its))
        if len(names) > 20:
            names = names[:19] + "…"
        posts.append((f"テーマ紹介｜{t['name']}", (
            f"{t['emoji']}{t['friendly']}について、{area}が意見を募集している案が{len(its)}件あります（{names}）。\n"
            f"いちばん近い締切は{mmdd(its[0]['deadline'])}。\n"
            f"住んでいるまちの話か、のぞいてみませんか？\n"
            f"{site}\n{main_tag} {t['hashtag']}"
        )))

    cards = []
    for label, body in posts:
        cards.append(
            f'<section><h2>{html.escape(label)} <small>{length(body)}/{LIMIT}字</small></h2>'
            f'<pre>{html.escape(body)}</pre>'
            f'<div class="btns"><button type="button" class="x" onclick="post(this)">𝕏アプリで投稿</button>'
            f'<button type="button" onclick="copy(this)">コピー</button></div></section>'
        )
    updated = data["updated"][:16].replace("T", " ")
    page = POSTS_TEMPLATE.replace("__UPDATED__", html.escape(updated))
    page = page.replace("<h1>X投稿文</h1>", f"<h1>X投稿文（{html.escape(area)}版）</h1>\n{NAV}")
    page = page.replace("__SHARE_JS__", SHARE_JS)
    page = page.replace("__SITE_NAME__", html.escape(config["site_name"])).replace("__CARDS__", "\n".join(cards))
    out = HERE.parent / "docs" / config.get("out_dir", "pref")
    out.mkdir(parents=True, exist_ok=True)
    (out / "posts.html").write_text(page, encoding="utf-8")
    print(f"docs/{config.get('out_dir', 'pref')}/posts.html を作りました（投稿文 {len(posts)} 本）")


# 国・都道府県・市区町村の投稿文ページを行き来するリンク
NAV = ('<p>投稿文ページ：<a href="../posts.html">🏛️ 国</a> ／ <a href="../pref/posts.html">🗾 都道府県</a>'
       ' ／ <a href="../city/posts.html">🏙️ 市区町村</a></p>')


if __name__ == "__main__":
    main()

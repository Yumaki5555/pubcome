"""data.json から X 投稿文を作る。

- posts.txt        … 投稿文をテキストで保存（コピー用）
- docs/posts.html  … スマホで開いて「Xで投稿」を押すだけで投稿画面が開くページ

使い方:  python post.py
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ui
from build import load_plain_titles, share_text
from ui import effective_deadline

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
    # 締切日と今日の「日付」の差（今日が締切なら0）。一覧ページと同じ数え方（0時締切は前の日の締切として数える）
    last_day = lambda it: effective_deadline(it["deadline"])[0]
    days_left = lambda it: (datetime.fromisoformat(last_day(it)).date() - now.date()).days
    new_since = (now - timedelta(days=NEW_DAYS)).isoformat()
    is_new = lambda it: (it.get("published") or "") >= new_since
    plain = load_plain_titles()
    for it in open_items:
        if it["id"] in plain:
            it["plain"] = plain[it["id"]]
    focus = [it for it in open_items if it["tags"]]

    posts = []  # (見出し, 本文, 関係する締切日：投稿文ページで、締切が過ぎたものを隠すのに使う)

    # 1) 毎日のまとめ
    posts.append(("今日のまとめ", (
        f"いま国が「みんなの意見を聞かせて」と募集しているテーマが{len(open_items)}件あります📣\n"
        f"子育て・年金・外国人のことなど、暮らしに身近な話も。\n"
        f"ひとことからでも送れます🙆\n"
        f"{site}\n{main_tag}"
    ), ""))

    # 2) 注目テーマの新着（1件ごとの定型文）
    hashtag_of = {t["name"]: t["hashtag"] for t in tag_defs}
    for it in sorted([it for it in focus if is_new(it)], key=lambda it: it["published"], reverse=True):
        posts.append((f"新着｜{'・'.join(it['tags'])}", share_text(it, main_tag, hashtag_of, site), last_day(it)))

    # 3) 注目テーマの締切間近（1件ごとの定型文）
    for it in sorted([it for it in focus if days_left(it) <= CLOSING_DAYS], key=lambda it: it["deadline"]):
        posts.append((f"締切間近｜{'・'.join(it['tags'])}", share_text(it, main_tag, hashtag_of, site), last_day(it)))

    # 4) 注目テーマごとの紹介
    for t in tag_defs:
        its = [it for it in open_items if t["name"] in it["tags"]]
        if not its:
            continue
        posts.append((f"テーマ紹介｜{t['name']}", (
            f"{t['emoji']}{t['friendly']}について、国が意見を募集している案が{len(its)}件あります。\n"
            f"いちばん近い締切は{mmdd(last_day(its[0]))}。\n"
            f"どんな案か、ちょっとのぞいてみませんか？\n"
            f"{site}\n{main_tag} {t['hashtag']}"
        ), last_day(its[0])))

    write_outputs(posts, data["updated"], config)


def write_outputs(posts, updated, config):
    txt = [f"X投稿文（{updated[:16].replace('T', ' ')} 更新）", ""]
    for i, (label, body, _) in enumerate(posts, 1):
        txt += [f"===== {i}. {label}（{length(body)}/{LIMIT}字） =====", body, ""]
    (HERE / "posts.txt").write_text("\n".join(txt), encoding="utf-8")

    page = ui.posts_page(posts, level="national", updated=updated, counts=ui.level_counts(), length=length, limit=LIMIT)
    (HERE / "docs").mkdir(exist_ok=True)
    (HERE / "docs" / "posts.html").write_text(page, encoding="utf-8")
    print(f"posts.txt と docs/posts.html を作りました（投稿文 {len(posts)} 本）")


if __name__ == "__main__":
    main()

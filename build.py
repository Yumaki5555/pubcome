"""data.json から公開用の一覧ページ（docs/index.html）と、案件ごとのスマホ用まとめ（docs/p/案件番号.html）を作る。
ページの見た目と動きは、3つの版で共通の ui.py にまとめてある。

使い方:  python build.py
"""
import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import ui
from ui import SHARE_JS, effective_deadline, date_ja, updated_ja  # SHARE_JS は post.py などもここから使う

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


def load_summaries(folder=HERE):
    """summaries.json（案件番号 → かんたん要約）を読む。1行目が「ひとことで」、2行目以降が「・」で始まる箇条書き。"""
    path = folder / "summaries.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_excluded(folder=HERE):
    """exclude.json（案件番号 → 理由）：募集が終わっている・案件ではないなどで、載せないもの。"""
    path = folder / "exclude.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def first_line(summary):
    """一覧に出す「ひとことで」の部分（要約の1行目）。"""
    return summary.strip().split("\n")[0] if summary else ""


def display_title(item):
    """わかりやすい言い換えがあればそれを、なければ正式名称を短くしたものを使う。"""
    return item.get("plain") or short_title(item["title"])


def summary_path(item):
    """案件ごとのスマホ用まとめページの場所（サイト内の相対パス）。"""
    return f"p/{item['id']}.html"


def share_text(item, main_hashtag, hashtag_of, site_url):
    """1件ごとの投稿の定型文（一覧ページの「Xで共有」と投稿文ページで共通）。
    リンク（23字として数える）込みで140字以内にする。締切は実際に出せる最後の日（0時締切なら前の日）にする。"""
    d = date.fromisoformat(effective_deadline(item["deadline"])[0])
    tags = " ".join([main_hashtag] + [hashtag_of[t] for t in item["tags"]])
    make = lambda title: (f"📣【パブコメ募集】{d.month}/{d.day}まで\n\n"
                          f"「{title}」\n国（{item['ministry']}）\n\n"
                          f"ひとことからでも、誰でも送れます🙆\n{tags}\n\n")
    title = display_title(item)
    while len(make(title)) + 23 > 140 and len(title) > 8:
        title = title[:-2].rstrip("…") + "…"
    return make(title) + site_url + summary_path(item)


def main():
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    tags = json.loads((HERE / "keywords.json").read_text(encoding="utf-8"))["tags"]
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))

    # 締切は「日付」で判定する（締切の当日は、時刻を過ぎても一覧に残し、画面で「受付終了」と示す）
    today = datetime.now(JST).date().isoformat()
    excluded = load_excluded()
    open_items = [it for it in data["items"] if it["deadline"] and effective_deadline(it["deadline"])[0] >= today
                  and it["id"] not in excluded]
    hashtag_of = {t["name"]: t["hashtag"] for t in tags}
    plain = load_plain_titles()
    summaries = load_summaries()
    for it in open_items:
        if it["id"] in plain:
            it["plain"] = plain[it["id"]]
        if summaries.get(it["id"]):
            it["summary"] = summaries[it["id"]]
        it["share"] = share_text(it, config["main_hashtag"], hashtag_of, config["site_url"])
        it["page"] = summary_path(it)
    counts = ui.level_counts()
    ui.write_shared(counts)
    build_summary_pages(open_items, tags, config)

    items = []
    for it in open_items:
        day, clock = effective_deadline(it["deadline"])
        gist, points = ui.split_summary(it.get("summary"))
        title = display_title(it)
        items.append({
            "id": it["id"], "t": title, "o": it["title"] if it["title"] != title else "",
            "body": it["ministry"], "cat": it.get("category") or "",
            "since": (it.get("published") or "")[:10], "dl": day, "time": clock,
            "url": it["url"], "page": it["page"], "share": it["share"],
            "gist": gist, "pts": points, "tags": it["tags"],
        })
    payload = {
        "level": "national",
        "updated": data["updated"],
        "items": items,
        "tags": [{"name": t["name"], "color": t["color"]} for t in tags],
        "counts": counts,
        "newDays": config.get("new_days", 7),
    }
    up = updated_ja(data["updated"])
    info = f"""<section class="info" aria-labelledby="info-h"><h2 id="info-h">このページの情報について</h2><dl>
<div><dt>出典</dt><dd>国の案件は、<a href="{ui.EGOV_TOP}" target="_blank" rel="noopener">e-Govパブリック・コメント</a>（国の公式の意見募集サイト）から集めています。各案件の「内容を見る」から、公式の資料を開けます。</dd></div>
<div><dt>更新</dt><dd>毎朝、自動で更新しています（データ最終更新：{ui.esc(up)}）。締切の日を過ぎた案件は、自動で一覧から外れます。</dd></div>
<div><dt>わかりやすい名前・要約</dt><dd>正式名称と公式の資料をもとに、AIが作ったものです。まちがいがある場合もあるので、正式な内容は必ず公式ページでご確認ください。</dd></div>
<div><dt>テーマ</dt><dd>案件名・分野・省庁名に含まれる言葉で自動的に振り分けています。テーマが付いていても関係が薄い案件や、付いていなくても関係する案件があります。</dd></div>
<div><dt>載っていない案件</dt><dd>e-Govに載っていない意見募集（各省庁が独自に行うものなど）は含まれません。</dd></div>
</dl></section>"""
    page = ui.list_page(
        level="national",
        title=f"{config['site_name']}｜いま意見を出せる国の案件一覧",
        og_title=f"{config['site_name']}｜募集中のパブコメ {len(items)}件",
        desc=config["site_description"], url=config["site_url"],
        h1="国の意見募集（パブコメ）",
        intro="国（各省庁）が、いま意見を募集している案件です（出典：e-Govパブリック・コメント）。",
        placeholder="例：子ども、年金",
        fields='<label class="field">担当省庁<select id="ministry"><option value="">すべての省庁</option></select></label>',
        info=info,
        footer=f'<p>出典：<a href="{ui.EGOV_TOP}" target="_blank" rel="noopener">e-Govパブリック・コメント</a>（毎朝自動で更新）</p>'
               '<p>このサイトは国や自治体の公式サイトではありません。正式な内容は、必ず各公式ページでご確認ください。</p>',
        updated=data["updated"], payload=payload,
        noscript=f'<a href="{ui.EGOV_TOP}">e-Govパブリック・コメント</a>で直接お探しください。',
    )

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
        day, clock = effective_deadline(it["deadline"])
        det = it.get("detail") or {}
        groups = [("まず読む：意見募集要領（出し方・提出先）", det.get("guide_files", [])),
                  ("案の中身", det.get("draft_files", [])),
                  ("関連資料", det.get("other_files", []))]
        files_html = "".join(f'<h3>{e(label)}</h3><ul class="files">{file_list(fs)}</ul>' for label, fs in groups if fs)
        n_files = sum(len(fs) for _, fs in groups[:2])
        title = display_title(it)
        deadline_text = f"{date_ja(day)} {clock}まで"
        if it["deadline"][11:16] == "00:00":
            raw = datetime.fromisoformat(it["deadline"])
            deadline_text += f"<small>（e-Govの表記は「{raw.month}月{raw.day}日 0:00」）</small>"
        warn = (f'<p class="warn">⚠️ e-Govでは、資料（この案件は{n_files}個）を<b>すべて一度開かないと</b>'
                f'「確認しました」のチェックが入れられない仕組みです。</p>') if n_files else ""
        howto = f"""<section class="box" aria-labelledby="how-h"><h2 id="how-h">✍️ 意見の出し方</h2>
<ol class="steps">
<li><b>資料を読む</b><span>下の「資料」で、どんな案かを確かめます（概要だけでも大丈夫です）。</span></li>
<li><b>「意見を提出する」でe-Govを開く</b><span>e-Govのページで資料をひとつずつ開き、「確認しました」にチェックを入れて「意見入力へ」に進みます。</span></li>
<li><b>意見を書いて送信する</b><span>短い意見でも送れます。</span></li>
</ol>{warn}
<h3>だれが出せる？</h3><p>国の意見公募は、広く一般から意見を受け付けています。氏名などの記入が必要か、郵送などほかの出し方があるかは案件ごとに違うので、「意見募集要領」でご確認ください。</p>
<h3>出した意見はどうなる？</h3><p>寄せられた意見は、案を決める前に検討されます。結果と「意見に対する考え方」は、後日e-Govなどで公表されるのが一般的です。ただし、意見がそのまま採用されるとは限りません。</p>
</section>"""
        basic = [("担当", it["ministry"]), ("分野", it.get("category")),
                 ("募集開始", date_ja(it["published"][:10]) if it.get("published") else ""),
                 ("案の題名", det.get("rule_name")), ("根拠となる法律", det.get("law"))]
        extra = ('<section class="box" aria-labelledby="basic-h"><h2 id="basic-h">🗂 基本情報（e-Govの記載）</h2><dl class="basic">'
                 + "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in basic if v) + "</dl></section>")
        note = e(det.get("note", "")).replace("\n", "<br>")
        if note:
            extra += f'<section class="box" aria-labelledby="note-h"><h2 id="note-h">備考</h2><p>{note}</p></section>'
        source = (f'<p>この案件の情報は、<a href="{e(it["url"])}" target="_blank" rel="noopener">e-Govパブリック・コメントの案件ページ</a>'
                  f'から自動で集めています（毎朝更新）。</p>'
                  '<p>わかりやすい名前と要約は当サイトがAIで作ったものです。正式な内容は必ずe-Govでご確認ください。</p>')
        page = ui.detail_page(
            level="national", root="../",
            title=title, og_title=f"【パブコメ募集】{title}",
            desc=f"{date.fromisoformat(day).month}/{date.fromisoformat(day).day}まで意見募集中（{it['ministry']}）。ひとことからでも、誰でも意見を送れます。",
            page_url=config["site_url"] + summary_path(it),
            who=f'国｜{e(it["ministry"])}' + (f'<span class="cat">分野：{e(it["category"])}</span>' if it.get("category") else ""),
            official=ui.official_line(title, it["title"]),
            deadline_text=deadline_text, dl=day, time=clock,
            submit_url=it["url"], submit_note="e-Gov（国の公式ページ）で提出",
            themes=ui.themes_line(it["tags"], color_of),
            summary=ui.summary_block(it.get("summary"), "国"),
            howto=howto,
            files=files_html or '<p>資料はe-Govのページでご確認ください。</p>',
            extra=extra,
            contact=e(det.get("contact", "")).replace("\n", "<br>") or "e-Govのページでご確認ください。",
            source=source, share=it["share"],
        )
        (out / f"{it['id']}.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()

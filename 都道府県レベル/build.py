"""data.json から都道府県版の一覧ページ（../docs/pref/index.html）とスマホ用まとめを作る。
市区町村版（../市区町村レベル/build.py）も、言葉と置き場所を config.json で差し替えてこの仕組みを使う。
ページの見た目と動きは、3つの版で共通の ../ui.py にまとめてある。

使い方:  python build.py
"""
import html
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
BASE = HERE   # データや設定を読むフォルダ（市区町村版では 市区町村レベル/ になる）
sys.path.insert(0, str(HERE.parent))
from build import short_title, load_summaries, load_excluded  # 国版と共通の部品を使う
import ui
from ui import date_ja, updated_ja


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
                          f"「{title}」\n{item['pref']}\n\n"
                          f"{item['pref']}関係者は、ひとことからでも送れます🙆\n"
                          f"それ以外の方は案件ごとにご確認ください\n{tags}\n\n")
    title = display_title(item)
    while len(make(title)) + 23 > 140 and len(title) > 8:
        title = title[:-2].rstrip("…") + "…"
    return make(title) + site_url + summary_path(item)


def main(base=HERE):
    global BASE, OUT_DIR
    BASE = base
    config = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    OUT_DIR = HERE.parent / "docs" / config.get("out_dir", "pref")
    level = config.get("out_dir", "pref")          # "pref" または "city"
    tags = json.loads((HERE.parent / "keywords.json").read_text(encoding="utf-8"))["tags"]
    data = json.loads((BASE / "data.json").read_text(encoding="utf-8"))

    today = datetime.now(JST).date().isoformat()
    excluded = load_excluded(BASE)
    open_items = [it for it in data["items"] if it["deadline"] >= today and it["id"] not in excluded]
    hashtag_of = {t["name"]: t["hashtag"] for t in tags}
    plain = load_plain_titles()
    summaries = load_summaries(BASE)
    listed = json.loads((BASE / config.get("list_file", "prefectures.json")).read_text(encoding="utf-8"))
    prefs = listed.get("prefectures") or listed.get("areas")
    pref_of = {a["name"]: a.get("pref", "") for a in prefs}   # 市区町村版：市区 → 都道府県
    # 募集開始日が書かれていない案件は、見回りを始めた日に見つけたものだと本当の開始日がわからないので
    # 新着あつかいにしない（それ以降に初めて見つけたものだけ、見つけた日を開始日の代わりにする）
    first_crawl = min((it["first_seen"] for it in data["items"]), default="")
    items = []
    for it in open_items:
        if it["id"] in plain:
            it["plain"] = plain[it["id"]]
        if summaries.get(it["id"]):
            it["summary"] = summaries[it["id"]]
        it["share"] = share_text(it, config["main_hashtag"], hashtag_of, config["site_url"])
        gist, points = ui.split_summary(it.get("summary"))
        title = display_title(it)
        items.append({
            "id": it["id"], "t": title, "o": it["title"] if it["title"] != title else "",
            "body": it["pref"], "area": pref_of.get(it["pref"], "") if level == "city" else "",
            # 新着の判定用：募集開始日（わからなければ空）
            "since": it.get("start") or (it["first_seen"] if it["first_seen"] > first_crawl else ""),
            "dl": it["deadline"], "time": "",
            "url": it["url"], "page": summary_path(it), "share": it["share"],
            "gist": gist, "pts": points, "tags": it["tags"],
            "how": ui.submit_methods((it.get("detail") or {}).get("howto")),
        })
    counts = ui.level_counts()
    ui.write_shared(counts)
    build_summary_pages(open_items, tags, config, level, pref_of, data.get("merged", {}))
    if "pref" in prefs[0]:
        # 市区町村版：都道府県ごとにまとめる（都道府県の並びは REGIONS の順）
        order = [n for _, names in REGIONS for n in names]
        groups = [(pn, [a["name"] for a in prefs if a["pref"] == pn]) for pn in order]
        groups = [g for g in groups if g[1]]
    else:
        groups = REGIONS
    status = data.get("status", {})
    officials = [{"name": p["name"], "url": p["url"], "pref": p.get("pref", ""),
                  "error": bool((status.get(p["name"]) or {}).get("error"))} for p in prefs]
    # 都道府県版で県を選んだとき「この県の市区の案件も見る」を出すため、市区町村版で見回っている都道府県を渡す
    related = []
    if level == "pref":
        city_areas = HERE.parent / "市区町村レベル" / "areas.json"
        if city_areas.exists():
            related = sorted({a["pref"] for a in json.loads(city_areas.read_text(encoding="utf-8"))["areas"]})
    payload = {
        "level": level,
        "updated": data["updated"],
        "items": items,
        "tags": [{"name": t["name"], "color": t["color"]} for t in tags],
        "regions": groups,
        "prefs": [n for _, names in REGIONS for n in names],   # 47都道府県（アドレスで指定された名前が都道府県かを確かめる）
        "officials": officials,
        "related": related,
        "counts": counts,
        "newDays": config.get("new_days", 7),
    }
    count_of = {}
    for i in items:
        count_of[i["body"]] = count_of.get(i["body"], 0) + 1
    page = ui.list_page(
        level=level,
        title=f"{config['site_name']}｜いま意見を出せる{config.get('area_label', '都道府県')}の案件一覧",
        og_title=f"{config['site_name']}｜募集中のパブコメ {len(items)}件",
        desc=config["site_description"], url=config["site_url"],
        h1=f"{config.get('area_label', '都道府県')}の意見募集（パブコメ）",
        intro=INTRO[level],
        placeholder="例：子ども、条例",
        fields=FIELDS[level],
        info=info_html(level, data["updated"], groups, officials, count_of),
        footer=('<p>出典：各自治体の公式ホームページ（毎朝自動で更新）</p>'
                '<p>このサイトは国や自治体の公式サイトではありません。正式な内容は、必ず各公式ページでご確認ください。</p>'),
        updated=data["updated"], payload=payload,
        noscript="下の「公式ページ」の一覧から各自治体のページをご覧ください。",
    )
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    print(f"docs/{config.get('out_dir', 'pref')}/index.html を作りました"
          f"（募集中 {len(items)} 件、{len({i['body'] for i in items})} {config.get('area_label', '都道府県')}）")

    # X投稿文のページ（posts.html）も一緒に作る
    import importlib.util
    spec = importlib.util.spec_from_file_location("pref_post", HERE / "post.py")
    pref_post = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pref_post)
    pref_post.main(BASE)


INTRO = {
    "pref": "47都道府県の公式ホームページから毎日自動で集めた、いま意見を募集している案件です。このサイトに載っていなくても、実際には募集していることがあります。",
    "city": ("政令指定都市・中核市・東京23区（計105か所）の公式ホームページから毎日自動で集めた案件です。"
             "それ以外の市町村は、まだ自動収集の対象外です。このサイトに載っていなくても、実際には募集していることがあります。"),
}

FIELDS = {
    "pref": '<label class="field">都道府県<select id="pref"><option value="">すべての都道府県</option></select></label>',
    "city": ('<label class="field">都道府県<select id="pref"><option value="">すべての都道府県</option></select></label>'
             '<label class="field">市区町村<select id="city"><option value="">すべての市区町村</option></select></label>'),
}


def info_html(level, updated, groups, officials, count_of):
    """一覧ページの下の「このページの情報について」（出典・対象・注意・公式ページの一覧）。"""
    e = ui.esc
    if level == "pref":
        target = "47都道府県すべてです。"
        label = "都道府県"
    else:
        target = ("政令指定都市20・中核市62・東京23区の計105か所です。"
                  "<b>それ以外の市町村（約1,600）は、まだ自動収集の対象外です。</b>お住まいの市町村の公式ホームページでご確認ください。")
        label = "市区"
    return f"""<section class="info" aria-labelledby="info-h"><h2 id="info-h">このページの情報について</h2><dl>
<div><dt>出典</dt><dd>各{label}の公式ホームページから、毎日自動で集めています。案件ごとに、元のページを「出典」として示しています。</dd></div>
<div><dt>自動収集の対象</dt><dd>{target}</dd></div>
<div><dt>更新</dt><dd>毎朝、自動で更新しています（データ最終更新：{e(updated_ja(updated))}）。締切の日を過ぎた案件は、自動で一覧から外れます。</dd></div>
<div><dt>注意</dt><dd>{label}ごとにページの作りがバラバラなため、載っていない案件や、まちがって載る案件があります。<b>このサイトで0件でも、実際には募集していることがあります。</b>下の一覧から各公式ページも確認できます。</dd></div>
<div><dt>提出方法</dt><dd>カードの「提出方法」は、公式ページの「意見の出し方」の文に出てくる言葉を自動で拾ったものです。正確な出し方と、意見を出せる人は、必ず公式ページでご確認ください。</dd></div>
<div><dt>わかりやすい名前・要約</dt><dd>正式名称と公式の資料をもとに、AIが作ったものです。まちがいがある場合もあるので、正式な内容は必ず公式ページでご確認ください。</dd></div>
<div><dt>テーマ</dt><dd>案件名に含まれる言葉で自動的に振り分けています。テーマが付いていても関係が薄い案件や、付いていなくても関係する案件があります。</dd></div>
</dl>
{ui.area_list_html(groups, officials, count_of, "都道府県" if level == "pref" else "市区")}
</section>"""


def words(page, config):
    """ひな形の「__UNIT__（県）」「__AREA__（都道府県）」を、都道府県版・市区町村版の言葉に置き換える。"""
    return page.replace("__UNIT__", config.get("unit", "県")).replace("__AREA__", config.get("area_label", "都道府県"))


def build_summary_pages(items, tag_defs, config, level, pref_of, merged):
    """案件ごとのスマホ用まとめページ（docs/p/番号.html）を作る。締切を過ぎたページは消す。
    merged（外した案件番号 → 残した案件番号）は、同じ案件を1つにまとめたときの対応。"""
    out = OUT_DIR / "p"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.html"):
        old.unlink()
    color_of = {t["name"]: t["color"] for t in tag_defs}
    e = html.escape
    lines = lambda text: "<br>".join(e(x) for x in text.split("\n"))

    for it in items:
        det = it.get("detail") or {}
        body = it["pref"]
        files = "".join(f'<li><a href="{e(f["url"])}" target="_blank" rel="noopener">📄 {e(f["name"])}</a></li>'
                        for f in det.get("files", []))
        start = date_ja(it["start"], with_year=False) if it.get("start") else ""
        deadline_text = f"{date_ja(it['deadline'])}まで" + (f"<small>募集開始：{start}</small>" if start else "")
        methods = ui.submit_methods(det.get("howto"))
        if det.get("howto"):
            how_case = ((f'<p><b>書かれている提出方法：</b>{e("・".join(methods))}</p>' if methods else "")
                        + f'<p class="quote">{lines(det["howto"])}</p>'
                        f'<p class="note">※{e(body)}のページから自動で抜き出した文です。途中で切れていることがあります。くわしくは公式ページでご確認ください。</p>')
        else:
            how_case = f'<p>意見の出し方（メール・入力フォーム・郵送など）は、{e(body)}の公式ページでご確認ください。</p>'
        howto = f"""<section class="box" aria-labelledby="how-h"><h2 id="how-h">✍️ 意見の出し方</h2>
<ol class="steps">
<li><b>資料を読む</b><span>下の「資料」で、どんな案かを確かめます（概要だけでも大丈夫です）。</span></li>
<li><b>出し方を確かめる</b><span>メール・入力フォーム・郵送など、出し方は案件ごとに違います。下の「この案件の出し方」か、{e(body)}の公式ページで確かめます。</span></li>
<li><b>意見を送る</b><span>書かれている方法で送ります。住所・氏名などの記入が必要なことがあります。</span></li>
</ol>
<h3>この案件の出し方（公式ページの記載）</h3>{how_case}
<h3>だれが出せる？</h3><p>自治体の意見募集は、そこに住んでいる人・通勤や通学をしている人・事業をしている人などが対象のことが多いですが、案件ごとに違います。公式ページでご確認ください。</p>
<h3>出した意見はどうなる？</h3><p>寄せられた意見は、案を決める前に検討されます。多くの場合、結果と「意見に対する考え方」が後日公表されます。ただし、意見がそのまま採用されるとは限りません。</p>
</section>"""
        period = (f"{date_ja(it['start'])} 〜 " if it.get("start") else "") + f"{date_ja(it['deadline'])}"
        area = pref_of.get(body, "") if level == "city" else ""
        basic = [("自治体", body + (f"（{area}）" if area else "")), ("募集期間", period)]
        extra = ('<section class="box" aria-labelledby="basic-h"><h2 id="basic-h">🗂 基本情報</h2><dl class="basic">'
                 + "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in basic if v) + "</dl></section>")
        source = (f'<p>この案件の情報は、<a href="{e(it["url"])}" target="_blank" rel="noopener">{e(body)}の公式ページ</a>'
                  f'から自動で集めています（毎朝更新）。ページの作りによっては読み取りをまちがえることがあります。</p>'
                  '<p>わかりやすい名前と要約は当サイトがAIで作ったものです。正式な内容は必ず公式ページでご確認ください。</p>')
        d = date.fromisoformat(it["deadline"])
        title = display_title(it)
        where = "都道府県" if level == "pref" else "市区町村"
        page = ui.detail_page(
            level=level, root="../../",
            title=title, og_title=f"【パブコメ募集・{body}】{title}",
            desc=f"{d.month}/{d.day}まで意見募集中（{body}）。{body}関係者は、ひとことからでも意見を送れます。それ以外の方は案件ごとにご確認ください。",
            page_url=config["site_url"] + summary_path(it),
            who=f"{where}｜{e(body)}" + (f"（{e(area)}）" if area else ""),
            official=ui.official_line(title, it["title"]),
            deadline_text=deadline_text, dl=it["deadline"], time="",
            submit_url=it["url"], submit_note="公式ページで提出方法を確認",
            themes=ui.themes_line(it["tags"], color_of),
            summary=ui.summary_block(it.get("summary"), body),
            howto=howto,
            files=f'<ul class="files">{files}</ul>' if files else f'<p>資料は{e(body)}の公式ページでご確認ください。</p>',
            extra=extra,
            contact=lines(det["contact"]) if det.get("contact") else f"{e(body)}の公式ページでご確認ください。",
            source=source, share=it["share"],
        )
        (out / f"{it['id']}.html").write_text(page, encoding="utf-8")

    # 同じ案件を1つにまとめたとき、外したほうのページ（Xなどで共有済みのことがある）から残したほうへ移す
    shown = {it["id"]: it for it in items}
    for old_id, new_id in merged.items():
        if new_id in shown:
            title = e(display_title(shown[new_id]))
            (out / f"{old_id}.html").write_text(
                '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
                f'<meta http-equiv="refresh" content="0; url={new_id}.html">'
                f'<link rel="canonical" href="{e(config["site_url"] + summary_path(shown[new_id]))}"><title>{title}</title></head>'
                f'<body><p>このページは<a href="{new_id}.html">「{title}」のページ</a>に移りました。</p></body></html>',
                encoding="utf-8")


if __name__ == "__main__":
    main()

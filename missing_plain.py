"""募集中なのに、まだわかりやすい言い換え（plain_titles.json）がない案件を一覧表示する。
あわせて、同じ省庁で一覧に出る名前が同じになっている案件（中身は別でも、見た人には重複に見える）も表示する。

使い方:  python missing_plain.py
"""
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build import short_title

HERE = Path(__file__).parent
JST = timezone(timedelta(hours=9))


def same_names(items, plain, org):
    """同じ省庁・自治体で、一覧に出る名前が同じ（「の」や記号の違いだけのものも含む）案件の組。"""
    groups = defaultdict(list)
    for it in items:
        name = plain.get(it["id"]) or short_title(it["title"])
        groups[(it[org], re.sub(r"[の\s・、。（）()「」『』]", "", unicodedata.normalize("NFKC", name)))].append(it)
    return [g for g in groups.values() if len(g) > 1]


def main():
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    path = HERE / "plain_titles.json"
    plain = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = datetime.now(JST).isoformat()
    open_items = [it for it in data["items"] if it["deadline"] and it["deadline"] >= now]
    missing = [it for it in open_items if it["id"] not in plain]
    for it in missing:
        print(f'{it["id"]} | {it["ministry"]} | {it["category"]} | {it["title"]}')
    print(f"言い換えが必要な案件: {len(missing)} 件")
    dups = same_names(open_items, plain, "ministry")
    if dups:
        print("\n同じ名前になっている案件（要約や資料で違いを確かめ、違いがわかる名前に書き直す）:")
        for g in dups:
            for it in g:
                print(f'{it["id"]} | {it["ministry"]} | {plain.get(it["id"], "")} | {it["title"]}')
            print()
    print(f"同じ名前になっている組: {len(dups)} 組")


if __name__ == "__main__":
    main()

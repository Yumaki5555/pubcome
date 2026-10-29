"""募集中なのに、まだわかりやすい言い換え（plain_titles.json）がない案件を一覧表示する。
あわせて、同じ県で一覧に出る名前が同じになっている案件（中身は別でも、見た人には重複に見える）も表示する。

使い方:  python 都道府県レベル/missing_plain.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from missing_plain import same_names  # 国版と共通の部品を使う

JST = timezone(timedelta(hours=9))


def main():
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    path = HERE / "plain_titles.json"
    plain = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    today = datetime.now(JST).date().isoformat()
    open_items = [it for it in data["items"] if it["deadline"] >= today]
    missing = [it for it in open_items if it["id"] not in plain]
    for it in missing:
        print(f'{it["id"]} | {it["pref"]} | {it["title"]}')
    print(f"言い換えが必要な案件: {len(missing)} 件")
    dups = same_names(open_items, plain, "pref")
    if dups:
        print("\n同じ名前になっている案件（要約や資料で違いを確かめ、違いがわかる名前に書き直す）:")
        for g in dups:
            for it in g:
                print(f'{it["id"]} | {it["pref"]} | {plain.get(it["id"], "")} | {it["title"]}')
            print()
    print(f"同じ名前になっている組: {len(dups)} 組")


if __name__ == "__main__":
    main()

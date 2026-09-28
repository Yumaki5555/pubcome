"""募集中なのに、まだわかりやすい言い換え（plain_titles.json）がない案件を一覧表示する。

使い方:  python 都道府県レベル/missing_plain.py
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
JST = timezone(timedelta(hours=9))


def main():
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    path = HERE / "plain_titles.json"
    plain = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    today = datetime.now(JST).date().isoformat()
    missing = [it for it in data["items"] if it["deadline"] >= today and it["id"] not in plain]
    for it in missing:
        print(f'{it["id"]} | {it["pref"]} | {it["title"]}')
    print(f"言い換えが必要な案件: {len(missing)} 件")


if __name__ == "__main__":
    main()

"""市区町村のホームページから「意見募集中」のパブリックコメントを集めて data.json に保存する。

読み取りのしくみは都道府県版（../都道府県レベル/fetch.py）とまったく同じで、
見回る先の一覧だけを areas.json（政令指定都市・中核市・東京23区）に差し替えている。

使い方:  python 市区町村レベル/fetch.py            （すべて）
         python 市区町村レベル/fetch.py 札幌市 港区   （一部だけ試す）
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("pref_fetch", HERE.parent / "都道府県レベル" / "fetch.py")
pref_fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pref_fetch)

if __name__ == "__main__":
    sys.exit(pref_fetch.main(HERE / "areas.json", HERE / "data.json"))

"""data.json から市区町村版の一覧ページ（../docs/city/index.html）とスマホ用まとめを作る。

ページの作り方は都道府県版（../都道府県レベル/build.py）と同じで、
言葉（「県」→「市区」など）と置き場所を config.json で差し替えている。

使い方:  python 市区町村レベル/build.py
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("pref_build", HERE.parent / "都道府県レベル" / "build.py")
pref_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pref_build)

if __name__ == "__main__":
    pref_build.main(HERE)

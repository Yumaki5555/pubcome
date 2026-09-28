# パブコメ掲示板

国（各省庁）が意見を募集している「パブリックコメント」を e-Gov から毎日集め、
締切が近い順の一覧ページと、X（旧Twitter）の投稿文を自動で作る仕組みです。

## ファイルの役割

| ファイル | 役割 |
|---|---|
| `fetch.py` | e-Gov から募集中の案件を集めて `data.json` に保存し、注目テーマの目印（タグ）を付ける |
| `build.py` | 一覧ページ `docs/index.html` を作る |
| `post.py` | X投稿文 `posts.txt` と、ボタンで投稿できる `docs/posts.html` を作る |
| `keywords.json` | 注目テーマ（外国人政策・モスク/宗教施設・子育て・社会保障）の判定に使う言葉の表。自由に編集OK |
| `config.json` | サイト名・説明文・公開アドレスなどの設定 |
| `.github/workflows/daily.yml` | 毎朝7時に上の3つを自動で動かす設定（GitHubで使う） |

## 手元のパソコンで動かす

```
python fetch.py
python build.py
python post.py
```

`docs/index.html` をダブルクリックすると一覧ページが見られます。

## インターネットに公開する（GitHub Pages）

GitHub（ギットハブ）は、ファイルを預けておける無料サービスです。
「GitHub Pages」でページを公開し、「GitHub Actions」で毎朝自動更新します。
パソコンの電源が切れていても自動で動きます。

1. https://github.com/ でアカウントを作る（無料）
2. 右上の「＋」→「New repository」で置き場所を作る
   - 名前の例：`pubcome`／「Public（公開）」を選ぶ
3. このフォルダのファイルをすべてアップロードする
4. 「Settings」→「Pages」で、Branch を `main`、フォルダを `/docs` にして Save
   - 数分後に `https://ユーザー名.github.io/pubcome/` で見られるようになります
5. `config.json` の `site_url` をそのアドレスに書き換える
6. 「Actions」タブ → 「daily-update」→「Run workflow」で一度動かして確認

以後は毎朝7時に自動で更新されます。

## 毎日のX投稿

`https://ユーザー名.github.io/pubcome/posts.html` をスマホで開き、
好きな投稿文の「𝕏で投稿する」を押すと、文章が入った状態でXが開きます。
内容を確認してから投稿してください。

## 注目テーマの言葉を増やす・減らす

`keywords.json` の `keywords` の中に言葉を足したり消したりするだけでOKです。
言葉で自動判定しているので、関係ない案件が混ざったり、漏れたりすることがあります。

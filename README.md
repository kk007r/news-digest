# 毎日のニュースまとめツール

RSS/Atomの公開フィードから、テックニュースと格闘技ニュースをキーワードで抽出し、スマホ閲覧用HTMLとObsidian用Markdownを生成する個人用ツールです。

LINE連携、OpenAI API、有料API、APIキーが必要なサービスは使いません。ニュース本文の全文転載も行わず、見出し、短い説明、URL、取得元、関連キーワードだけを保存します。

## できること

- RSS/Atomから記事情報を取得する
- `keywords.yml` のキーワードに一致した記事だけ抽出する
- コンソールに抽出結果を表示する
- `docs/index.html` を生成する
- `news/daily`、`news/tech`、`news/mma` にMarkdownを生成する
- GitHub Actionsで毎朝自動実行する

## フォルダ構成

```text
news-digest/
├─ AGENTS.md
├─ README.md
├─ requirements.txt
├─ main.py
├─ feeds.yml
├─ keywords.yml
├─ obsidian.yml
├─ translations.yml
├─ sync_obsidian.py
├─ docs/
│  ├─ .nojekyll
│  ├─ index.html
│  └─ style.css
├─ news/
│  ├─ daily/
│  ├─ tech/
│  └─ mma/
└─ .github/
   └─ workflows/
      └─ daily-news.yml
```

このフォルダをリポジトリのルートとして使う想定です。

## 初回セットアップ

Windows PowerShell:

```powershell
cd C:\Users\komor\news-digest
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux:

```bash
cd ~/news-digest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 手動実行

```powershell
cd C:\Users\komor\news-digest
python main.py
```

実行すると以下が生成・更新されます。

```text
docs/index.html
news/daily/YYYY-MM-DD_ニュースまとめ.md
news/tech/YYYY-MM-DD_テックニュース.md
news/mma/YYYY-MM-DD_格闘技ニュース.md
```

HTMLだけ不要な場合:

```powershell
python main.py --no-html
```

Markdownだけ不要な場合:

```powershell
python main.py --no-markdown
```

## 動作確認

1. `python main.py` を実行する。
2. コンソールにテックニュースと格闘技ニュースの件数、記事タイトル、URLが表示されることを確認する。
3. `docs/index.html` をブラウザで開き、スマホ幅でも読みやすいことを確認する。
4. `news/daily`、`news/tech`、`news/mma` に今日の日付のMarkdownが作られていることを確認する。
5. Markdownの先頭にYAML front matterがあることを確認する。

## 設定: feeds.yml

ニュース取得元は `feeds.yml` で管理します。

```yml
tech:
  - name: "GitHub Blog"
    url: "https://github.blog/feed/"

mma:
  - name: "UFC News"
    url: "https://www.ufc.com/rss/news"
```

RSSが見つからないサイトは、次のように無効化したままメモを残せます。

```yml
mma:
  - name: "RIZIN 公式ニュース"
    url: ""
    enabled: false
    note: "RSS URLが見つかったらここに追加してください。"
```

RSS URLが見つかったら `url` に追加し、`enabled: true` に変更してください。

## 設定: keywords.yml

抽出キーワードは `keywords.yml` で管理します。

```yml
tech:
  - AI
  - OpenAI
  - GitHub

mma:
  - RIZIN
  - UFC
  - 平良達郎
```

記事タイトル、短い説明、取得元名のどれかにキーワードが含まれると抽出対象になります。

## 設定: translations.yml

英語記事を日本語で読みやすくしたい場合は、`translations.yml` にURLごとの手動訳を追加します。

```yml
articles:
  "https://example.com/article":
    title_ja: "日本語タイトル"
    summary_ja: "短い日本語概要"
```

`main.py` は一致するURLがあれば、日本語タイトルと日本語概要を優先してHTMLとMarkdownに表示します。登録がない記事はRSSの原文タイトルと原文概要を表示します。

自動翻訳API、OpenAI API、有料翻訳APIは使っていません。リンク先本文については、記事全文を保存せず、HTMLに「日本語翻訳で開く」リンクを追加します。このリンクはGoogle翻訳のWeb表示を開くためのもので、APIキーや追加費用は不要です。

## Obsidianへの取り込み

生成済みMarkdownは `sync_obsidian.py` でObsidian保管庫へコピーできます。

まず、Obsidian側で保管庫を作成します。その後、保管庫のパスを `obsidian.local.yml` に書きます。`obsidian.local.yml` は `.gitignore` 済みなので、個人の保管庫パスをGitHubへ公開せずに済みます。

```yml
vault_path: "C:\\Users\\komor\\Documents\\Obsidian\\MyVault"
target_folder: "News Digest"
overwrite: true
```

ドライラン:

```powershell
python sync_obsidian.py --dry-run
```

実際に同期:

```powershell
python sync_obsidian.py
```

コマンドだけで保管庫を指定することもできます。

```powershell
python sync_obsidian.py --vault "C:\Users\komor\Documents\Obsidian\MyVault"
```

同期される構成:

```text
<Obsidian保管庫>/
└─ News Digest/
   ├─ daily/
   ├─ tech/
   └─ mma/
```

生成されるMarkdownにはYAML front matterが付くため、DataviewなどのObsidianプラグインを使う場合も扱いやすくなります。

GitHub Actionsはクラウド上で動くため、PC上のObsidian保管庫には直接コピーできません。Obsidian同期はPCで `python main.py` を実行したあとに `python sync_obsidian.py` を実行してください。

## GitHub Actions

リポジトリ直下の `.github/workflows/daily-news.yml` が毎朝実行用のworkflowです。

- `workflow_dispatch`: GitHubの画面から手動実行
- `schedule`: 毎日UTC 22:00に実行
- 日本時間では毎朝07:00の想定
- 生成された `docs` と `news` をコミット

手動実行するには、GitHubで次を開きます。

1. Actions
2. Daily News Digest
3. Run workflow

## GitHub Pages

このフォルダを専用リポジトリとして使う場合は、GitHub Pagesの公開元を `docs` に設定してください。

公開後は `docs/index.html` がニュースまとめページになります。

このリポジトリの公開URL:

```text
https://komorikazuki.github.io/news-digest/
```

GitHub Pagesの設定:

1. GitHubでリポジトリを開く。
2. `Settings` を開く。
3. `Pages` を開く。
4. `Build and deployment` の `Source` を `Deploy from a branch` にする。
5. `Branch` を `main`、フォルダを `/docs` にする。
6. `Save` を押す。

公開URLは通常、次のどちらかになります。

```text
https://<ユーザー名>.github.io/<リポジトリ名>/
https://<ユーザー名>.github.io/news-digest/
```

`docs/.nojekyll` は、GitHub PagesがJekyll変換を行わず、生成済みHTML/CSSをそのまま配信するための空ファイルです。

## GitHubへ公開する流れ

まだGitリポジトリにしていない場合は、まずこのフォルダでGitを初期化します。

```powershell
cd C:\Users\komor\news-digest
git init
git add .
git commit -m "Initial news digest tool"
```

その後、GitHubで新しいリポジトリを作り、表示された案内に従って `remote` を追加してpushします。

例:

```powershell
git branch -M main
git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
git push -u origin main
```

push後に、上のGitHub Pages設定を行ってください。

## 公開後の確認

1. GitHub Actionsの `Daily News Digest` を `Run workflow` で手動実行する。
2. workflowが成功することを確認する。
3. `docs/index.html` と `news/` に更新コミットが作られることを確認する。
4. GitHub PagesのURLをスマホで開く。
5. 記事タイトル、概要、原文リンク、日本語翻訳リンクが表示されることを確認する。

## 注意点

- RSS取得は毎朝1回程度に抑えます。
- ログインが必要なサイトのスクレイピングは行いません。
- RSS本文が長い場合も、保存する説明文は短く切り詰めます。
- フィード側の仕様変更で取得できなくなることがあります。その場合は `feeds.yml` のURLを差し替えてください。
- GitHub ActionsとGitHub PagesはGitHubの無料枠・標準機能の範囲を想定しています。

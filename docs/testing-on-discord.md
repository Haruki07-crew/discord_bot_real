# テスト用の Bot で動作を確かめる

オフラインのテスト (`python -m unittest discover -s tests`) では、Discord の画面の動きまでは確かめられません。たとえば、ボタンでのページ送り、添付ファイル、DM による通知などです。
これらは、**本番とは別のテスト用 Bot とテスト用サーバー** で確かめます。本番のトークンで手元から起動すると、本番の Bot と二重に動いてしまうので、必ず別の Bot を使ってください。

## 1. テスト用の Bot とサーバーを用意する (初回だけ)

1. Discord で新しいサーバーを作る (左の「＋」→「オリジナルの作成」)。名前は `atcoder-bot-test` などにする。
2. [Developer Portal](https://discord.com/developers/applications) で、本番とは別の Application (例: `AtCoder Bot (test)`) を作る。
3. README の導入手順 1〜3 と同じように、トークンをコピーし、テスト用サーバーに招待して、ID を集める。

## 2. テスト用の設定ファイルを作る

本番の `app/.env` とは別に、リポジトリの外 (例: `~/atcoder-bot-test/.env`) に作ります。

```env
DISCORD_TOKEN=テスト用Botのトークン
ADMIN_ID=自分のユーザーID
RANKING_CHANNEL_ID=テスト用サーバーのチャンネルID
LOG_CHANNEL_ID=テスト用サーバーのチャンネルID
DB_PATH=/Users/<you>/atcoder-bot-test/database.db
```

## 3. 起動する

```bash
cd app
set -a; source ~/atcoder-bot-test/.env; set +a   # テスト用の設定を読み込む (app/.env より優先される)
python main.py
```

> `python-dotenv` は、すでに設定されている環境変数を上書きしません。そのため、先に `source` したテスト用の値が使われます。
> 起動ログの Bot 名がテスト用の名前になっているかを、必ず確認してください。

## 4. 確認すること (チェックリスト)

- [ ] `/user_register` で自分を登録できる (`REQUIRE_ATCODER_VERIFICATION=true` にすると、`/user_verify` の流れも試せる)
- [ ] `/syozin` で、今日の総合AC・新規ACが表示される
- [ ] `/bulk_register` で何人か登録してから `/diligence_growth 1週間` を実行し、◀ ▶ ボタンでページが切り替わる。グラフはどのページでも Embed の中に表示される
- [ ] ボタンが15分後に押せなくなる
- [ ] `/recommend`、`/diligence_score 1週間`、`/versus` が表示され、問題のリンクが正しく開ける
- [ ] `/diligence_growth 1週間 color:緑色` で同じ色の人だけが出る
- [ ] `/notify` でオンにすると DM が届く (22時の連続ACリマインド、月曜9時の週次ふり返り)
- [ ] `/bulk_register` した人に `/user_link` を実行すると、本人が `/notify` を使えるようになる
- [ ] ABC の30分前と10分前にリマインドが出る (それぞれ1回だけ)
- [ ] `/contest_dm minutes:15` で確認の DM が届き、ABC の15分前に DM が1回だけ届く。`/contest_dm` で設定が表示される
- [ ] 実績は、過去の分がまとめて投稿されず、新しく達成したときだけ投稿される
- [ ] `/everyone_state`、`/user_list`、`/abc_ranking 483` が表示される
- [ ] `/bot_status` は管理者だけに見え、管理者以外には断りのメッセージが出る
- [ ] わざとエラーを起こすと (例: 起動中に DB ファイルを消す)、管理者に DM が届く
- [ ] 月曜の週次投稿と ABC の自動投稿は、`RANKING_CHANNEL_ID` のチャンネルに出る (すぐ試したいときは、DB の `bot_state` で `prev_contest` を1つ前の番号にする)

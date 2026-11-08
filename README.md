# AtCoder 精進管理 Discord Bot

AtCoder の精進(AC数・獲得点数)とレートの変化を自動で集計して、Discord にランキングやグラフを投稿する Bot です。
サークルや学校の仲間で「誰がどれだけ精進したか」を見える化して、競い合うために作りました。

## できること

| | 内容 |
|---|---|
| 📈 精進の記録 | `/syozin` で今日のAC数・獲得点数・これまでのAC数を表示 |
| 🏆 ランキング | `/diligence_growth` で、1日〜1年の期間のレート変化とAC数のランキングとグラフを表示 |
| 🔥 連続AC | `/everyone_state` で、全員の総AC数と何日連続でACしているかを表示 |
| 🥇 ABCの結果 | ABC のレートが確定すると、登録メンバーの順位・AC数・パフォーマンスを**自動で投稿** |
| 📊 週次レポート | 毎週月曜 0:15 に、先週のランキングと12週分の累積グラフを**自動で投稿** |

---

## 導入手順

全体の流れ:

1. Discord で Bot を作る (Developer Portal)
2. Bot を自分のサーバーに招待する
3. 必要な ID を集める
4. `.env` に設定を書く
5. Bot を起動する
6. 動作を確認する

所要時間は 15〜20 分ほどです。

### 1. Discord で Bot を作る

1. [Discord Developer Portal](https://discord.com/developers/applications) を開き、右上の **New Application** を押す。名前 (例: `AtCoder Bot`) を入力して作成する。
2. 左のメニューから **Bot** を開く。
3. **Reset Token** を押してトークンを表示し、コピーしておく。これが `DISCORD_TOKEN` になる。
   > ⚠️ トークンはパスワードと同じです。他人に見せたり、GitHub に push したりしないでください。漏れたらすぐに Reset Token で作り直してください。
4. 同じ **Bot** のページの下にある **Privileged Gateway Intents** で、次の3つをすべて **ON** にして保存する。
   - Presence Intent
   - Server Members Intent
   - Message Content Intent

   > これを忘れると、起動時に `PrivilegedIntentsRequired` というエラーで止まります。

### 2. Bot を自分のサーバーに招待する

1. 左のメニューから **OAuth2** → **URL Generator** を開く。
2. **SCOPES** で `bot` と `applications.commands` にチェックを入れる。
3. 下に出てくる **BOT PERMISSIONS** で、次にチェックを入れる。
   - View Channels (チャンネルを見る)
   - Send Messages (メッセージを送信)
   - Embed Links (埋め込みリンク)
   - Attach Files (ファイルを添付) ← グラフ画像の投稿に必要
   - Read Message History (メッセージ履歴を読む)
4. 一番下に出る URL をブラウザで開き、Bot を入れたいサーバーを選んで **認証** する。

### 3. 必要な ID を集める

ID をコピーするには、まず Discord の **開発者モード** を ON にします。
(Discord の **ユーザー設定** → **詳細設定** → **開発者モード**)

ON にすると、右クリックメニューに **ID をコピー** が出るようになります。

| 何の ID か | コピーの仕方 | 設定する名前 |
|---|---|---|
| 管理者 (あなた) のユーザーID | 自分のアイコンを右クリック → ID をコピー | `ADMIN_ID` |
| ランキングを自動投稿するチャンネル | チャンネル名を右クリック → チャンネルIDをコピー | `RANKING_CHANNEL_ID` |
| APIログを流すチャンネル (任意) | 同上。ログ専用のチャンネルを作っておくのがおすすめ | `LOG_CHANNEL_ID` |

### 4. `.env` に設定を書く

`app/.env` というファイルを作り、次のように書きます (値は自分のものに置き換える)。

```env
DISCORD_TOKEN=ここに1でコピーしたトークン
ADMIN_ID=123456789012345678
RANKING_CHANNEL_ID=123456789012345678
LOG_CHANNEL_ID=123456789012345678
```

| 名前 | 必須? | 説明 |
|---|---|---|
| `DISCORD_TOKEN` | ✅ 必須 | Bot のトークン |
| `ADMIN_ID` | ✅ 必須 | 管理者のユーザーID。エラーの通知が届き、他人の登録を解除できるようになる |
| `RANKING_CHANNEL_ID` | おすすめ | ABC結果・週次レポートの投稿先。**未設定だと自動投稿はすべて行われない** |
| `LOG_CHANNEL_ID` | 任意 | APIを呼んだ記録を流すチャンネル。サーバー内に無いIDだとログは送られない |
| `DB_PATH` | 任意 | データベースの保存場所。未設定なら起動したフォルダの `database.db` |
| `PORT` | 任意 | 動作確認用 HTTP サーバーのポート (初期値 `8000`) |

`.env` は `.gitignore` に入っているので、Git にはコミットされません。

### 5. Bot を起動する

起動方法は2つあります。お試しなら **A**、24時間動かし続けるなら **B** がおすすめです。

#### A. 自分のPCで動かす

Python 3.11 を使ってください (Docker 版と同じバージョン)。

```bash
git clone https://github.com/Haruki07-crew/discord_bot_real.git
cd discord_bot_real
pip install -r requirements.txt
cd app
python main.py
```

ターミナルに `activate the bot  now!!!!` と出たら起動成功です。止めるときは `Ctrl + C` を押します。
データは `app/database.db` に保存されます。

#### B. ラズパイ5 / Azure で常時動かす (Docker Compose)

```bash
git clone git@github.com:Haruki07-crew/discord_bot_real.git
cd discord_bot_real
# app/.env を置いてから
docker compose up -d --build
docker compose logs -f     # "activate the bot  now!!!!" が出れば成功
```

- データは `data/database.db` に保存されるので、作り直しても消えません。毎日1:00に `data/backups/` へ14日分のバックアップを取ります。
- OS の準備、非公開リポジトリの clone、`main` 更新時の自動反映、Azure での注意点は **[docs/deploy.md](docs/deploy.md)** にまとめています。

> ⚠️ 別の場所 (自分の PC など) で同じトークンの Bot が動いている場合は、先に止めてください。2つ同時に動くと自動投稿が二重になります。

### 6. 動作を確認する

1. Discord でサーバーを開き、メッセージ欄に `/` を入力する。`/user_register` などが候補に出れば OK。
   - 出ない場合は、Discord を再読み込み (`Ctrl + R` / Mac は `Cmd + R`) してください。反映までに数分かかることもあります。
2. `/user_register atcoder_name:自分のAtCoder名` で自分を登録する。
3. `/syozin atcoder_name:自分のAtCoder名` を実行して、AC数が表示されれば完了です 🎉

---

## 使い方

### メンバーを登録する

| コマンド | 説明 |
|---|---|
| `/user_register atcoder_name [discord_name]` | 自分の AtCoder アカウントを登録する。`discord_name` はランキングに表示される名前 (省略すると Discord の表示名) |
| `/user_unregister atcoder_name` | 登録を解除する。登録した本人か管理者だけが実行できる |
| `/user_list` | 登録メンバーと現在のレートの一覧を表示する |

- 登録できるのは **1人1アカウント** です (管理者は何人でも登録できます)。登録し直すときは `/user_unregister` で解除してから登録します。
- 登録すると、その人の過去の提出をすべて取り込みます。提出が多い人は数分かかります。
- AtCoder のユーザー名は、大文字と小文字を区別しません (`Hanaosi` と `hanaosi` は同じ人として扱います)。

### 精進を見る

| コマンド | 説明 |
|---|---|
| `/syozin atcoder_name` | 今日のAC数・今日の獲得点数・これまでのAC数を表示する。登録していない人でも見られる |
| `/everyone_state` | 全員の総AC数と、何日連続でACしているかを表示する (今日の分は含めず、昨日から数える) |
| `/diligence_growth period` | 期間内のレート変化とAC数のランキングを、グラフ付きで表示する |
| `/diligence_growth_point period` | `/diligence_growth` の点数版。AC数のかわりに獲得点数で比べる |
| `/abc_ranking contest_number` | 指定した ABC (例: `483`) での、登録メンバーの順位・AC数・パフォーマンス・レート変化を表示する |

**`/diligence_growth` の期間** は、今日を含めた日数で数えます。

- `1日`: 今日の 0:00 から今まで
- `1週間`: 6日前の 0:00 から今まで
- `1ヶ月` / `3ヶ月` / `半年` / `1年`: 同様に 30 / 90 / 180 / 365 日分

グラフは、1週間以内なら散布図 (横軸: AC数、縦軸: レート変化) です。それより長い期間では、レートの推移を表す折れ線グラフになります。

> 💡 データは Bot がバックグラウンドで1人ずつ同期し続けています (提出はおよそ5分ごと)。
> コマンドは同期済みのデータを読むだけなので、すぐに返事が出ます。何分前のデータかはランキングの一番下に表示されます。
> `/syozin` で登録済みの人を指定したときは、その人のデータをその場で取り直してから表示します。

### 自動で投稿されるもの

`RANKING_CHANNEL_ID` に設定したチャンネルに投稿されます。

| タイミング | 内容 |
|---|---|
| ABC のレートが確定したあと (1時間ごとに確認) | その ABC に参加した登録メンバーのランキング |
| 毎週月曜 0:15 | 先週 (月〜日) のランキングと、12週分の累積グラフ (AC数版・点数版) |

- 毎日 1:00 にデータベースをバックアップします (投稿はしません)。
- 週次レポートは12週で1サイクルです。13週目からはグラフがリセットされます。
- 月曜 0:15 に Bot が止まっていても、その日のうちに起動すれば週次レポートを投稿します。

### 管理者向け: まとめて登録する

`ADMIN_ID` のユーザーが、Bot がいるチャンネルで次のメッセージを送ると、`app/main.py` に書かれたメンバーをまとめて登録します。

| メッセージ | 登録されるメンバー |
|---|---|
| `テスト用にユーザー登録` | `TEST_USERS` |
| `他高専テスト用に登録` | `OTHER_KOSEN_USERS` |

メンバーを変えたいときは、`app/main.py` の `TEST_USERS` / `OTHER_KOSEN_USERS` を書き換えてください。

---

## 困ったとき

| 症状 | 原因と対処 |
|---|---|
| 起動時に `PrivilegedIntentsRequired` | 手順1-4 の Intents を3つとも ON にする |
| 起動時に `LoginFailure` / `Improper token` | `DISCORD_TOKEN` が間違っている。Developer Portal で Reset Token してコピーし直す |
| `/` を入力してもコマンドが出ない | 招待するときに `applications.commands` を付け忘れている (手順2 をやり直す)。または Discord を再読み込みする |
| グラフが出ない / 送信に失敗する | Bot に **Attach Files** と **Embed Links** の権限があるか確認する |
| ABC の結果や週次レポートが投稿されない | `RANKING_CHANNEL_ID` が正しいか、Bot がそのチャンネルを見られるか確認する |
| 再起動したら登録が消えた | データベースがコンテナの中にある。手順5-B の `docker compose` で起動する (データは `data/` に残る) |
| 「⚠️ エラーが発生しました」と出る | ターミナル (Docker なら `docker compose logs`) にエラーの詳細が出ているので確認する |

---

## データの取得元

- [AtCoder](https://atcoder.jp/): コンテストの成績とレート
- [AtCoder Problems (kenkoooo)](https://kenkoooo.com/atcoder/): 提出の履歴

どちらにも負荷をかけないように、ユーザーごとに1秒以上の間を空けてアクセスしています。

---

## 開発者向け

ファイル構成、データベースの設計、内部の処理の流れは [docs/development.md](docs/development.md) にまとめています。

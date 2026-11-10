# Mac で Bot を1日動かす (caffeinate)

ラズパイの準備ができるまで、手元の Mac を本番機の代わりにする手順です。
Docker Desktop で、ラズパイと同じ構成 (`compose.yaml`) のまま動かします。

所要時間: 15分ほど (初回のビルドに数分かかります)

---

## 0. 始める前に

- [ ] **同じトークンの Bot がほかで動いていないこと。** 2つ同時に動くと自動投稿が二重になります。
- [ ] **Mac を電源アダプタにつなぐこと。** バッテリー駆動のままだと、残量が減ると止まります。
- [ ] **Mac のふたを閉じないこと。** `caffeinate` を使っても、ふたを閉じるとスリープします。
- [ ] Wi-Fi が切れない場所に置くこと。

---

## 1. 最新のコードにする

```bash
cd ~/Documents/discord_bot/atcoder_bot
git checkout main
git pull
```

**確認:** `git log --oneline -1` に `Merge pull request #25` 以降の番号が表示されれば、新しい9機能が入っています。

---

## 2. `app/.env` を見直す

少なくとも次の3つを書きます。特に次の2点に気をつけてください。

```env
DISCORD_TOKEN=トークン
ADMIN_ID=あなたのユーザーID
RANKING_CHANNEL_ID=投稿先チャンネルのID
```

1. **`DISCORD_TOKEN =` の `=` の前にある空白を消す。**
   Python では読めますが、Docker では読めないことがあります。
2. **`RANKING_CHANNEL_ID` を追加する。**
   これが無いと、次の自動投稿がすべて行われません。
   - ABC の結果
   - 週次レポート
   - ABC のリマインド
   - 実績バッジ

   チャンネルIDは、チャンネル名を右クリック →「チャンネルIDをコピー」で取れます。
   出てこないときは、Discord の設定 → 詳細設定 →「開発者モード」をオンにしてください。

ほかに書ける項目は README の「4. `.env` に設定を書く」を見てください。

> ⚠️ `.env` はトークンが入った秘密のファイルです。コミットしたり、人に送ったりしないでください (`.gitignore` 済み)。

---

## 3. Docker Desktop を起動する

```bash
open -a Docker
```

メニューバーのクジラのアイコンが止まったら、起動は完了です。

lima などほかの Docker を使うために `DOCKER_HOST` を設定している場合 (`echo $DOCKER_HOST` で何か表示される場合)、そのままでは Docker Desktop を使えません。**Bot を操作するターミナルでは最初に次を実行してください**。

```bash
unset DOCKER_HOST
docker context use desktop-linux
```

**確認:** `docker version` を実行して、`Server:` の欄が表示されれば OK です。

> 💡 `unset` の効果はそのターミナルの中だけです。新しいターミナルを開いたら、もう一度実行してください。

---

## 4. Bot を起動する

```bash
cd ~/Documents/discord_bot/atcoder_bot
docker compose up -d --build
docker compose logs -f
```

ログに `activate the bot  now!!!!` が出たら、起動は成功です。
ログを見るのをやめるときは `Ctrl + C` を押してください。止まるのはログの表示だけで、Bot は動き続けます。

**確認:** `docker compose ps` を実行して、STATUS が `Up ... (healthy)` になれば OK です。
起動から2分ほどは `(health: starting)` と表示されます。

- データは `data/database.db` に保存されます。Bot を止めたり作り直したりしても消えません。
- 初めて Docker で起動したときは DB が空なので、**メンバーは登録し直しになります** (手順6)。

---

## 5. Mac をスリープさせない

**別のターミナル**を開いて、次を実行します。

```bash
caffeinate -dis
```

| オプション | 意味 |
|---|---|
| `-d` | 画面をスリープさせない |
| `-i` | 操作が無くても Mac をスリープさせない |
| `-s` | 電源につないでいる間は、Mac をスリープさせない |

`-d` だけでも画面が点いている間は動き続けますが、`-i` と `-s` も付けておくと確実です。
このターミナルは閉じずに、そのまま置いておいてください。`Ctrl + C` を押すと `caffeinate` が終わり、普段どおりスリープするようになります。

> 💡 24時間で自動で終わらせたい場合は、`caffeinate -dis -t 86400` と書きます (86400秒 = 24時間)。

---

## 6. Discord で動作を確かめる

1. メッセージ欄に `/` を入力して、Bot のコマンドが候補に出るか確かめる。
   - 出ないときは、Discord を `Cmd + R` で再読み込みしてください。反映まで数分かかることもあります。
2. `/user_register` で自分を登録する。
3. `/syozin` で自分の記録を表示する。
4. `/bot_status` を実行する (管理者だけが使えます)。同期の進み具合が表示されれば OK です。
5. 新しい機能を試す: `/recommend`、`/versus`、`/diligence_score`、`/notify`

試すことの一覧は [testing-on-discord.md](testing-on-discord.md) のチェックリストにあります。
登録した直後は過去の提出を取り込んでいる途中なので、全員分のデータがそろうまで数分〜数十分かかります。

### 1日の間に自動で起きること (JST)

| 時刻 | 起きること |
|---|---|
| 毎日 1:00 | DB のバックアップ (`data/backups/`) |
| 毎日 22:00 | `/notify` で連続ACの通知をオンにした人に DM |
| ABC 開始の30分前 | チャンネルにリマインドを投稿 |
| ABC 終了後 | 結果ランキングを投稿 |
| 30分ごと | 新しく達成した実績を投稿 |
| 月曜 9:00 | `/notify` で週次ふり返りをオンにした人に DM |

---

## 7. 止める

```bash
unset DOCKER_HOST && docker context use desktop-linux   # 新しいターミナルなら
cd ~/Documents/discord_bot/atcoder_bot
docker compose down
```

`caffeinate` を動かしているターミナルで `Ctrl + C` を押します。

データは `data/` に残るので、次に `docker compose up -d` すれば続きから動きます。

---

## コードを更新したとき

ラズパイ用の自動更新 (systemd タイマー) は Mac では使えません。
`main` が更新されたら、次のコマンドで手動で取り込みます。

```bash
git pull
docker compose up -d --build
```

---

## うまくいかないとき

| 症状 | 原因と対処 |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop が起動していない (手順3)。または `DOCKER_HOST` が残っている → `unset DOCKER_HOST` |
| ログに `Improper token` / `LoginFailure` | トークンが間違っている、または `=` の前後に空白がある。Developer Portal で Reset Token して貼り直す |
| コマンドが候補に出ない | Discord を再読み込みする。Bot を招待するときに `applications.commands` の権限を付けたか確認する |
| 自動投稿が来ない | `RANKING_CHANNEL_ID` が未設定か、Bot がそのチャンネルに書き込めない |
| DM が来ない | サーバーのプライバシー設定で「ダイレクトメッセージ」を許可していない |
| 途中で止まっていた | ふたを閉じた、電源が抜けた、Mac が再起動した。Docker Desktop を起動すれば、Bot も自動で立ち上がる (`restart: unless-stopped`) |
| エラーが管理者に DM で届いた | `docker compose logs --tail 200` でログを見る。内容を Claude に貼れば調べられます |

---

## ラズパイに移るとき

1. Mac で `docker compose down` して Bot を止める。
2. `data/` フォルダをそのままラズパイにコピーする。登録したメンバーや取得済みのデータを引き継げる。

   ```bash
   scp -r data <ユーザー名>@atcoder-bot.local:~/discord_bot_real/
   ```

3. ラズパイで [deploy.md](deploy.md) の手順どおりに起動する。

Mac とラズパイで同時に動かさないでください (自動投稿が二重になります)。

# Bot を常時動かす (ラズパイ5 / Azure)

## どれで動かすか

| | ラズパイ5 (おすすめ) | Azure VM (学生向け特典) | Pico 2W |
|---|---|---|---|
| 費用 | 電気代のみ | 無料枠の範囲内なら0円。特典の期間やクレジットが切れると有料・停止 | — |
| データの保存 | SD / SSD にそのまま残る | VM のディスクに残る | — |
| 手間 | 初回の準備 30〜60分 | 初回の準備 30〜60分。期限の管理が必要 | — |
| 止まる要因 | 停電、家のネットワーク、SD カードの故障 | クレジット切れ、特典の期限 | **動かせない** |

- **Pico 2W では動かせません。** マイコン(RAM 520KB)なので、Python 本体・discord.py・matplotlib が動きません。
- Azure の App Service や Container Apps も**おすすめしません**。SQLite のファイルを置く永続ストレージ(Azure Files)では、SQLite のファイルロックが正しく効かず、DB が壊れることがあります。Azure を使うなら、普通の VM に下の手順で入れるのが確実です。

どちらの場合も、Docker Compose で動かします。

- **データの保存場所:** `data/` フォルダ。`data/database.db` が本体で、`data/backups/` に毎日1:00のバックアップが14日分たまります。
- **自動更新:** `main` ブランチが更新されると、5分以内に自動で取り込んで再起動します。

---

## ⚠️ 同じ Bot を2か所で動かさない

同じトークンの Bot が2つ同時に動くと、ABC の結果や週次レポートが二重に投稿されます。新しい環境で動かす前に、ほかの場所 (自分の PC など) で動かしている Bot は止めてください。

---

## ラズパイ5 で動かす

全体の流れと、それぞれで学べること:

| 手順 | やること | 学べること |
|---|---|---|
| 1 | OS を入れて SSH で接続する | Linux のインストール、SSH (リモートログイン) |
| 2 | Docker を入れる | パッケージ管理 (apt)、ユーザーとグループの権限 |
| 3 | Deploy key で clone する | SSH 鍵の仕組み、最小権限 (読み取り専用) の考え方 |
| 4 | `.env` を置く | 秘密情報をコードから分けて管理すること |
| 5 | `docker compose` で起動する | コンテナ、ボリューム (データの永続化)、ログ |
| 6 | systemd タイマーで自動更新する | サービスの管理、定期実行 (cron の代わり) |
| 7 | バックアップを手元に取る | バックアップとリストアの考え方 |

各手順の終わりに「確認」と書いたコマンドがあります。期待どおりに表示されてから次に進むと、どこで詰まったかが分かりやすくなります。

### 1. OS を入れる

1. PC に [Raspberry Pi Imager](https://www.raspberrypi.com/software/) を入れて起動する。
2. 次のように選ぶ。
   - デバイス: **Raspberry Pi 5**
   - OS: **Raspberry Pi OS Lite (64-bit)** (画面なしの版で十分)
   - 書き込み先: SD カード、または USB / NVMe の SSD
3. 「設定を編集する」で、次を設定してから書き込む。
   - ホスト名 (例: `atcoder-bot`)
   - ユーザー名とパスワード
   - Wi-Fi (有線 LAN なら不要)
   - **SSH を有効にする**
4. ラズパイに挿して電源を入れ、PC から接続する。

```bash
ssh <ユーザー名>@atcoder-bot.local
```

**確認:** `uname -m` が `aarch64` と表示されれば、64bit 版の OS が入っています。

> 💡 長く動かし続けるなら、SD カードより **SSD** の方が壊れにくくて安心です。電源は公式の 27W アダプタ、冷却はアクティブクーラーを推奨します。

### 2. Docker を入れる

```bash
sudo apt update && sudo apt full-upgrade -y
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
exit   # 一度ログアウトして入り直すと、sudo なしで docker が使えるようになる
```

**確認:** 入り直したら、次の2つを実行します。

- `docker compose version`: バージョンが表示される
- `docker run --rm hello-world`: `Hello from Docker!` と表示される

### 3. リポジトリを取ってくる (非公開リポジトリなので Deploy key を使う)

ラズパイで、読み取り専用の鍵を作ります。

```bash
ssh-keygen -t ed25519 -f ~/.ssh/atcoder_bot_deploy -N "" -C "atcoder-bot@raspi"
cat ~/.ssh/atcoder_bot_deploy.pub
```

表示された1行をコピーし、GitHub に登録します。

1. リポジトリの **Settings** → **Deploy keys** → **Add deploy key** を開く。
2. Title (例: `raspi`) を入れ、Key にコピーした1行を貼り付ける。
3. **Allow write access はチェックしない**(読み取り専用にする)。

ラズパイに戻って、この鍵を使う設定をしてから clone します。

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/atcoder_bot_deploy
  IdentitiesOnly yes
EOF
ssh -T git@github.com      # 確認: "Hi Haruki07-crew/discord_bot_real! You've successfully authenticated" と出る
git clone git@github.com:Haruki07-crew/discord_bot_real.git ~/discord_bot_real
cd ~/discord_bot_real
```

### 4. `.env` を置く

PC にある `app/.env` を、ラズパイにコピーします(**PC 側で**実行)。

```bash
scp app/.env <ユーザー名>@atcoder-bot.local:~/discord_bot_real/app/.env
```

新しく作る場合は、README の「4. `.env` に設定を書く」の内容で、ラズパイ上に `~/discord_bot_real/app/.env` を作ります。

### 5. 起動する

```bash
cd ~/discord_bot_real
docker compose up -d --build     # 初回はビルドに 5〜10 分かかる
docker compose logs -f           # "activate the bot  now!!!!" が出れば成功 (Ctrl+C で抜ける)
```

Discord で `/syozin` などが動くことを確認します。

### 6. 自動更新を設定する

`main` が更新されたら自動で取り込むようにします。まず `deploy/atcoder-bot-update.service` の `User` と、パス(2か所)を自分の環境に合わせて書き換えます。ユーザー名が `pi` で、`~/discord_bot_real` に clone したなら、そのままで大丈夫です。

```bash
sudo cp deploy/atcoder-bot-update.service deploy/atcoder-bot-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now atcoder-bot-update.timer
systemctl list-timers | grep atcoder     # 次の実行予定が出れば OK
```

更新のログは `journalctl -u atcoder-bot-update -n 50` で見られます。

### 7. バックアップを手元にも取る (おすすめ)

`data/backups/` は同じ SD カードの上にあるので、カードが壊れるとバックアップも一緒に失われます。ときどき PC にコピーしておくと安心です(**PC 側で**実行)。

```bash
scp -r <ユーザー名>@atcoder-bot.local:~/discord_bot_real/data/backups ./atcoder-bot-backups
```

---

## Azure VM で動かす

1. [Azure portal](https://portal.azure.com/) で **Azure for Students** のサブスクリプションを使い、**仮想マシン** を作る。
   - イメージ: **Ubuntu Server 24.04 LTS**(x64 / Arm64 のどちらでも可)
   - サイズ: **B1s**(作成画面に「無料サービスの対象」と表示されるサイズを選ぶ。対象や期間は特典の内容によって変わるので、作成画面で必ず確認する)
   - 認証: **SSH 公開キー**
   - 受信ポート: **SSH (22) のみ**(Bot は外から接続される必要がない)
2. 作成後、`ssh azureuser@<パブリックIP>` で接続する。
3. B1s はメモリが 1GB で、Docker のビルド中に足りなくなることがあるので、スワップを作る。

   ```bash
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
4. あとは **ラズパイの手順 2〜7 と同じ**。
   - `pi` は `azureuser` に、`atcoder-bot.local` はパブリック IP に読み替える。
   - systemd のファイルの `User` とパスも `azureuser` に合わせる。

> ⚠️ Azure のクレジットや特典の期限が切れると、VM が止まります。portal の「コストの管理」で残高と期限を定期的に確認してください。

---

## よく使う操作

```bash
cd ~/discord_bot_real
docker compose ps              # 動いているか
docker compose logs -f         # ログを見る
docker compose restart         # 再起動
docker compose down            # 止める (データは data/ に残る)
docker compose up -d --build   # 手動で最新に作り直す
```

### バックアップから戻す

```bash
docker compose down
cp data/backups/database-YYYYMMDD.db data/database.db
docker compose up -d
```

---

## 詰まったときは

| 症状 | 確認すること |
|---|---|
| `ssh: Could not resolve hostname atcoder-bot.local` | PC とラズパイが同じネットワークにあるか確認する。ルーターの管理画面でラズパイの IP アドレスを調べ、`ssh <ユーザー名>@<IPアドレス>` で接続する |
| `permission denied while trying to connect to the Docker daemon socket` | `usermod -aG docker` のあとに、ログインし直したか確認する |
| `git clone` で `Permission denied (publickey)` | Deploy key の登録と `~/.ssh/config` の内容を確認する。`ssh -vT git@github.com` で詳しいログが出る |
| `docker compose up` で `env file ... not found` | `app/.env` を置いたか確認する (手順4) |
| Bot がすぐ止まる / 再起動を繰り返す | `docker compose logs --tail 50` でエラーを見る。`PrivilegedIntentsRequired` や `Improper token` なら README の「困ったとき」を参照 |
| 自動更新されない | `systemctl list-timers` にタイマーがあるか確認する。`journalctl -u atcoder-bot-update -n 50` でログを見る |

## 参考リンク

**Raspberry Pi**
- [Raspberry Pi Imager (ダウンロード)](https://www.raspberrypi.com/software/)
- [Getting started (公式ドキュメント)](https://www.raspberrypi.com/documentation/computers/getting-started.html): OS の書き込みと初期設定
- [Remote access (公式ドキュメント)](https://www.raspberrypi.com/documentation/computers/remote-access.html): SSH での接続、IP アドレスの調べ方
- [Raspberry Pi hardware (公式ドキュメント)](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html): 電源・冷却・SSD (NVMe) からの起動

**Docker**
- [Install Docker Engine on Debian](https://docs.docker.com/engine/install/debian/): Raspberry Pi OS は Debian ベース。手順2の `get.docker.com` は、このページの "convenience script" のこと
- [Linux post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/): sudo なしで docker を使う設定
- [Docker Compose overview](https://docs.docker.com/compose/): `compose.yaml` の書き方
- [Volumes](https://docs.docker.com/engine/storage/volumes/): データを残す仕組み (このリポジトリでは `./data` をコンテナにつないでいる)

**GitHub / SSH**
- [Managing deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys): 手順3の Deploy key
- [Generating a new SSH key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent): `ssh-keygen` の使い方

**systemd**
- [systemd.timer (man page)](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html): 手順6のタイマーの書き方
- [ArchWiki: systemd/Timers](https://wiki.archlinux.org/title/Systemd/Timers): 例が多くて分かりやすい解説

**Azure**
- [Azure for Students](https://azure.microsoft.com/free/students/): 学生向け特典の内容
- [Quickstart: Linux VM を portal で作成](https://learn.microsoft.com/azure/virtual-machines/linux/quick-create-portal): VM の作り方

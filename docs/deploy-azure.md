# Azure の仮想マシンで Bot を動かす

Azure for Students の仮想マシン (VM) に Ubuntu を入れ、Docker Compose で Bot を常時動かす手順です。
ラズパイ版 ([deploy.md](deploy.md)) と同じ構成なので、`main` の自動取り込みもバックアップもそのまま使えます。

所要時間: 初回は 45〜60分ほど

| 手順 | やること | 学べること |
|---|---|---|
| 1 | 予算アラートを設定する | クラウドの課金の仕組み、使いすぎの防止 |
| 2 | VM を作る | リージョン、VM のサイズ、ネットワークセキュリティグループ (ファイアウォール) |
| 3 | SSH で接続する | 公開鍵認証 |
| 4 | スワップと Docker を入れる | メモリ管理、パッケージ管理 (apt) |
| 5 | リポジトリを取ってくる | Deploy key (読み取り専用の鍵) |
| 6 | `.env` を置いて起動する | 秘密情報の扱い、コンテナ |
| 7 | 自動更新を設定する | systemd のタイマー |
| 8 | バックアップを手元に取る | バックアップの考え方 |

各手順の終わりに「確認」と書いたコマンドがあります。期待どおりに表示されてから次に進むと、どこで詰まったかが分かりやすくなります。

---

## ⚠️ 始める前に

- **同じトークンの Bot を2か所で動かさないでください。** Mac などで動かしている Bot は、手順6で起動する直前に止めます。2つ同時に動くと、自動投稿が二重になります。
- **料金について:**
  - Azure for Students では、クレジットカードなしでクレジットが付与されます。
  - 一部のサービスは、一定量まで無料で使えます。
  - 無料になる VM のサイズや量、期限は変わることがあります。作成画面の表示と、portal の「コストの管理」で必ず確認してください。
  - クレジットや期限が切れると、VM は止まります。

---

## 1. 予算アラートを設定する (最初にやる)

使いすぎに気づけるよう、VM を作る前に設定しておきます。

1. [Azure portal](https://portal.azure.com/) にサインインする。
   - [Azure for Students](https://azure.microsoft.com/free/students/) をまだ有効にしていない場合は、先に有効にしてください。
2. 上の検索欄で **「コストの管理と請求」** を開く。
3. **予算** →「追加」から、次のように設定する。
   - スコープ: Azure for Students のサブスクリプション
   - 金額: 例として月 $5
4. アラートを「実際のコストの 50% と 100%」で設定し、自分のメールアドレスに届くようにする。

**確認:** 予算の一覧に、作った予算が表示されれば OK です。

---

## 2. VM を作る

portal の検索欄で **「仮想マシン」** を開き、「作成」→「Azure 仮想マシン」を選びます。

### 「基本」タブ

| 項目 | 設定 |
|---|---|
| サブスクリプション | Azure for Students |
| リソースグループ | 「新規作成」→ `atcoder-bot-rg`。Bot に関するものは全部ここに入るので、後で片付けやすい |
| 仮想マシン名 | `atcoder-bot` |
| 地域 | **(Asia Pacific) Japan East**。選べない場合や、サイズが在庫切れの場合は Korea Central など近い地域 |
| 可用性オプション | インフラストラクチャ冗長は必要ありません |
| イメージ | **Ubuntu Server 24.04 LTS - x64 Gen2** |
| サイズ | **B1s** (1 vCPU / 1GB)。「無料サービスの対象」と表示されるサイズを選ぶ |
| 認証の種類 | **SSH 公開キー** |
| ユーザー名 | `azureuser` (このまま) |
| SSH 公開キーのソース | 「新しいキーの組を生成」→ 名前は `atcoder-bot-key` |
| パブリック受信ポート | 「選択したポートを許可する」→ **SSH (22) のみ** |

> 💡 Bot は Discord へ自分から接続するので、外からの接続を受ける必要がありません。開けるポートは SSH だけにします。

### 「ディスク」タブ

- OS ディスクの種類: **Standard SSD**。無料サービスの対象を確認してください。
- 「VM と共に削除」にチェックを入れる。

### 「管理」タブ

- **自動シャットダウン: オフにする。**
  オンのままだと毎晩 VM が止まり、Bot も止まります。

### 作成する

「確認および作成」→「作成」を押します。
**「秘密キーのダウンロードとリソースの作成」** が出たら、`atcoder-bot-key.pem` をダウンロードします。
このファイルは後から再ダウンロードできないので、なくさないでください。

**確認:** デプロイが完了したら「リソースに移動」を押し、**パブリック IP アドレス** をメモします。

### (おすすめ) SSH を自分の IP からだけ許可する

このままだと、世界中から SSH の接続を試されます。

1. VM の画面で「ネットワーク」→「ネットワーク設定」を開く。
2. SSH (22) の受信規則を開く。
3. **ソース** を「My IP address」に変える。

自宅と学校など、接続元が変わる場合は、その都度ここを直すか、規則を戻してください。

---

## 3. SSH で接続する

**Mac のターミナル**で、ダウンロードした鍵を `~/.ssh` に移して接続します。

```bash
mv ~/Downloads/atcoder-bot-key.pem ~/.ssh/
chmod 400 ~/.ssh/atcoder-bot-key.pem        # 自分しか読めないようにしないと ssh が使ってくれない
ssh -i ~/.ssh/atcoder-bot-key.pem azureuser@<パブリックIP>
```

初回は `Are you sure you want to continue connecting` と聞かれるので、`yes` と入力します。

毎回入力するのは大変なので、Mac の `~/.ssh/config` に次を追記しておくと、`ssh atcoder-azure` だけで接続できます。

```
Host atcoder-azure
  HostName <パブリックIP>
  User azureuser
  IdentityFile ~/.ssh/atcoder-bot-key.pem
```

**確認:** プロンプトが `azureuser@atcoder-bot:~$` になれば、接続できています。

---

## 4. スワップと Docker を入れる

ここからは **VM の中で**実行します。

B1s はメモリが 1GB しかありません。Docker のビルド (matplotlib などのインストール) の途中で足りなくなることがあるので、ディスクの一部をメモリの代わりに使う「スワップ」を 2GB 作ります。

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # 再起動しても有効にする
```

**確認:** `free -h` の `Swap:` の行が `2.0Gi` になっていれば OK です。

続けて、Docker を入れます。

```bash
sudo apt update && sudo apt full-upgrade -y
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
exit   # 一度ログアウトする
```

もう一度 `ssh atcoder-azure` で入り直します。入り直すと、`sudo` なしで `docker` が使えるようになります。

**確認:**

- `docker compose version`: バージョンが表示される
- `docker run --rm hello-world`: `Hello from Docker!` と表示される

---

## 5. リポジトリを取ってくる (Deploy key)

リポジトリは非公開なので、この VM 専用の **読み取り専用の鍵** を作って GitHub に登録します。

```bash
ssh-keygen -t ed25519 -f ~/.ssh/atcoder_bot_deploy -N "" -C "atcoder-bot@azure"
cat ~/.ssh/atcoder_bot_deploy.pub
```

表示された1行をコピーし、GitHub に登録します。

1. リポジトリの **Settings** → **Deploy keys** → **Add deploy key** を開く。
2. Title に `azure` と入れ、Key にコピーした1行を貼り付ける。
3. **Allow write access はチェックしない。**

VM に戻って、この鍵を使う設定をしてから clone します。

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/atcoder_bot_deploy
  IdentitiesOnly yes
EOF
ssh -T git@github.com
git clone git@github.com:Haruki07-crew/discord_bot_real.git ~/discord_bot_real
cd ~/discord_bot_real
```

`ssh -T` では、初回だけ `yes` と入力します。

**確認:** `ssh -T git@github.com` で `Hi Haruki07-crew/discord_bot_real! You've successfully authenticated` と出て、`ls` で `compose.yaml` が見えれば OK です。

---

## 6. `.env` を置いて起動する

**Mac のターミナル**で、`.env` を VM にコピーします。

```bash
cd ~/Documents/discord_bot/atcoder_bot
scp app/.env atcoder-azure:~/discord_bot_real/app/.env
```

`.env` には、少なくとも次の3つが書かれている必要があります。

- `DISCORD_TOKEN`
- `ADMIN_ID`
- `RANKING_CHANNEL_ID`

`=` の前後に空白を入れないでください (README の「4. `.env` に設定を書く」)。

### Mac で動かしているデータを引き継ぐ場合

Mac で `docker compose down` して Bot を止めてから、`data/` もコピーします。
こうすると、登録したメンバーと取得済みのデータを引き継げます。

```bash
scp -r data atcoder-azure:~/discord_bot_real/
```

引き継がない場合は、起動後に `/bulk_register` などでメンバーを登録し直してください。

### 起動する

**ほかの場所で動いている Bot を止めたことを確認してから**、**VM の中で**実行します。

```bash
cd ~/discord_bot_real
docker compose up -d --build     # 初回はビルドに 5〜15 分かかる
docker compose logs -f           # "activate the bot  now!!!!" が出れば成功 (Ctrl+C で抜ける)
```

**確認:**

- `docker compose ps` の STATUS が `Up ... (healthy)` になる。起動から2分ほどは `health: starting` と表示されます。
- Discord で `/syozin` と `/bot_status` が動く。

---

## 7. 自動更新を設定する

`main` が更新されたら、5分以内に自動で取り込んで作り直すようにします。
設定ファイルはラズパイ用 (ユーザー名 `pi`) なので、`azureuser` に書き換えてから登録します。

```bash
cd ~/discord_bot_real
sed -e 's#/home/pi/#/home/azureuser/#g' -e 's#^User=pi$#User=azureuser#' \
  deploy/atcoder-bot-update.service | sudo tee /etc/systemd/system/atcoder-bot-update.service
sudo cp deploy/atcoder-bot-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now atcoder-bot-update.timer
```

**確認:**

- `systemctl list-timers | grep atcoder` で、次の実行予定が表示される。
- `sudo systemctl start atcoder-bot-update && journalctl -u atcoder-bot-update -n 20` でエラーが出ていない。変更が無ければ、何も表示されずに終わります。

VM が再起動しても、Bot (`restart: unless-stopped`) とタイマーは自動で立ち上がります。

---

## 8. バックアップを手元にも取る

`data/backups/` には、毎日 1:00 に 14日分のバックアップがたまります。
ただし VM の中にあるので、VM を消すと一緒に消えます。ときどき **Mac で**コピーしておくと安心です。

```bash
scp -r atcoder-azure:~/discord_bot_real/data/backups ./atcoder-bot-backups
```

---

## よく使う操作

```bash
ssh atcoder-azure
cd ~/discord_bot_real
docker compose ps              # 動いているか (healthy なら正常)
docker compose logs -f         # ログを見る
docker compose restart         # 再起動
docker compose down            # 止める (データは data/ に残る)
docker compose up -d --build   # 手動で最新に作り直す
free -h && df -h /             # メモリとディスクの空き
```

### VM を止める・片付ける

止め方によって、料金のかかり方が変わります。

| やりたいこと | 方法 | 料金 |
|---|---|---|
| 一時的に止める | portal の VM 画面で「停止」 | 「停止済み (割り当て解除)」になれば、VM 本体の料金は止まる。ディスクとパブリック IP の料金はかかり続けることがある |
| 完全にやめる | portal で **リソースグループ `atcoder-bot-rg` を削除** | VM・ディスク・IP がまとめて消え、料金は発生しない |

完全にやめる前に、手順8でバックアップを取ってください。
`sudo shutdown` で VM の中から止めた場合は、料金は止まりません。

---

## 詰まったときは

| 症状 | 確認すること |
|---|---|
| `ssh: connect to host ... Connection timed out` | VM が起動しているか。受信規則を「My IP address」にした後に、IP が変わっていないか (手順2の最後) |
| `Permissions 0644 for '...pem' are too open` | `chmod 400 ~/.ssh/atcoder-bot-key.pem` を実行する |
| `Permission denied (publickey)` (VM への接続) | `-i` で正しい .pem を指定しているか。ユーザー名が `azureuser` か |
| サイズ B1s が選べない / 在庫が無い | 地域を変える (Japan West、Korea Central など) |
| `docker compose up --build` が途中で止まる / `Killed` | メモリ不足。スワップを作ったか (`free -h`) |
| `permission denied ... docker.sock` | `usermod -aG docker` のあとに、ログインし直したか |
| `git clone` で `Permission denied (publickey)` | Deploy key の登録と `~/.ssh/config` を確認する。`ssh -vT git@github.com` で詳しいログが出る |
| `env file ... not found` | `app/.env` を置いたか (手順6) |
| 毎晩 Bot が止まる | 「管理」タブの自動シャットダウンがオンのまま。VM の画面の「自動シャットダウン」でオフにする |
| 予算アラートのメールが来た | 「コストの管理」→「コスト分析」で、何に料金がかかっているかを見る |

---

## 参考リンク

- [Azure for Students](https://azure.microsoft.com/free/students/): 学生向け特典の内容とクレジット
- [Quickstart: Linux VM を portal で作成](https://learn.microsoft.com/azure/virtual-machines/linux/quick-create-portal): 手順2の公式版 (画面つき)
- [SSH キーで Linux VM に接続](https://learn.microsoft.com/azure/virtual-machines/linux-vm-connect): 手順3
- [予算を作成する](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets): 手順1
- [VM の自動シャットダウン](https://learn.microsoft.com/azure/virtual-machines/auto-shutdown-vm): 手順2の「管理」タブ
- [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/): 手順4の `get.docker.com` は、このページの "convenience script" のこと
- [Managing deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys): 手順5
- ラズパイ版の手順・共通の操作: [deploy.md](deploy.md)

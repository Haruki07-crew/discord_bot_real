# CLAUDE.md

AtCoder の精進 (AC数・点数) とレート変化を集計し、Discord にランキング・グラフを投稿する Bot。
利用者向けの説明は README.md、内部構成は docs/development.md、外部APIの仕様は docs/atcoder-api.md。

## コマンド

```bash
python -m unittest discover -s tests -v   # オフラインテスト (ネットワーク・Discord 不要)。変更後は必ず実行
python -m py_compile app/main.py          # 構文チェック (hook でも自動実行される)
cd app && python main.py                  # 起動 (本番トークンでは実行しないこと。下記参照)
docker compose up -d --build              # 本番と同じ構成で起動。本番はラズパイ5 / Azure VM (docs/deploy.md)
```

Python 3.11 (Docker と同じ)。依存は requirements.txt。pytest は使わず標準の unittest。

## 構成

- `app/main.py` — スラッシュコマンド、自動タスク (`tasks.loop`)、Embed 分割などのヘルパー
- `app/atcoder/` — 1関数1ファイル。`__init__.py` で re-export し、main.py は `from atcoder import *`
  - 新しい関数を足したら `__init__.py` の import と `__all__` の両方に追加する
- `app/config.py` — 環境変数 (`DISCORD_TOKEN` `ADMIN_ID` `RANKING_CHANNEL_ID` `LOG_CHANNEL_ID` `DB_PATH`)
- `app/atcoder/background_sync.py` — データは Bot 内で1人ずつ同期し続ける。**コマンドの中で全員分を取り直さない** (人数に比例して遅くなる)
- `app/atcoder/http_client.py` — 外部APIへのリクエストはすべてここを通す (同じホストへは1秒に1回まで)
- `app/discord_logger.py` — API 呼び出しログを5秒ごとにまとめて Discord に送る (処理は送信を待たない)
- `tests/` — `support.py` が main.py を Discord に接続せずに読み込む。偽の Channel / Interaction を使う
- DB は SQLite 1ファイル (`DB_PATH`)。テーブル定義は `app/atcoder/init_*.py`

## 絶対に守ること

- **外部APIは同じホストに1秒に1回まで。** atcoder.jp と kenkoooo.com はどちらも善意で公開されている。
  ループで叩く場合は必ず間隔を空け、ユーザー数に比例してリクエストが増える設計は避ける。
  詳細と検証済みの仕様は docs/atcoder-api.md。
- **本番トークンでローカル起動しない。** 本番の Bot と2つ同時に動き、自動投稿が二重になる。
  動作確認は tests/ のオフラインテストか、テスト用 Bot のトークンで行う。
- **`.env` と `database.db` をコミットしない** (.gitignore 済み)。トークンをコードやログに書かない。
- **main への push = 本番デプロイ** (本番機が5分ごとに main を取り込む)。 必ずブランチ → テスト → PR → マージの順で行う (`/ship` skill)。

## コードの書き方

- インデントは2スペース。コメントとユーザー向けメッセージは日本語。
- コマンドは `await interaction.response.defer()` してから処理し、例外は `report_command_error()` に渡す
  (記録・管理者への DM・実行者へのエラー表示をまとめて行う)。新規作成は `/add-command` skill を参照。
- 自動タスクの失敗は `alerts.notify_admin(key, text)` で管理者に知らせる (同じ key は cooldown に1回)。
- Embed は直接作らない。コマンドの返信は `build_pages()` + `send_pages_to_interaction()` (1ページ10人、ボタンで切替)、自動投稿は `top_fields()` + `ranking_text_file()` (上位10人 + 全順位の添付)。人数が増えても連投にならないようにする。
- 投稿の送信は失敗しうる。自動投稿は `send_with_retry()` を使い、送信成功後に状態 (prev_contest など) を進める。
- 期間は `get_period_start_unix(day)` に統一する。「今日を含めて day 日分」。
- AC の数え方 (決定済み): 総合AC = (問題, JSTの日付) ごとに1回 (別の日の解き直しは数える)、新規AC = 期間内に初めて AC した問題。`count_period_ac` が [総合AC, 点数, 新規AC] を返す。
- DB には `from atcoder import db` → `with db.connect(db_file) as conn:` で接続する (`sqlite3.connect` を直接 with で使うと接続が閉じない)。
- 依存パッケージは requirements.txt でバージョンを固定している。上げるときは Python 3.11 でテストを通してから。
- AtCoder のユーザー名は大文字小文字を区別しない。比較は `COLLATE NOCASE` か `.lower()`。
- ユーザー入力の AtCoder 名は URL に入れる前に `is_valid_atcoder_name()` で検査する。

## 既知の課題 (直すときは別PRで)


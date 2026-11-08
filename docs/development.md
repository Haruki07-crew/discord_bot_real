# 開発者向けドキュメント

導入方法・コマンドの使い方は [README](../README.md) を参照。ここでは内部の構成と処理の流れをまとめる。

---

## ディレクトリ構成

```
app/
  main.py                 Botのエントリーポイント。スラッシュコマンド・自動タスクの定義
  config.py               環境変数の読み込み (DISCORD_TOKEN, ADMIN_ID, RANKING_CHANNEL_ID, LOG_CHANNEL_ID, DB_PATH)
  server.py               ヘルスチェック用HTTPサーバー (FastAPI + uvicorn, デーモンスレッド)
  alerts.py               管理者への DM 通知 (同じ key は cooldown 秒に1回) と直近のエラーの記録
  discord_logger.py       API呼び出しをDiscordチャンネルにログ出力するユーティリティ
  database.db             SQLiteデータベース (実行時に自動生成。DB_PATH で場所を変更可)
  .env                    環境変数ファイル

  atcoder/
    __init__.py            全モジュールの re-export
    init_db.py             DB初期化のエントリーポイント
    init_progress_tables.py  テーブル作成 (contest_history, ac_submissions_cache, update_bookmark, weekly_snapshots, weekly_cycle)
    init_auto_post_table.py  テーブル作成 (auto_posted_contests, bot_state)

    --- ユーザー管理 ---
    register_user.py       ユーザー登録 (INSERT)
    delete_user.py         ユーザー削除 (DELETE)
    get_user_dict.py       全ユーザーの {atcoder_name: discord_name} 辞書を返す
    get_registered_user.py 指定ユーザーの登録情報を返す (二重登録チェック用)
    get_register_id.py     登録者IDを返す (解除権限チェック用)
    verification.py        本人確認 (確認コードの発行・期限管理、プロフィールの所属欄にコードがあるかの確認)
    get_registered_by_discord_id.py  その Discord ユーザーが自分で登録した AtCoder 名を返す (1人1アカウント制限用)

    --- データ取得・キャッシュ ---
    background_sync.py                 バックグラウンド同期 (sync_step)。一番古いユーザーから1人ずつ提出・コンテスト履歴を更新
    http_client.py                     外部APIへのリクエストを集約。同じホストへは Bot 全体で1秒に1回まで
    initial_fetch_user_data.py        コンテスト履歴 + AC提出を一括取得 / refresh_users_data (集計前の差分更新)
    atcoder_user_exists.py            ユーザーページの404でAtCoderユーザーの存在を確認
    fetch_and_cache_contest_history.py コンテスト履歴をAtCoder APIから取得しDBにキャッシュ
    fetch_and_cache_ac_submissions.py  AC提出をkenkoooo APIから取得しDBにキャッシュ
    get_ac_count.py                    総AC数を返す (DBキャッシュ優先、なければAPI)
    count_period_ac.py                 指定期間の [総合AC, 点数, 新規AC] を返す (総合ACは問題・JST日付ごとに1回)
    get_latest_rating_from_db.py       DBキャッシュから最新レートを返す
    get_rate_heart.py                  レート値に応じたハート絵文字を返す
    parse_atcoder_time.py              AtCoderの日時文字列をdatetimeに変換
    get_ac_streak.py                   昨日から遡って何日連続でACしているかを返す (今日は含めない)

    --- ランキング生成 ---
    AC_fight.py              全ユーザーのAC数を取得し降順ソートしたリストを返す
    make_growth_ranking.py   レート変化(第1キー) + AC数(第2キー) でランキングを生成
    get_ac_rate_change_data.py  全ユーザーの期間内AC数・レート変化を辞書で返す

    --- グラフ生成 ---
    create_ac_rate_graph.py    散布図 (横軸: AC数, 縦軸: レート変化)。7日以内の期間で使用
    create_progress_graph.py   折れ線グラフ (横軸: AC数, 縦軸: レート)。8日以上の期間で使用
    create_weekly_graph.py     累積折れ線グラフ (12週サイクル)。週次自動投稿で使用
    get_progress_data.py       期間内のコンテスト参加ポイント列 [(ac_count, rating), ...] を返す

    --- ABC コンテスト ---
    get_abc_standings.py             指定ABCの結果を取得し、登録ユーザーをrated/unratedに分類
    fetch_abc_standings_if_ready.py  ABC結果がレート確定済みか判定し、確定時のみ結果を返す
    build_abc_standings.py           results/jsonから登録ユーザーを抽出 (上2つの共通処理。参加者の提出キャッシュを更新してからAC数を数える)
    get_contest_ac_count.py          コンテスト中のAC数をac_submissions_cacheからカウント
    get_prev_contest.py              最後に処理したABCコンテスト番号を取得
    set_prev_contest.py              最後に処理したABCコンテスト番号を保存
    get_latest_ended_abc_number.py   直近の終了済みABC番号をAPIから取得

    --- 週次サイクル ---
    weekly_cycle_helpers.py   12週サイクルの管理、スナップショットの保存・取得

    --- その他 ---
```

---

## 表示の共通ルール

- コマンドの返信は `build_pages()` で1ページ10人に分け、`send_pages_to_interaction()` で送る。2ページ以上なら `PageView` (◀ ▶ ボタン、15分で無効) を付ける。
- 自動投稿は `top_fields()` で上位10人 + 「ほか N 人」にし、11人以上なら `ranking_text_file()` で全順位を .txt で添付する (再起動でボタンが効かなくなるため、自動投稿にはボタンを使わない)。
- グラフは `graph_targets()` (上位10人 + 実行した本人) だけを描く。

## おすすめ・通知・実績

- `atcoder/problem_data.py`: 難易度と問題一覧の取得 (1日1回)、色、精進スコア
- `atcoder/engagement.py`: おすすめ、スコア集計、レート進捗、次の壁
- `atcoder/notifications.py`: `notification_prefs` / `achievements` テーブル、DM 希望、アカウントの紐づけ
- `atcoder/achievements.py`: 実績の判定。初回判定のユーザーは過去の分を投稿せず記録する (`_initialized`)。投稿に成功してから記録する
- `atcoder/contest_reminder.py`: atcoder.jp の予定表を1時間に1回読み、開始30分前に投稿する (送信済みは `auto_posted_contests` の `reminder:abcNNN`)
- 定期処理: `abc_reminder_task` (1分) / `achievements_task` (30分) / `streak_reminder_task` (毎日22時) / `weekly_review_task` (月曜9時)

## 監視

- コマンドの例外は `report_command_error()` で記録・管理者に DM・実行者にエラー表示をまとめて行う。新しいコマンドもこれを使う。
- 自動タスク (週次・ABC・同期) の失敗も `alerts.notify_admin()` で知らせる。同期は連続10回失敗で通知し、成功したら復旧を通知する。
- `server.py` の `/health` は `bot_health()` を使い、Discord 切断か同期の連続失敗で 503 を返す。compose.yaml の healthcheck が1分ごとに見る。
- `/bot_status` (管理者のみ、本人にだけ表示) で状態と直近5件のエラーを確認できる。

## スラッシュコマンド一覧

### /syozin

指定ユーザーの精進記録を表示する。

| パラメータ | 型 | 説明 |
|---|---|---|
| atcoder_name | str | AtCoderユーザー名 |

表示内容: 今日の総合AC・新規AC・獲得点数、これまでに解いた問題数

登録済みユーザーの場合は、表示前に提出キャッシュを差分更新する。

### /user_register

AtCoderユーザーをBotに登録する。管理者以外は1人1アカウントまで (自分が登録した行が既にあれば拒否)。

| パラメータ | 型 | 説明 |
|---|---|---|
| atcoder_name | str | AtCoderユーザー名 |
| discord_name | str (省略可) | ランキングに表示する名前。省略時は Discord の表示名 |

処理: AtCoder APIでユーザー存在確認 -> DB登録 -> コンテスト履歴・AC提出を全件取得してキャッシュ

### /user_verify

`REQUIRE_ATCODER_VERIFICATION=true` のとき、`/user_register` (管理者以外) は登録せずに確認コードを発行し、`pending_verifications` に保存する (有効期限1時間)。
`/user_verify` は `atcoder.jp/users/{name}` の所属欄 (Affiliation / 所属) にコードがあれば登録を完了する。

### /user_unregister

登録を解除する。登録者本人またはadminのみ実行可能。そのユーザーの提出・コンテスト履歴のキャッシュも削除する。

| パラメータ | 型 | 説明 |
|---|---|---|
| atcoder_name | str | AtCoderユーザー名 (オートコンプリート対応) |

### /user_list

登録ユーザーの一覧と最新レートを表示する。レート帯に応じたハート色で装飾する。

### /everyone_state

全登録ユーザーの総AC数と連続AC日数を一覧表示する。
バックグラウンド同期済みのデータを読むだけ (フッターに何分前のデータかを表示)。

表示内容: 各ユーザーの総AC数、昨日から遡って何日連続でACしているか (今日の分は含めない)

ソート: 連続AC日数(降順) -> 総AC数(降順)

### /diligence_growth

指定期間のレート変化とAC数のランキングを表示する。期間は今日を含めた日数 (1日 = 今日の0:00から、1週間 = 6日前の0:00から)。

| パラメータ | 型 | 選択肢 |
|---|---|---|
| period | Choice | 1日 / 1週間 / 1ヶ月 / 3ヶ月 / 半年 / 1年 |

ソート: レート変化(降順) -> AC数(降順)

バックグラウンド同期済みのデータを読むだけ (フッターに何分前のデータかを表示)。

グラフ:
- 7日以内: 散布図 (横軸: AC数, 縦軸: レート変化)
- 8日以上: 折れ線グラフ (横軸: AC数, 縦軸: レート)

### /diligence_growth_point

/diligence_growth の点数版。横軸がAC数ではなく獲得点数になる。

| パラメータ | 型 | 選択肢 |
|---|---|---|
| period | Choice | 1日 / 1週間 / 1ヶ月 / 3ヶ月 / 半年 / 1年 |

ソート: レート変化(降順) -> 点数(降順)

### /abc_ranking

指定したABCコンテストの登録ユーザーランキングを表示する。

| パラメータ | 型 | 説明 |
|---|---|---|
| contest_number | int | ABCのコンテスト番号 (1-999) |

表示内容: 順位、コンテスト中のAC数、パフォーマンス、レート変化、rated/unrated分類

コンテスト中のAC数は ac_submissions_cache から算出する (コンテスト終了時刻 - 100分 の範囲)。
終了時刻は results/json の EndTime を使い、集計前に参加者の提出キャッシュを差分更新する。

---

## 一括登録 (/bulk_register)

管理者が `/bulk_register group:...` を実行すると、`BULK_GROUPS` (main.py の TEST_USERS / OTHER_KOSEN_USERS) をまとめて登録する。
以前はメッセージ本文で動かしていたが、Message Content Intent が必要になるためスラッシュコマンドにした。
Bot は `discord.Intents.default()` で動き、特別な許可が必要な Intents は使わない。

---

## 自動タスク

### background_sync

1秒ごとに `sync_step()` を実行する。提出 (kenkoooo) とコンテスト履歴 (atcoder.jp) について、同期が一番古いユーザーを1人ずつ更新する。

- 提出は5分ごと、コンテスト履歴は24時間ごとが目安。ABC の自動投稿後は、参加者のコンテスト履歴を優先して取り直す (`request_contest_resync`)。
- 取得に失敗した種類は60秒止める (落ちている API を叩き続けない)。
- ホストごとに1秒に1回の制限は http_client が守る。1000人なら一巡約17分。
- コマンドは DB を読むだけ。`/syozin` で登録済みユーザーを指定したときだけ、その1人をその場で更新する。

### daily_update

毎日 1:00 JST に DB を `<DBのフォルダ>/backups/` にバックアップする (14日分)。

### weekly_ranking_post

毎週月曜 0:15 JST に実行。日曜深夜の提出やレート確定を確実に含めるため、集計前に全登録ユーザーを更新する (コンテスト履歴は必ず取り直す)。
同じ日に二重に実行されても週番号が進まないよう、`bot_state` の `weekly_last_posted` に投稿日を記録する。

1. 直近1週間のAC数・点数・レート変化のランキングをテキストで投稿
2. 12週サイクルの累積折れ線グラフを2枚投稿
   - AC数版: 横軸=累積AC数, 縦軸=累積レート変化
   - 点数版: 横軸=累積点数, 縦軸=累積レート変化

各週のデータは `weekly_snapshots` テーブルに保存される。12週経過後はサイクルIDが進み、グラフは0からリセットされる。

### auto_abc_ranking

1時間ごとに実行。前回処理したABC番号 (`prev_contest`) の次のコンテスト結果をAtCoder APIで確認し、レート確定済みであれば登録ユーザーのランキングを自動投稿する。投稿に成功してから `prev_contest` を更新する (送信に失敗した場合は次の実行で再試行)。

`prev_contest` が未設定の場合は、kenkoooo のコンテスト一覧から直近に終了したABC番号を取得して初期化する。取得できなかった場合は初期化せず次の実行で再試行する (固定値で初期化すると古いABCが連投されるため)。

---

## データベース設計

DB: SQLite (`database.db`)

### users

ユーザー登録情報。

| カラム | 型 | 説明 |
|---|---|---|
| atcoder_name | TEXT (PK) | AtCoderユーザー名 |
| discord_name | TEXT | Discordの表示名 |
| discord_id | INTEGER | DiscordユーザーID |
| register_id | INTEGER | 登録操作を行ったユーザーのDiscord ID |

### contest_history

AtCoderのRatedコンテスト参加履歴。

| カラム | 型 | 説明 |
|---|---|---|
| atcoder_name | TEXT (PK) | AtCoderユーザー名 |
| contest_screen_name | TEXT (PK) | コンテスト識別名 |
| end_time | TEXT | コンテスト終了時刻 |
| new_rating | INTEGER | コンテスト後のレート |
| old_rating | INTEGER | コンテスト前のレート |

### ac_submissions_cache

AC (正解) 提出のキャッシュ。

| カラム | 型 | 説明 |
|---|---|---|
| atcoder_name | TEXT (PK) | AtCoderユーザー名 |
| submission_id | INTEGER (PK) | 提出ID |
| problem_id | TEXT | 問題ID |
| epoch_second | INTEGER | 提出時刻 (Unix秒) |
| point | INTEGER | 獲得点数 |

### update_bookmark

データ取得の進捗管理。差分取得に使用する。

| カラム | 型 | 説明 |
|---|---|---|
| atcoder_name | TEXT (PK) | AtCoderユーザー名 |
| contest_last_fetched | REAL | コンテスト履歴の最終取得時刻 (Unix秒) |
| submission_last_id | INTEGER | 最後に取得した提出ID |
| submission_cache_from | REAL | キャッシュの開始epoch |
| submission_last_fetch | REAL | 最終取得時刻 (Unix秒) |

### weekly_snapshots

週次自動投稿用のスナップショット。12週サイクルのグラフ描画に使用する。

| カラム | 型 | 説明 |
|---|---|---|
| cycle_id | INTEGER (PK) | サイクル番号 (12週ごとに増加) |
| week_number | INTEGER (PK) | 週番号 (1-12) |
| atcoder_name | TEXT (PK) | AtCoderユーザー名 |
| ac_count | INTEGER | その週のAC数 |
| ac_point | INTEGER | その週の獲得点数 |
| rate_change | INTEGER | その週のレート変化 |

### weekly_cycle

現在の週次サイクル状態を管理する (レコードは常に1行)。

| カラム | 型 | 説明 |
|---|---|---|
| id | INTEGER (PK) | 常に1 |
| cycle_id | INTEGER | 現在のサイクル番号 |
| current_week | INTEGER | 現在の週番号 (0: 初期状態, 1-12: 進行中) |

### bot_state

Bot全体のキーバリューストア。現在は `prev_contest` の管理に使用。

| カラム | 型 | 説明 |
|---|---|---|
| key | TEXT (PK) | キー名 |
| value | TEXT | 値 |

### auto_posted_contests

自動投稿済みのコンテストを記録し、二重投稿を防止する。

| カラム | 型 | 説明 |
|---|---|---|
| contest_id | TEXT (PK) | コンテストID (例: "abc450") |
| posted_at | REAL | 投稿時刻 (Unix秒) |

---

## 外部API

### AtCoder API

| エンドポイント | 用途 | 呼び出し元 |
|---|---|---|
| `atcoder.jp/users/{user}` | ユーザー存在確認 (存在しなければ404) | atcoder_user_exists |
| `atcoder.jp/users/{user}/history/json` | コンテスト履歴・レート取得 (存在しないユーザーでも 200 [] を返すため存在確認には使えない) | fetch_and_cache_contest_history |
| `atcoder.jp/contests/{id}/results/json` | コンテスト結果 (順位・パフォーマンス) | get_abc_standings, fetch_abc_standings_if_ready |

注意事項:
- User-Agentヘッダーを付与している
- パフォーマンス値が負の場合は0に補正する (低パフォーマンス時のAPI仕様対応)

### kenkoooo AtCoder Problems API

| エンドポイント | 用途 | 呼び出し元 |
|---|---|---|
| `kenkoooo.com/atcoder/atcoder-api/v3/user/submissions` | ユーザーのAC提出一覧 | fetch_and_cache_ac_submissions, count_period_ac |
| `kenkoooo.com/atcoder/atcoder-api/v3/user/ac_rank` | 総AC数 | get_ac_count |
| `kenkoooo.com/atcoder/resources/contests.json` | コンテスト一覧 | get_latest_ended_abc_number |

注意事項:
- ページネーション: 1回最大500件。`from_id` は無視されるため `from_second` を進めてページ送りする。間隔は http_client が1秒空ける
- 差分取得は最終提出時刻の24時間前から取り直す (kenkoooo が提出を遅れて取り込むことがあるため。重複は INSERT OR IGNORE で除外)
- AHC (AtCoder Heuristic Contest) の問題はproblem_idに "ahc" を含むため除外している
- レスポンスは `content_type=None` で解析 (サーバーのContent-Typeが不安定なため)

### 共通のAPIハンドリング

- 全API呼び出しは `atcoder/http_client.py` を通す。同じホストへのリクエストは Bot 全体で1秒に1回までに制限される
- 全API呼び出しに30秒のタイムアウトを設定 (connect: 10秒, read: 20秒)
- API呼び出しはdiscord_loggerで記録され、5秒ごとにまとめて指定チャンネルに送信される (本来の処理は送信を待たない)
- DBキャッシュの有効期間: コンテスト履歴は600秒 (10分、週次集計の直前は必ず取り直す)、AC提出は60秒

---

## データフロー

### ユーザー登録時

```
/user_register
  -> atcoder_user_exists()           ... AtCoderユーザーページでユーザー存在確認
  -> register_user()                 ... usersテーブルにINSERT
  -> initial_fetch_user_data()
      -> fetch_and_cache_contest_history()  ... コンテスト履歴を全件取得しDBに保存
      -> fetch_and_cache_ac_submissions()   ... AC提出を全件取得しDBに保存
```

### バックグラウンド同期 (background_sync, 1秒ごと)

```
background_sync
  -> sync_step()
      -> 提出の同期が5分以上前のユーザーのうち最も古い1人 -> fetch_and_cache_ac_submissions()
      -> コンテスト履歴が24時間以上前 (または再取得要求あり) の最も古い1人 -> fetch_and_cache_contest_history(force=True)
```

### 週次ランキング投稿 (weekly_ranking_post, 毎週月曜 0:15 JST)

```
weekly_ranking_post
  -> refresh_users_data(force_contest=True)  ... 全ユーザーのキャッシュを差分更新 (コンテスト履歴は必ず取り直す)
  -> make_growth_ranking(day=8, end_unix=今日0:00)  ... 先週月曜0:00〜今週月曜0:00 のランキングを生成
      -> AC_fight()                 ... 各ユーザーのAC数・点数を取得
          -> count_period_ac()      ... DBキャッシュから期間AC数を集計
      -> get_ac_rate_change_data()  ... 各ユーザーのレート変化を計算
  -> advance_weekly_cycle()         ... 週番号を進める (12週でリセット)
  -> save_weekly_snapshot()         ... 今週のデータをDBに保存
  -> get_weekly_snapshots()         ... サイクル全体のデータを取得
  -> create_weekly_graph(x_axis="ac")     ... AC数版の累積折れ線グラフを生成
  -> create_weekly_graph(x_axis="point")  ... 点数版の累積折れ線グラフを生成
  -> Discordに投稿 (テキスト + グラフ2枚)
```

### ABC自動ランキング (auto_abc_ranking, 1時間ごと)

```
auto_abc_ranking
  -> ensure_prev_contest()                ... 前回処理したABC番号を取得 (未設定ならAPIで初期化)
  -> fetch_abc_standings_if_ready()       ... 次のABCの結果を確認
      -> AtCoder results/json API         ... レート確定済みか判定 (unrated になった回は終了24時間後に確定扱い)
      -> build_abc_standings()
          -> fetch_and_cache_ac_submissions()  ... 参加者の提出キャッシュを差分更新
          -> get_contest_ac_count()            ... コンテスト中のAC数をDBから算出
      (全員のAC数が0なら kenkoooo の取り込み待ちとみなし、終了から48時間までは投稿を見送る)
  -> Discordに投稿 (rated/unrated分類のランキング + AC数)
  -> set_prev_contest()                   ... 投稿成功後にABC番号を更新
```

### 精進状況表示 (/everyone_state)

```
/everyone_state
  -> get_user_dict()       ... 全登録ユーザーを取得
  -> get_ac_count()        ... 各ユーザーの総AC数を取得
  -> get_ac_streak()       ... 各ユーザーの連続AC日数を算出
```

---

## 環境変数・起動

環境変数の一覧と起動方法は [README の導入手順](../README.md#導入手順) を参照。

起動時の処理 (on_ready):
1. DBの全テーブルを初期化 (init_db)
2. バックグラウンドタスクを開始 (background_sync, daily_update, weekly_ranking_post, auto_abc_ranking)
3. スラッシュコマンドをDiscordに同期 (tree.sync)。起動後1回だけ行い、失敗しても続行する
4. ログ出力用チャンネルを設定
5. prev_contestが未設定の場合、APIから直近のABC番号を取得して初期化 (失敗時は auto_abc_ranking で再試行)
6. 月曜0:15以降に起動し週次投稿が未実施なら、別タスクで週次投稿を行う

ヘルスチェック用HTTPサーバー (server.py) は client.run の前にデーモンスレッドで起動する。

## テスト

```bash
python -m unittest discover -s tests -v
```

- `tests/support.py` が main.py を Discord に接続せずに読み込む (`server_thread()` と `client.run()` を除いて exec)。
- コマンドは `ns["コマンド名"].callback(FakeInteraction, ...)`、タスクは `ns["タスク名"].coro()` で実行する。
- `tests/test_offline.py` はネットワークに出ない。GitHub Actions (.github/workflows/test.yml) で PR ごとに実行される。

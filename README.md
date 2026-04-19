# AtCoder 精進管理 Discord Bot

AtCoderの精進記録・コンテスト結果・レート変化を自動で収集し、Discord上でランキングやグラフとして配信するBot。

---

## ディレクトリ構成

```
app/
  main.py                 Botのエントリーポイント。スラッシュコマンド・自動タスクの定義
  config.py               環境変数の読み込み (DISCORD_TOKEN, ADMIN_ID, RANKING_CHANNEL_ID)
  server.py               ヘルスチェック用HTTPサーバー (FastAPI + uvicorn, デーモンスレッド)
  discord_logger.py       API呼び出しをDiscordチャンネルにログ出力するユーティリティ
  database.db             SQLiteデータベース (実行時に自動生成)
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
    get_all_users_with_discord_id.py  全ユーザーの (atcoder_name, discord_name, discord_id) を返す

    --- データ取得・キャッシュ ---
    initial_fetch_user_data.py        コンテスト履歴 + AC提出を一括取得
    fetch_and_cache_contest_history.py コンテスト履歴をAtCoder APIから取得しDBにキャッシュ
    fetch_and_cache_ac_submissions.py  AC提出をkenkoooo APIから取得しDBにキャッシュ
    get_ac_count.py                    総AC数を返す (DBキャッシュ優先、なければAPI)
    count_period_ac.py                 指定期間のAC数と合計点数を返す [ac_count, point_sum]
    count_period_ac2.py                count_period_acの拡張版 (難易度合計も返す)
    get_latest_rating.py               AtCoder APIから現在のレートを文字列で返す
    get_latest_rating_nofstring.py     AtCoder APIから現在のレートを数値で返す
    get_latest_rating_from_db.py       DBキャッシュから最新レートを返す
    get_rate_heart.py                  レート値に応じたハート絵文字を返す
    parse_atcoder_time.py              AtCoderの日時文字列をdatetimeに変換
    get_ac_streak.py                   今日から遡って何日連続でACしているかを返す

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
    get_contest_ac_count.py          コンテスト中のAC数をac_submissions_cacheからカウント
    get_contest_end_time.py          contest_historyからコンテスト終了時刻を取得
    get_prev_contest.py              最後に処理したABCコンテスト番号を取得
    set_prev_contest.py              最後に処理したABCコンテスト番号を保存
    get_latest_ended_abc_number.py   直近の終了済みABC番号をAPIから取得
    is_contest_auto_posted.py        自動投稿済みかどうかを判定
    mark_contest_auto_posted.py      自動投稿済みとしてマーク

    --- 週次サイクル ---
    weekly_cycle_helpers.py   12週サイクルの管理、スナップショットの保存・取得

    --- その他 ---
    fetch_problem.py   kenkoooo の problem-models.json を取得しキャッシュ
    get_diff.py        問題の生difficulty値を加工して返す
```

---

## スラッシュコマンド一覧

### /syozin

指定ユーザーの精進記録を表示する。

| パラメータ | 型 | 説明 |
|---|---|---|
| atcoder_name | str | AtCoderユーザー名 |

表示内容: 通算AC数、今日のAC数、今日の獲得点数

### /user_register

AtCoderユーザーをBotに登録する。

| パラメータ | 型 | 説明 |
|---|---|---|
| atcoder_name | str | AtCoderユーザー名 |
| discord_name | str | Discordの表示名 (手動入力) |

処理: AtCoder APIでユーザー存在確認 -> DB登録 -> コンテスト履歴・AC提出を全件取得してキャッシュ

### /user_unregister

登録を解除する。登録者本人またはadminのみ実行可能。

| パラメータ | 型 | 説明 |
|---|---|---|
| atcoder_name | str | AtCoderユーザー名 (オートコンプリート対応) |

### /user_list

登録ユーザーの一覧と最新レートを表示する。レート帯に応じたハート色で装飾する。

### /everyone_state

全登録ユーザーの総AC数と連続AC日数を一覧表示する。
データはdaily_update (毎日 1:00 JST) で更新されるキャッシュをもとに計算する。

表示内容: 各ユーザーの総AC数、今日から遡って何日連続でACしているか

### /diligence_growth

指定期間のレート変化とAC数のランキングを表示する。

| パラメータ | 型 | 選択肢 |
|---|---|---|
| period | Choice | 1日 / 1週間 / 1ヶ月 / 3ヶ月 / 半年 / 1年 |

ソート: レート変化(降順) -> AC数(降順)

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

---

## 一括登録メッセージ

ADMIN_IDのユーザーが特定のメッセージを送信すると、事前定義されたユーザーを一括登録する。

| メッセージ | 対象 |
|---|---|
| テスト用にユーザー登録 | TEST_USERS (11人) - メインメンバー |
| 他高専テスト用に登録 | OTHER_KOSEN_USERS (9人) - 他高専メンバー |

---

## 自動タスク

### daily_update

毎日 1:00 JST に実行。全登録ユーザーのコンテスト履歴とAC提出をAPIから取得し、DBキャッシュを更新する。ユーザー間で1.5秒のインターバルを入れてAPIレート制限を回避する。

### weekly_ranking_post

毎週月曜 0:15 JST に実行。

1. 直近1週間のAC数・点数・レート変化のランキングをテキストで投稿
2. 12週サイクルの累積折れ線グラフを2枚投稿
   - AC数版: 横軸=累積AC数, 縦軸=累積レート変化
   - 点数版: 横軸=累積点数, 縦軸=累積レート変化

各週のデータは `weekly_snapshots` テーブルに保存される。12週経過後はサイクルIDが進み、グラフは0からリセットされる。

### auto_abc_ranking

毎日 1:05 JST に実行。前回処理したABC番号 (初期値: 455) の次のコンテスト結果をAtCoder APIで確認し、レート確定済みであれば登録ユーザーのランキングを自動投稿する。投稿後は `prev_contest` を更新して二重投稿を防止する。

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
| `atcoder.jp/users/{user}/history/json` | コンテスト履歴・レート取得 | fetch_and_cache_contest_history, get_latest_rating, get_latest_rating_nofstring |
| `atcoder.jp/contests/{id}/results/json` | コンテスト結果 (順位・パフォーマンス) | get_abc_standings, fetch_abc_standings_if_ready |

注意事項:
- User-Agentヘッダーを付与している
- パフォーマンス値が負の場合は0に補正する (低パフォーマンス時のAPI仕様対応)

### kenkoooo AtCoder Problems API

| エンドポイント | 用途 | 呼び出し元 |
|---|---|---|
| `kenkoooo.com/atcoder/atcoder-api/v3/user/submissions` | ユーザーのAC提出一覧 | fetch_and_cache_ac_submissions, count_period_ac, count_period_ac2 |
| `kenkoooo.com/atcoder/atcoder-api/v3/user/ac_rank` | 総AC数 | get_ac_count |
| `kenkoooo.com/atcoder/resources/contests.json` | コンテスト一覧 | get_latest_ended_abc_number |
| `kenkoooo.com/atcoder/resources/problem-models.json` | 問題の難易度モデル | fetch_problem |

注意事項:
- ページネーション: 1回500件、`from_id`で差分取得。ページ間に0.8秒のインターバル
- AHC (AtCoder Heuristic Contest) の問題はproblem_idに "ahc" を含むため除外している
- レスポンスは `content_type=None` で解析 (サーバーのContent-Typeが不安定なため)

### 共通のAPIハンドリング

- 全API呼び出しに30秒のタイムアウトを設定 (connect: 10秒, read: 20秒)
- API呼び出しはdiscord_loggerで記録され、指定チャンネルにログが送信される
- DBキャッシュの有効期間: コンテスト履歴は3600秒 (1時間)、AC提出は60秒

---

## データフロー

### ユーザー登録時

```
/user_register
  -> get_latest_rating_nofstring()   ... AtCoder APIでユーザー存在確認
  -> register_user()                 ... usersテーブルにINSERT
  -> initial_fetch_user_data()
      -> fetch_and_cache_contest_history()  ... コンテスト履歴を全件取得しDBに保存
      -> fetch_and_cache_ac_submissions()   ... AC提出を全件取得しDBに保存
```

### 日次データ更新 (daily_update, 毎日 1:00 JST)

```
daily_update
  -> get_user_dict()                ... 全登録ユーザーを取得
  -> initial_fetch_user_data()      ... 各ユーザーの差分データを取得
      -> fetch_and_cache_contest_history()  ... 前回から1時間以上経過していれば再取得
      -> fetch_and_cache_ac_submissions()   ... 前回の最終提出IDから差分取得
```

### 週次ランキング投稿 (weekly_ranking_post, 毎週月曜 0:15 JST)

```
weekly_ranking_post
  -> make_growth_ranking()          ... 直近7日のランキングを生成
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

### ABC自動ランキング (auto_abc_ranking, 毎日 1:05 JST)

```
auto_abc_ranking
  -> get_prev_contest()                   ... 前回処理したABC番号を取得
  -> fetch_abc_standings_if_ready()       ... 次のABCの結果を確認
      -> AtCoder results/json API         ... レート確定済みか判定
      -> get_contest_ac_count()           ... コンテスト中のAC数をDBから算出
  -> set_prev_contest()                   ... ABC番号を更新
  -> Discordに投稿 (rated/unrated分類のランキング + AC数)
```

### 精進状況表示 (/everyone_state)

```
/everyone_state
  -> get_user_dict()       ... 全登録ユーザーを取得
  -> get_ac_count()        ... 各ユーザーの総AC数を取得
  -> get_ac_streak()       ... 各ユーザーの連続AC日数を算出
```

---

## 環境変数 (.env)

| 変数名 | 説明 |
|---|---|
| DISCORD_TOKEN | Discord Botトークン |
| ADMIN_ID | 管理者のDiscordユーザーID |
| RANKING_CHANNEL_ID | ランキング自動投稿先のチャンネルID |
| PORT | HTTPサーバーのポート番号 (デフォルト: 8000) |

---

## 起動

```bash
cd app
python main.py
```

起動時の処理:
1. DBの全テーブルを初期化 (init_db)
2. スラッシュコマンドをDiscordに同期 (tree.sync)
3. バックグラウンドタスクを開始 (daily_update, weekly_ranking_post, auto_abc_ranking)
4. prev_contestが未設定の場合、APIから直近のABC番号を取得して初期化 (フォールバック: 455)
5. ログ出力用チャンネルを設定
6. ヘルスチェック用HTTPサーバーをデーモンスレッドで起動

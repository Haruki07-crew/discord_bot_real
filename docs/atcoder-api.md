# 外部APIの仕様メモ

実際にAPIを叩いて確認した仕様。コードの前提になっているので、変わったらここも更新する。

## 共通ルール

- **リクエストは必ず `app/atcoder/http_client.py` の `get()` / `get_json()` を通す。** aiohttp を直接使わない。
  - 同じホストへのリクエストは Bot 全体で1秒に1回までに制限される (コマンドと自動タスクが同時に動いても守られる)。
  - タイムアウト (30秒)、User-Agent、`content_type=None` での JSON 解析、discord_logger への記録もここで行う。

## atcoder.jp

| エンドポイント | 仕様 |
|---|---|
| `/users/{name}` | 存在しないユーザーは **404**。存在確認はこれで行う (`atcoder_user_exists`) |
| `/users/{name}/history/json` | 存在しないユーザーも、コンテスト未参加のユーザーも **200 `[]`**。存在確認には使えない |
| `/contests/abcNNN/results/json` | 1回で参加者全員の結果。各要素に `UserScreenName` `Place` `OldRating` `NewRating` `Performance` `IsRated` `EndTime` (`"2026-11-07T22:40:00+09:00"`) |

- ユーザー名は大文字小文字を区別しない。
- results/json はレート確定後に `NewRating > 0` の rated 参加者が現れる。unrated 回は全員 `IsRated=false`。
- 最近の ABC はすべて100分。

## kenkoooo.com (AtCoder Problems)

| エンドポイント | 仕様 |
|---|---|
| `/atcoder/atcoder-api/v3/user/submissions?user=X&from_second=T` | 最大500件、`epoch_second` 昇順。**`from_id` は無視される**。`from_second` はその秒を含む。ユーザー名の大文字小文字は区別しない |
| `/atcoder/atcoder-api/v3/user/ac_rank?user=X` | AC が1つも無いユーザー (と存在しないユーザー) は **404** |
| `/atcoder/resources/contests.json` | 全コンテスト。`start_epoch_second` + `duration_second` で終了時刻 |
| `/atcoder/resources/problem-models.json` | 問題の推定難易度 |

- ページ送りは `from_second` を最後の提出の `epoch_second` に進める (同じ秒に500件以上ある場合は +1)。
- kenkoooo はコンテスト終了後に提出をまとめて取り込むことがあり、時刻順に増えるとは限らない。
  差分取得は最終提出時刻の24時間前から取り直している (重複は INSERT OR IGNORE で除外)。

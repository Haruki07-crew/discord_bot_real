from atcoder import db
"""ユーザーのデータを少しずつ同期し続けるバックグラウンド処理。

コマンドのたびに全員分を取り直すと、人数に比例して時間がかかり (1000人で15分以上)、
Discord の応答期限 (15分) を超える。そこで Bot 内で常に「一番古いユーザー」から順に同期し、
コマンドは DB を読むだけにする。

1回の sync_step で、提出 (kenkoooo) とコンテスト履歴 (atcoder.jp) をそれぞれ最大1人ずつ更新する。
ホストごとに1秒に1回の制限は http_client が守るので、1秒ごとに呼べば 1000人でも一巡約17分。
"""
import asyncio
import sqlite3
import time
from contextlib import closing

from atcoder.fetch_and_cache_ac_submissions import fetch_and_cache_ac_submissions
from atcoder.fetch_and_cache_contest_history import fetch_and_cache_contest_history

SUBMISSION_SYNC_SEC = 5 * 60        # 提出はこの間隔ごとに取り直す
CONTEST_SYNC_SEC = 24 * 60 * 60     # コンテスト履歴はこの間隔ごと (コンテスト後は優先して取り直す)
FAILURE_PAUSE_SEC = 60              # 取得に失敗したら、その種類の同期をしばらく止める (落ちているAPIを叩き続けない)

USER_BACKOFF_BASE_SEC = 5 * 60       # 失敗したユーザーは 5分 → 10分 → 20分 … と間隔を空けて再挑戦する
USER_BACKOFF_MAX_SEC = 6 * 60 * 60
GLOBAL_PAUSE_STREAK = 3              # 別々のユーザーで続けてこの回数失敗したら API の障害とみなして全体を止める

_pause_until = {"submission": 0.0, "contest": 0.0}
_user_backoff = {}  # (kind, atcoder_name) -> (次に試してよい時刻, 連続失敗回数)
# 監視用: (ユーザーを問わず) 連続で失敗した回数と、最後に成功した時刻 (Unix秒)
fail_streak = {"submission": 0, "contest": 0}
last_success = {"submission": None, "contest": None}

_KINDS = {
  "submission": ("submission_last_fetch", SUBMISSION_SYNC_SEC),
  "contest": ("contest_last_fetched", CONTEST_SYNC_SEC),
}


def _most_stale_user(conn, kind, column, older_than, now):
  """同期が必要なユーザーのうち一番古い人。失敗して待機中のユーザーは飛ばす
  (飛ばさないと、失敗し続ける1人が毎回選ばれて、ほかの全員の同期が止まる)。"""
  # column は _KINDS の固定値のみ (ユーザー入力は入らない)
  rows = conn.execute(f"""
    SELECT u.atcoder_name FROM users u
    LEFT JOIN update_bookmark b ON b.atcoder_name = u.atcoder_name
    WHERE COALESCE(b.{column}, 0) < ?
    ORDER BY COALESCE(b.{column}, 0) ASC, u.atcoder_name ASC
  """, (older_than,))
  for (name,) in rows:
    retry_at, _count = _user_backoff.get((kind, name), (0.0, 0))
    if now >= retry_at:
      return name
  return None


def _fetched_at(conn, column, atcoder_name):
  row = conn.execute(f"SELECT {column} FROM update_bookmark WHERE atcoder_name = ?", (atcoder_name,)).fetchone()
  return (row[0] or 0) if row else 0


def _is_registered(conn, atcoder_name):
  return conn.execute("SELECT 1 FROM users WHERE atcoder_name = ?", (atcoder_name,)).fetchone() is not None


def _remove_orphan(conn, atcoder_name):
  """同期中に登録解除されたユーザーの、書き戻されたキャッシュを消す。"""
  for table in ("ac_submissions_cache", "contest_history", "update_bookmark"):
    conn.execute(f"DELETE FROM {table} WHERE atcoder_name = ?", (atcoder_name,))


async def sync_step(db_file, now=None):
  """同期が必要なユーザーを種類ごとに1人ずつ更新する。戻り値: {"submission": 名前 or None, "contest": 名前 or None}"""
  now = time.time() if now is None else now
  picked = {}
  with db.connect(db_file) as conn:
    for kind, (column, interval) in _KINDS.items():
      picked[kind] = None if now < _pause_until[kind] else _most_stale_user(conn, kind, column, now - interval, now)

  jobs = []
  if picked["submission"]:
    jobs.append(fetch_and_cache_ac_submissions(picked["submission"], db_file))
  if picked["contest"]:
    jobs.append(fetch_and_cache_contest_history(picked["contest"], db_file, force=True))
  if not jobs:
    return picked
  results = await asyncio.gather(*jobs, return_exceptions=True)
  for r in results:
    if isinstance(r, Exception):
      print(f"[background_sync] {type(r).__name__}: {r}")

  # 取得時刻が更新されていなければ失敗とみなす
  with db.connect(db_file) as conn:
    for kind, (column, _interval) in _KINDS.items():
      name = picked[kind]
      if not name:
        continue
      if not _is_registered(conn, name):
        _remove_orphan(conn, name)  # 失敗扱いにはしない
        _user_backoff.pop((kind, name), None)
        continue
      if _fetched_at(conn, column, name) < now:
        _record_failure(kind, name, now)
      else:
        _user_backoff.pop((kind, name), None)
        fail_streak[kind] = 0
        last_success[kind] = time.time()
  return picked


def _record_failure(kind, name, now):
  _retry_at, count = _user_backoff.get((kind, name), (0.0, 0))
  count += 1
  wait = min(USER_BACKOFF_BASE_SEC * 2 ** (count - 1), USER_BACKOFF_MAX_SEC)
  _user_backoff[(kind, name)] = (now + wait, count)
  fail_streak[kind] += 1
  print(f"[background_sync] {kind} sync failed for {name} ({count}回目), retry in {wait}s")
  if fail_streak[kind] >= GLOBAL_PAUSE_STREAK:
    # 別々のユーザーで続けて失敗している = API 側の障害の可能性が高いので、全体を少し止める
    _pause_until[kind] = now + FAILURE_PAUSE_SEC


def request_contest_resync(atcoder_names, db_file):
  """コンテスト履歴を次の同期で優先して取り直すよう印を付ける (レート確定直後など)。"""
  with db.connect(db_file) as conn:
    conn.executemany(
      "UPDATE update_bookmark SET contest_last_fetched = 0 WHERE atcoder_name = ? COLLATE NOCASE",
      [(n,) for n in atcoder_names],
    )
    conn.commit()


def get_oldest_submission_sync(db_file):
  """登録ユーザーのうち、提出の同期が一番古い時刻 (Unix秒)。ユーザーがいなければ None。"""
  with db.connect(db_file) as conn:
    row = conn.execute("""
      SELECT MIN(COALESCE(b.submission_last_fetch, 0)) FROM users u
      LEFT JOIN update_bookmark b ON b.atcoder_name = u.atcoder_name
    """).fetchone()
  return row[0] if row and row[0] is not None else None

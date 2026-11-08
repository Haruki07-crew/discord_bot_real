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

_pause_until = {"submission": 0.0, "contest": 0.0}

_KINDS = {
  "submission": ("submission_last_fetch", SUBMISSION_SYNC_SEC),
  "contest": ("contest_last_fetched", CONTEST_SYNC_SEC),
}


def _most_stale_user(conn, column, older_than):
  # column は _KINDS の固定値のみ (ユーザー入力は入らない)
  row = conn.execute(f"""
    SELECT u.atcoder_name FROM users u
    LEFT JOIN update_bookmark b ON b.atcoder_name = u.atcoder_name
    WHERE COALESCE(b.{column}, 0) < ?
    ORDER BY COALESCE(b.{column}, 0) ASC, u.atcoder_name ASC
    LIMIT 1
  """, (older_than,)).fetchone()
  return row[0] if row else None


def _fetched_at(conn, column, atcoder_name):
  row = conn.execute(f"SELECT {column} FROM update_bookmark WHERE atcoder_name = ?", (atcoder_name,)).fetchone()
  return (row[0] or 0) if row else 0


async def sync_step(db_file, now=None):
  """同期が必要なユーザーを種類ごとに1人ずつ更新する。戻り値: {"submission": 名前 or None, "contest": 名前 or None}"""
  now = time.time() if now is None else now
  picked = {}
  with closing(sqlite3.connect(db_file)) as conn:
    for kind, (column, interval) in _KINDS.items():
      picked[kind] = None if now < _pause_until[kind] else _most_stale_user(conn, column, now - interval)

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

  # 取得時刻が更新されていなければ失敗とみなして、その種類をしばらく止める
  with closing(sqlite3.connect(db_file)) as conn:
    for kind, (column, _interval) in _KINDS.items():
      name = picked[kind]
      if name and _fetched_at(conn, column, name) < now:
        _pause_until[kind] = now + FAILURE_PAUSE_SEC
        print(f"[background_sync] {kind} sync failed for {name}, pausing {FAILURE_PAUSE_SEC}s")
  return picked


def request_contest_resync(atcoder_names, db_file):
  """コンテスト履歴を次の同期で優先して取り直すよう印を付ける (レート確定直後など)。"""
  with closing(sqlite3.connect(db_file)) as conn:
    conn.executemany(
      "UPDATE update_bookmark SET contest_last_fetched = 0 WHERE atcoder_name = ? COLLATE NOCASE",
      [(n,) for n in atcoder_names],
    )
    conn.commit()


def get_oldest_submission_sync(db_file):
  """登録ユーザーのうち、提出の同期が一番古い時刻 (Unix秒)。ユーザーがいなければ None。"""
  with closing(sqlite3.connect(db_file)) as conn:
    row = conn.execute("""
      SELECT MIN(COALESCE(b.submission_last_fetch, 0)) FROM users u
      LEFT JOIN update_bookmark b ON b.atcoder_name = u.atcoder_name
    """).fetchone()
  return row[0] if row and row[0] is not None else None

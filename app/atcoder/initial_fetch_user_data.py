import asyncio
import sqlite3
import time

async def initial_fetch_user_data(atcoder_name, db_file):
  from atcoder.fetch_and_cache_contest_history import fetch_and_cache_contest_history, CONTEST_CACHE_TTL
  from atcoder.fetch_and_cache_ac_submissions import fetch_and_cache_ac_submissions

  # コンテスト履歴がキャッシュ有効期間内なら API を叩かないので、待機も不要
  with sqlite3.connect(db_file) as conn:
    row = conn.execute(
      "SELECT contest_last_fetched FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    ).fetchone()
  contest_cached = bool(row and row[0] and (time.time() - row[0]) < CONTEST_CACHE_TTL)

  await fetch_and_cache_contest_history(atcoder_name, db_file)
  if not contest_cached:
    await asyncio.sleep(1.0)
  await fetch_and_cache_ac_submissions(atcoder_name, db_file)


async def refresh_users_data(atcoder_names, db_file, interval=1.0):
  """集計の直前に、指定ユーザーのコンテスト履歴とAC提出キャッシュを差分更新する。
  daily_update は1日1回しか走らないため、これを呼ばないと当日分のACやレート変化が反映されない。
  1人失敗しても他のユーザーの更新は続ける。"""
  for i, atcoder_name in enumerate(atcoder_names):
    if i > 0:
      await asyncio.sleep(interval)
    try:
      await initial_fetch_user_data(atcoder_name, db_file)
    except Exception as e:
      print(f"[refresh_users_data] {atcoder_name}: {type(e).__name__}: {e}")

from atcoder import db
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from atcoder import http_client

JST = timezone(timedelta(hours=9))
# レートはコンテスト終了から少し遅れて確定する。長くキャッシュすると確定直後の集計に反映されないので短めにする
CONTEST_CACHE_TTL = 600

async def fetch_and_cache_contest_history(atcoder_name, db_file, force=False):
  """force=True ならキャッシュの有効期限に関係なく再取得する (週次集計の直前など)"""
  now = time.time()

  with db.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT contest_last_fetched FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    )
    meta = cursor.fetchone()

    if not force and meta and meta[0] and (now - meta[0]) < CONTEST_CACHE_TTL:
      cursor.execute("""
        SELECT contest_screen_name, end_time, new_rating, old_rating
        FROM contest_history WHERE atcoder_name = ?
        ORDER BY end_time ASC
      """, (atcoder_name,))
      rows = cursor.fetchall()
      return [
        {"ContestScreenName": r[0], "EndTime": r[1], "NewRating": r[2], "OldRating": r[3]}
        for r in rows
      ]

  try:
    url = f"https://atcoder.jp/users/{atcoder_name}/history/json"
    data = await http_client.get_json(url, log=f"コンテスト履歴取得 [{atcoder_name}]")
  except Exception as e:
    with db.connect(db_file) as conn:
      cursor = conn.cursor()
      cursor.execute("""
        SELECT contest_screen_name, end_time, new_rating, old_rating
        FROM contest_history WHERE atcoder_name = ?
        ORDER BY end_time ASC
      """, (atcoder_name,))
      rows = cursor.fetchall()
    return [
      {"ContestScreenName": r[0], "EndTime": r[1], "NewRating": r[2], "OldRating": r[3]}
      for r in rows
    ]

  if not isinstance(data, list):
    return []
  rated_contests = [c for c in data if c.get("IsRated", False)]
  with db.connect(db_file) as conn:
    cursor = conn.cursor()
    for contest in rated_contests:
      cursor.execute("""
        INSERT OR REPLACE INTO contest_history
        (atcoder_name, contest_screen_name, end_time, new_rating, old_rating)
        VALUES (?, ?, ?, ?, ?)
      """, (
        atcoder_name,
        contest["ContestScreenName"],
        contest["EndTime"],
        contest["NewRating"],
        contest["OldRating"]
      ))
    cursor.execute("""
      INSERT INTO update_bookmark (atcoder_name, contest_last_fetched)
      VALUES (?, ?)
      ON CONFLICT(atcoder_name) DO UPDATE SET contest_last_fetched = excluded.contest_last_fetched
    """, (atcoder_name, now))
    conn.commit()

  return rated_contests

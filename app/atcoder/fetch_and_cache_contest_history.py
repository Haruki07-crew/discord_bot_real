import aiohttp
import sqlite3
import time
from datetime import datetime, timezone, timedelta
import discord_logger

JST = timezone(timedelta(hours=9))
CONTEST_CACHE_TTL = 3600

async def fetch_and_cache_contest_history(atcoder_name, db_file):
  now = time.time()

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT contest_last_fetched FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    )
    meta = cursor.fetchone()

    if meta and (now - meta[0]) < CONTEST_CACHE_TTL:
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
    await discord_logger.log_api(f"APIを叩いた: コンテスト履歴取得 (fetch_and_cache_contest_history) [{atcoder_name}]")
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    async with aiohttp.ClientSession() as session:
      async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
  except Exception as e:
    with sqlite3.connect(db_file) as conn:
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
  with sqlite3.connect(db_file) as conn:
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

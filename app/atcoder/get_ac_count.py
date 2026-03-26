import aiohttp
import sqlite3
from datetime import datetime, timezone, timedelta
import discord_logger

async def get_ac_count(atcoder_name, db_file="database.db"):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT 1 FROM progress_cache_meta WHERE atcoder_name = ?",
      (atcoder_name,)
    )
    if cursor.fetchone():
      cursor.execute(
        "SELECT COUNT(DISTINCT problem_id) FROM ac_submissions_cache WHERE atcoder_name = ?",
        (atcoder_name,)
      )
      row = cursor.fetchone()
      return row[0] if row else 0

  url = f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/ac_rank?user={atcoder_name}"
  await discord_logger.log_api(f"APIを叩いた: AC数取得 (get_ac_count) [{atcoder_name}]")
  timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
  async with aiohttp.ClientSession() as session:
    async with session.get(url, timeout=timeout) as resp:
      resp.raise_for_status()
      data = await resp.json(content_type=None)
  return data["count"]

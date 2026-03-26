import aiohttp
import asyncio
import math
import sqlite3
from datetime import datetime, timezone, timedelta
import discord_logger

async def count_period_ac(atcoder_name, day, db_file="database.db"):
  time_difference = timezone(timedelta(hours=9))
  now = datetime.now(time_difference)
  if day == 1:
    start_time = datetime(now.year, now.month, now.day, tzinfo=time_difference)
  else:
    start_time = datetime(now.year, now.month, now.day, tzinfo=time_difference) - timedelta(days=day)
  period_start_unix = int(start_time.timestamp())

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT submission_last_id FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    )
    meta = cursor.fetchone()

  if meta is not None and meta[0] and meta[0] > 0:
    with sqlite3.connect(db_file) as conn:
      cursor = conn.cursor()
      cursor.execute("""
        SELECT problem_id, MAX(point) FROM ac_submissions_cache
        WHERE atcoder_name = ? AND epoch_second >= ?
        GROUP BY problem_id
      """, (atcoder_name, period_start_unix))
      rows = cursor.fetchall()
    ac_count = len(rows)
    ac_point_sum = sum(point or 0 for _, point in rows)
    return [ac_count, math.ceil(ac_point_sum)]

  s = set()
  ac_point_sum = 0
  last_submission_id = None
  page = 0
  timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
  async with aiohttp.ClientSession() as session:
    while True:
      url = f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions?user={atcoder_name}&from_second={period_start_unix}"
      if last_submission_id:
        url += f"&from_id={last_submission_id + 1}"
      await discord_logger.log_api(f"APIを叩いた: 期間AC数取得 (count_period_ac) [{atcoder_name}] page={page}")
      try:
        async with session.get(url, timeout=timeout) as resp:
          resp.raise_for_status()
          data = await resp.json(content_type=None)
      except Exception as e:
        break
      if not isinstance(data, list) or not data:
        break
      for submission in data:
        if submission["result"] == "AC":
          problem_id = submission["problem_id"]
          if "ahc" not in problem_id and problem_id not in s:
            s.add(problem_id)
            ac_point_sum += submission["point"]
        last_submission_id = submission["id"]
      page += 1
      if len(data) < 500:
        break
      await asyncio.sleep(0.8)
  return [len(s), math.ceil(ac_point_sum)]

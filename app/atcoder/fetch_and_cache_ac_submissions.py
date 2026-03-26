import aiohttp
import asyncio
import sqlite3
import time
from datetime import datetime, timezone, timedelta
import discord_logger

JST = timezone(timedelta(hours=9))

async def fetch_and_cache_ac_submissions(atcoder_name, db_file):
  now = time.time()

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "INSERT OR IGNORE INTO update_bookmark (atcoder_name) VALUES (?)",
      (atcoder_name,)
    )
    conn.commit()
    cursor.execute(
      "SELECT submission_last_id, submission_last_fetch, submission_cache_from FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    )
    row = cursor.fetchone()

  if row is None:
    return
  last_id, last_fetch, last_epoch = row

  if last_fetch and (now - last_fetch) < 60:
    return

  from_id = last_id if last_id and last_id > 0 else None
  from_epoch = int(last_epoch) if last_epoch and last_epoch > 0 else 0

  if from_id and from_epoch == 0:
    with sqlite3.connect(db_file) as conn:
      cursor = conn.cursor()
      cursor.execute(
        "SELECT MAX(epoch_second) FROM ac_submissions_cache WHERE atcoder_name = ?",
        (atcoder_name,)
      )
      r = cursor.fetchone()
      from_epoch = r[0] if r and r[0] else 0

  new_submissions = []
  last_submission_id = from_id
  last_epoch_second = from_epoch
  timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
  async with aiohttp.ClientSession() as session:
    page = 0
    while page < 300:
      url = (
        f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions"
        f"?user={atcoder_name}&from_second={last_epoch_second}"
      )
      if last_submission_id:
        url += f"&from_id={last_submission_id}"

      await discord_logger.log_api(f"APIを叩いた: AC提出取得 (fetch_and_cache_ac_submissions) [{atcoder_name}] page={page}")
      try:
        async with session.get(url, timeout=timeout) as resp:
          resp.raise_for_status()
          data = await resp.json(content_type=None)
      except Exception as e:
        break

      if not isinstance(data, list) or not data:
        break

      for sub in data:
        if sub["result"] == "AC" and "ahc" not in sub["problem_id"]:
          new_submissions.append((atcoder_name, sub["id"], sub["problem_id"], sub["epoch_second"], sub.get("point", 0)))

      last_submission_id = data[-1]["id"]
      last_epoch_second = data[-1]["epoch_second"]
      page += 1
      if len(data) < 500:
        break
      await asyncio.sleep(0.8)

  if new_submissions or (last_submission_id and last_submission_id != from_id):
    with sqlite3.connect(db_file) as conn:
      cursor = conn.cursor()
      if new_submissions:
        cursor.executemany("""
          INSERT OR IGNORE INTO ac_submissions_cache
          (atcoder_name, submission_id, problem_id, epoch_second, point)
          VALUES (?, ?, ?, ?, ?)
        """, new_submissions)
      if last_submission_id and last_submission_id != from_id:
        cursor.execute("""
          UPDATE update_bookmark
          SET submission_last_id = ?, submission_last_fetch = ?, submission_cache_from = ?
          WHERE atcoder_name = ?
        """, (last_submission_id, now, last_epoch_second, atcoder_name))
      conn.commit()

from atcoder import db
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from atcoder import http_client

JST = timezone(timedelta(hours=9))

# kenkoooo はコンテスト終了後に提出をまとめて取り込むなど、時刻順に取り込まれるとは限らない。
# 最終提出時刻ちょうどから取得すると後から取り込まれた古い提出を取りこぼすので、
# 少し巻き戻して取得する (重複は INSERT OR IGNORE で除外される)。
REFETCH_MARGIN_SEC = 24 * 60 * 60

async def fetch_and_cache_ac_submissions(atcoder_name, db_file):
  now = time.time()

  with db.connect(db_file) as conn:
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
    with db.connect(db_file) as conn:
      cursor = conn.cursor()
      cursor.execute(
        "SELECT MAX(epoch_second) FROM ac_submissions_cache WHERE atcoder_name = ?",
        (atcoder_name,)
      )
      r = cursor.fetchone()
      from_epoch = r[0] if r and r[0] else 0

  # kenkoooo API は from_id を無視するので from_second だけでページ送りする。
  # from_second は「その秒を含む」ため直前の最終提出が再取得されるが、INSERT OR IGNORE で重複排除される。
  new_submissions = []
  last_submission_id = from_id
  last_epoch_second = max(0, from_epoch - REFETCH_MARGIN_SEC) if from_epoch > 0 else 0
  fetch_ok = False
  for page in range(300):
    url = (
      f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions"
      f"?user={atcoder_name}&from_second={last_epoch_second}"
    )
    try:
      data = await http_client.get_json(url, log=f"AC提出取得 [{atcoder_name}] page={page}")
    except Exception as e:
      print(f"[fetch_and_cache_ac_submissions] {atcoder_name}: {type(e).__name__}: {e}")
      break

    if not isinstance(data, list):
      break
    fetch_ok = True
    if not data:
      break

    for sub in data:
      if sub["result"] == "AC" and "ahc" not in sub["problem_id"]:
        new_submissions.append((atcoder_name, sub["id"], sub["problem_id"], sub["epoch_second"], sub.get("point", 0)))

    last_submission_id = data[-1]["id"]
    if len(data) < 500:
      last_epoch_second = data[-1]["epoch_second"]
      break
    next_epoch = data[-1]["epoch_second"]
    # 同一秒に500件以上ある場合でも先へ進めるようにする
    last_epoch_second = next_epoch if next_epoch > last_epoch_second else last_epoch_second + 1

  with db.connect(db_file) as conn:
    cursor = conn.cursor()
    if new_submissions:
      cursor.executemany("""
        INSERT OR IGNORE INTO ac_submissions_cache
        (atcoder_name, submission_id, problem_id, epoch_second, point)
        VALUES (?, ?, ?, ?, ?)
      """, new_submissions)
    if last_submission_id and last_submission_id != from_id and last_epoch_second > from_epoch:
      cursor.execute("""
        UPDATE update_bookmark
        SET submission_last_id = ?, submission_cache_from = ?
        WHERE atcoder_name = ?
      """, (last_submission_id, last_epoch_second, atcoder_name))
    if fetch_ok:
      # 新しい提出が無くても取得時刻は記録し、60秒以内の連続呼び出しでAPIを叩かないようにする
      cursor.execute(
        "UPDATE update_bookmark SET submission_last_fetch = ? WHERE atcoder_name = ?",
        (now, atcoder_name)
      )
    conn.commit()

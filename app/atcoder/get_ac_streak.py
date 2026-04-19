import sqlite3
from datetime import datetime, timezone, timedelta


def get_ac_streak(atcoder_name, db_file):
  """昨日から遡って何日連続でACしているかを返す。今日の分は含めない。"""
  JST = timezone(timedelta(hours=9))
  now = datetime.now(JST)
  yesterday = datetime(now.year, now.month, now.day, tzinfo=JST) - timedelta(days=1)

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("""
      SELECT DISTINCT date(epoch_second, 'unixepoch', '+9 hours') as ac_date
      FROM ac_submissions_cache
      WHERE atcoder_name = ?
      ORDER BY ac_date DESC
    """, (atcoder_name,))
    rows = cursor.fetchall()

  if not rows:
    return 0

  ac_dates = set(row[0] for row in rows)

  streak = 0
  check_date = yesterday
  while True:
    date_str = check_date.strftime("%Y-%m-%d")
    if date_str in ac_dates:
      streak += 1
      check_date -= timedelta(days=1)
    else:
      break

  return streak

import sqlite3
from datetime import datetime, timezone, timedelta

async def get_progress_data(atcoder_name, days, db_file):
  from atcoder.parse_atcoder_time import parse_atcoder_time
  try:
    time_diff = timezone(timedelta(hours=9))
    now = datetime.now(time_diff)
    period_start = now - timedelta(days=days)
    period_start_unix = int(period_start.timestamp())

    with sqlite3.connect(db_file) as conn:
      cursor = conn.cursor()
      cursor.execute("""
        SELECT contest_screen_name, end_time, new_rating, old_rating
        FROM contest_history WHERE atcoder_name = ?
        ORDER BY end_time ASC
      """, (atcoder_name,))
      rows = cursor.fetchall()
    if not rows:
      return None
    all_contests = [
      {"ContestScreenName": r[0], "EndTime": r[1], "NewRating": r[2], "OldRating": r[3]}
      for r in rows
    ]

    initial_rating = None
    period_contests = []
    for contest in all_contests:
      end_dt = parse_atcoder_time(contest["EndTime"])
      if end_dt is None:
        continue
      if end_dt.timestamp() < period_start_unix:
        initial_rating = contest["NewRating"]
      else:
        period_contests.append({
          "end_unix": end_dt.timestamp(),
          "new_rating": contest["NewRating"],
          "old_rating": contest["OldRating"]
        })

    if not period_contests:
      return None

    period_contests.sort(key=lambda x: x["end_unix"])

    if initial_rating is None:
      initial_rating = period_contests[0]["old_rating"]

    with sqlite3.connect(db_file) as conn:
      cursor = conn.cursor()
      cursor.execute("""
        SELECT problem_id, epoch_second FROM ac_submissions_cache
        WHERE atcoder_name = ? AND epoch_second >= ?
        ORDER BY epoch_second ASC
      """, (atcoder_name, period_start_unix))
      ac_rows = cursor.fetchall()

    points = [(0, initial_rating)]
    solved = set()
    sub_idx = 0
    for contest in period_contests:
      while sub_idx < len(ac_rows) and ac_rows[sub_idx][1] <= contest["end_unix"]:
        solved.add(ac_rows[sub_idx][0])
        sub_idx += 1
      points.append((len(solved), contest["new_rating"]))

    return points

  except Exception as e:
    return None

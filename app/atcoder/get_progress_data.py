import sqlite3

async def get_progress_data(atcoder_name, days, db_file, x_axis="ac"):
  """期間内のコンテストごとの (横軸の値, レート) のリストを返す。
  x_axis="ac" なら期間内の累積AC数、"point" なら累積獲得点数 (問題ごとに最大点を1回だけ加算)。"""
  from atcoder.parse_atcoder_time import parse_atcoder_time
  from atcoder.count_period_ac import get_period_start_unix
  try:
    period_start_unix = get_period_start_unix(days)

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
        SELECT problem_id, epoch_second, point FROM ac_submissions_cache
        WHERE atcoder_name = ? AND epoch_second >= ?
        ORDER BY epoch_second ASC
      """, (atcoder_name, period_start_unix))
      ac_rows = cursor.fetchall()

    points = [(0, initial_rating)]
    best_point = {}  # problem_id -> その問題で得た最大点
    sub_idx = 0
    for contest in period_contests:
      while sub_idx < len(ac_rows) and ac_rows[sub_idx][1] <= contest["end_unix"]:
        problem_id, _epoch, point = ac_rows[sub_idx]
        best_point[problem_id] = max(best_point.get(problem_id, 0), point or 0)
        sub_idx += 1
      x = sum(best_point.values()) if x_axis == "point" else len(best_point)
      points.append((x, contest["new_rating"]))

    return points

  except Exception as e:
    return None

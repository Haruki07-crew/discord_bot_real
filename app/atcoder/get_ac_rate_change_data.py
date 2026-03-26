import sqlite3
from datetime import datetime, timezone, timedelta

async def get_ac_rate_change_data(user_dict, days, db_file):
  from atcoder.parse_atcoder_time import parse_atcoder_time
  from atcoder.count_period_ac import count_period_ac
  JST = timezone(timedelta(hours=9))
  now = datetime.now(JST)
  period_start_unix = int((now - timedelta(days=days)).timestamp())

  result = {}
  for atcoder_name, discord_name in user_dict.items():
    try:
      ac_data = await count_period_ac(atcoder_name, days, db_file)
      ac_count = ac_data[0]

      with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
          SELECT end_time, new_rating, old_rating
          FROM contest_history WHERE atcoder_name = ?
          ORDER BY end_time ASC
        """, (atcoder_name,))
        rows = cursor.fetchall()

      initial_rating = None
      final_rating = None
      first_old_rating = None
      for end_time_str, new_rating, old_rating in rows:
        end_dt = parse_atcoder_time(end_time_str)
        if end_dt is None:
          continue
        if end_dt.timestamp() < period_start_unix:
          initial_rating = new_rating
        else:
          if first_old_rating is None:
            first_old_rating = old_rating
          final_rating = new_rating

      if final_rating is None:
        rate_change = 0
      else:
        base = initial_rating if initial_rating is not None else (first_old_rating or 0)
        rate_change = final_rating - base

      result[atcoder_name] = {
        "discord_name": discord_name,
        "ac": ac_count,
        "rate_change": rate_change
      }
    except Exception as e:
      result[atcoder_name] = {"discord_name": discord_name, "ac": 0, "rate_change": 0}

  return result

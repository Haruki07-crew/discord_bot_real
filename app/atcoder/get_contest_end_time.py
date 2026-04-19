import sqlite3
from atcoder.parse_atcoder_time import parse_atcoder_time


def get_contest_end_time_unix(contest_number, db_file):
  """contest_historyから指定ABCの終了時刻(Unix秒)を取得する。
  見つからない場合はNoneを返す。"""
  contest_id = f"abc{contest_number:03d}"

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("""
      SELECT end_time FROM contest_history
      WHERE contest_screen_name LIKE ?
      LIMIT 1
    """, (f"{contest_id}%",))
    row = cursor.fetchone()

  if row is None:
    return None

  dt = parse_atcoder_time(row[0])
  if dt is None:
    return None

  return int(dt.timestamp())

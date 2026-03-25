import sqlite3

def get_latest_rating_from_db(atcoder_name, db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("""
      SELECT new_rating FROM contest_history
      WHERE atcoder_name = ?
      ORDER BY end_time DESC
      LIMIT 1
    """, (atcoder_name,))
    row = cursor.fetchone()
  return row[0] if row else 0

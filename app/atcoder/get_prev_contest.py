import sqlite3

def get_prev_contest(db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_state WHERE key = 'prev_contest'")
    row = cursor.fetchone()
    if row is None:
      return None
    return int(row[0])

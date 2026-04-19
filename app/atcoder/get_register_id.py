import sqlite3

def get_register_id(atcoder_name, db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT register_id FROM users WHERE atcoder_name = ?", (atcoder_name,))
    row = cursor.fetchone()
  return row[0] if row else None

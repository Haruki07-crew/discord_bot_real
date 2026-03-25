import sqlite3

def get_user_dict(db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT atcoder_name, discord_name FROM users")
    rows = cursor.fetchall()
  return {row[0]: row[1] for row in rows}

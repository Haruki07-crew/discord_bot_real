import sqlite3

def get_registered_user(atcoder_name, db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT discord_name, register_id FROM users WHERE atcoder_name = ?", (atcoder_name,))
    return cursor.fetchone()

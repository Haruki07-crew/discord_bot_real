import sqlite3

def get_all_users_with_discord_id(db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT atcoder_name, discord_name, discord_id FROM users")
    return cursor.fetchall()

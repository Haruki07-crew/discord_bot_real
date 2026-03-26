import sqlite3

def register_user(atcoder_name, discord_name, discord_id, resister_id, db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "INSERT INTO users (atcoder_name, discord_name, discord_id, resister_id) VALUES (?, ?, ?, ?)",
      (atcoder_name, discord_name, discord_id, resister_id)
    )
    conn.commit()

import sqlite3

def set_prev_contest(number, db_file):
  with sqlite3.connect(db_file) as conn:
    conn.execute(
      "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('prev_contest', ?)",
      (str(number),)
    )
    conn.commit()

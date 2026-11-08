from atcoder import db
import sqlite3

def set_prev_contest(number, db_file):
  with db.connect(db_file) as conn:
    conn.execute(
      "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('prev_contest', ?)",
      (str(number),)
    )
    conn.commit()

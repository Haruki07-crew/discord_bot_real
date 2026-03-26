import sqlite3
import time

def mark_contest_auto_posted(contest_id, db_file):
  with sqlite3.connect(db_file) as conn:
    conn.execute(
      "INSERT OR IGNORE INTO auto_posted_contests (contest_id, posted_at) VALUES (?, ?)",
      (contest_id, time.time())
    )
    conn.commit()

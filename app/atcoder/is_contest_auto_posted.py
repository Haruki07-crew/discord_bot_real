import sqlite3

def is_contest_auto_posted(contest_id, db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM auto_posted_contests WHERE contest_id = ?", (contest_id,))
    return cursor.fetchone() is not None

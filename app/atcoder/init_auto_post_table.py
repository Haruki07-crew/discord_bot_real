import sqlite3

def init_auto_post_table(db_file):
  with sqlite3.connect(db_file) as conn:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS auto_posted_contests (
        contest_id TEXT PRIMARY KEY,
        posted_at  REAL
      )
    """)
    conn.commit()

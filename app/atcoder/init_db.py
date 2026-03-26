import sqlite3
from atcoder.init_progress_tables import init_progress_tables
from atcoder.init_auto_post_table import init_auto_post_table

def init_db(db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("""
      CREATE TABLE IF NOT EXISTS users (
        atcoder_name TEXT PRIMARY KEY,
        discord_name TEXT,
        discord_id INTEGER,
        resister_id INTEGER
      )
    """)
    try:
      cursor.execute("ALTER TABLE users ADD COLUMN discord_id INTEGER")
    except sqlite3.OperationalError:
      pass
    conn.commit()
  with sqlite3.connect(db_file) as conn:
    try:
      conn.execute("ALTER TABLE ac_submissions_cache ADD COLUMN point INTEGER DEFAULT 0")
      conn.commit()
    except sqlite3.OperationalError:
      pass
  init_progress_tables(db_file)
  init_auto_post_table(db_file)

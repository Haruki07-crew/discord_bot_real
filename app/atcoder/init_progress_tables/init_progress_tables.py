import sqlite3

def init_progress_tables(db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("""
      CREATE TABLE IF NOT EXISTS contest_history (
        atcoder_name TEXT,
        contest_screen_name TEXT,
        end_time TEXT,
        new_rating INTEGER,
        old_rating INTEGER,
        PRIMARY KEY (atcoder_name, contest_screen_name)
      )
    """)
    cursor.execute("""
      CREATE TABLE IF NOT EXISTS ac_submissions_cache (
        atcoder_name TEXT,
        submission_id INTEGER,
        problem_id TEXT,
        epoch_second INTEGER,
        point INTEGER DEFAULT 0,
        PRIMARY KEY (atcoder_name, submission_id)
      )
    """)
    cursor.execute("""
      CREATE TABLE IF NOT EXISTS update_bookmark (
        atcoder_name TEXT PRIMARY KEY,
        contest_last_fetched REAL DEFAULT 0.0,
        submission_last_id INTEGER DEFAULT 0,
        submission_cache_from REAL DEFAULT 0.0,
        submission_last_fetch REAL DEFAULT 0.0
      )
    """)
    conn.commit()

import sqlite3

def delete_user(atcoder_name, db_file):
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE atcoder_name = ?", (atcoder_name,))
    conn.commit()

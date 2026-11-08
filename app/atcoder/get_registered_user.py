from atcoder import db
import sqlite3

def get_registered_user(atcoder_name, db_file):
  # AtCoderのユーザー名は大文字小文字を区別しないので、二重登録チェックも区別せずに行う
  with db.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT discord_name, register_id FROM users WHERE atcoder_name = ? COLLATE NOCASE",
      (atcoder_name,)
    )
    return cursor.fetchone()

import sqlite3
from contextlib import closing


def get_registered_by_discord_id(discord_id, db_file):
  """その Discord ユーザーが自分で登録した AtCoder 名を返す (無ければ None)。"""
  with closing(sqlite3.connect(db_file)) as conn:
    row = conn.execute(
      "SELECT atcoder_name FROM users WHERE discord_id = ? AND register_id = ? LIMIT 1",
      (discord_id, discord_id),
    ).fetchone()
  return row[0] if row else None

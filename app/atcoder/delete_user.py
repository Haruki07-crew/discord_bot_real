import sqlite3

def delete_user(atcoder_name, db_file):
  """ユーザーの登録を解除し、そのユーザーのキャッシュも削除する。
  キャッシュを残すと、再登録時に古いブックマークが使われたり、DBが肥大化したりする。
  週次スナップショットは過去の記録として残す (グラフには現在の登録者だけを表示する)。"""
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    for table in ("users", "ac_submissions_cache", "contest_history", "update_bookmark"):
      cursor.execute(f"DELETE FROM {table} WHERE atcoder_name = ? COLLATE NOCASE", (atcoder_name,))
    conn.commit()

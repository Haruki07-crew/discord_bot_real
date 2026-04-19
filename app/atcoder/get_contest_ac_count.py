import sqlite3


def get_contest_ac_count(atcoder_name, contest_number, end_time_unix, db_file):
  """コンテスト中のAC数をac_submissions_cacheから数える。
  ABCは100分間なので、end_time - 100分 ~ end_time の提出を対象とする。
  """
  contest_id = f"abc{contest_number:03d}"
  start_time_unix = end_time_unix - (100 * 60)  # ABC = 100分

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("""
      SELECT COUNT(DISTINCT problem_id) FROM ac_submissions_cache
      WHERE atcoder_name = ?
        AND problem_id LIKE ?
        AND epoch_second >= ?
        AND epoch_second <= ?
    """, (atcoder_name, f"{contest_id}_%", start_time_unix, end_time_unix))
    row = cursor.fetchone()

  return row[0] if row else 0

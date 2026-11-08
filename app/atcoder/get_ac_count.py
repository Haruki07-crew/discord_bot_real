from atcoder import db
import sqlite3
from atcoder import http_client

async def get_ac_count(atcoder_name, db_file="database.db"):
  with db.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT submission_last_id, submission_last_fetch FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    )
    row = cursor.fetchone()
    # 一度でも提出の取得に成功していればキャッシュを使う。
    # (提出が1件も無いユーザーは submission_last_id が 0 のままなので、それだけで判定すると
    #  API にフォールバックして 404 で例外になり、/everyone_state 全体が失敗していた)
    if row and ((row[0] and row[0] > 0) or (row[1] and row[1] > 0)):
      cursor.execute(
        "SELECT COUNT(DISTINCT problem_id) FROM ac_submissions_cache WHERE atcoder_name = ?",
        (atcoder_name,)
      )
      row = cursor.fetchone()
      return row[0] if row else 0

  url = f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/ac_rank?user={atcoder_name}"
  status, data = await http_client.get(url, log=f"AC数取得 [{atcoder_name}]")
  if status == 404:
    return 0  # kenkoooo は AC が1つも無いユーザー (と存在しないユーザー) に 404 を返す
  if status != 200:
    raise RuntimeError(f"HTTP {status}: {url}")
  return data["count"]

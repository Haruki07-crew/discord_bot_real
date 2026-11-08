import math
import sqlite3
from datetime import datetime, timezone, timedelta
from atcoder import http_client

def get_period_start_unix(day):
  """集計期間の開始時刻(Unix秒)を返す。AC数・レート変化・グラフで同じ期間を使うための共通関数。
  今日を含めて day 日分 (day == 1 なら今日の0:00(JST)、7 なら6日前の0:00)。"""
  time_difference = timezone(timedelta(hours=9))
  now = datetime.now(time_difference)
  today_start = datetime(now.year, now.month, now.day, tzinfo=time_difference)
  return int((today_start - timedelta(days=max(day, 1) - 1)).timestamp())


async def count_period_ac(atcoder_name, day, db_file="database.db", end_unix=None):
  """期間内のユニークAC数と点数合計を [ac_count, point_sum] で返す。
  end_unix を指定するとその時刻より前の提出だけを数える (週次集計で週をまたいで二重に数えないため)。"""
  period_start_unix = get_period_start_unix(day)
  period_end_unix = end_unix if end_unix is not None else 2**62

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "SELECT submission_last_id, submission_last_fetch FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    )
    meta = cursor.fetchone()

  # 一度でも提出の取得に成功していればキャッシュを使う (提出0件のユーザーも含む)
  if meta is not None and ((meta[0] and meta[0] > 0) or (meta[1] and meta[1] > 0)):
    with sqlite3.connect(db_file) as conn:
      cursor = conn.cursor()
      cursor.execute("""
        SELECT problem_id, MAX(point) FROM ac_submissions_cache
        WHERE atcoder_name = ? AND epoch_second >= ? AND epoch_second < ?
        GROUP BY problem_id
      """, (atcoder_name, period_start_unix, period_end_unix))
      rows = cursor.fetchall()
    ac_count = len(rows)
    ac_point_sum = sum(point or 0 for _, point in rows)
    return [ac_count, math.ceil(ac_point_sum)]

  # kenkoooo API は from_id を無視するため、from_second を進めてページ送りする
  # (from_second を固定したままだと500件以上ある場合に同じページを取り続けてしまう)
  s = set()
  ac_point_sum = 0
  from_second = period_start_unix
  for page in range(300):
    url = f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions?user={atcoder_name}&from_second={from_second}"
    try:
      data = await http_client.get_json(url, log=f"期間AC数取得 [{atcoder_name}] page={page}")
    except Exception:
      break
    if not isinstance(data, list) or not data:
      break
    for submission in data:
      if submission["epoch_second"] >= period_end_unix:
        continue
      if submission["result"] == "AC":
        problem_id = submission["problem_id"]
        if "ahc" not in problem_id and problem_id not in s:
          s.add(problem_id)
          ac_point_sum += submission.get("point", 0) or 0
    if len(data) < 500:
      break
    next_from = data[-1]["epoch_second"]
    from_second = next_from if next_from > from_second else from_second + 1
  return [len(s), math.ceil(ac_point_sum)]

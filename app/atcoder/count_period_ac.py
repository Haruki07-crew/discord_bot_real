import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta
from atcoder import http_client

JST = timezone(timedelta(hours=9))

def get_period_start_unix(day):
  """集計期間の開始時刻(Unix秒)を返す。AC数・レート変化・グラフで同じ期間を使うための共通関数。
  今日を含めて day 日分 (day == 1 なら今日の0:00(JST)、7 なら6日前の0:00)。"""
  time_difference = timezone(timedelta(hours=9))
  now = datetime.now(time_difference)
  today_start = datetime(now.year, now.month, now.day, tzinfo=time_difference)
  return int((today_start - timedelta(days=max(day, 1) - 1)).timestamp())


# 日付は JST で区切る (SQLite の date() 用)
JST_OFFSET = "+9 hours"


async def count_period_ac(atcoder_name, day, db_file="database.db", end_unix=None):
  """期間内の AC を [総合AC, 点数, 新規AC] で返す。

  - 総合AC: 期間内に AC した (問題, 日付) の組の数。同じ問題を同じ日に何度 AC しても1回。
           別の日にもう一度 AC すれば、その日の分としてまた数える。
  - 点数:   総合AC と同じ単位 (問題・日付ごと) で、その問題の点数を足したもの。
  - 新規AC: 期間内に初めて AC した問題の数 (それより前に一度も AC していない問題)。
           登録していないユーザーは全履歴を持っていないので None。
  end_unix を指定するとその時刻より前の提出だけを数える (週次集計で週をまたいで二重に数えないため)。"""
  period_start_unix = get_period_start_unix(day)
  period_end_unix = end_unix if end_unix is not None else 2**62

  with closing(sqlite3.connect(db_file)) as conn:
    meta = conn.execute(
      "SELECT submission_last_id, submission_last_fetch FROM update_bookmark WHERE atcoder_name = ?",
      (atcoder_name,)
    ).fetchone()

    # 一度でも提出の取得に成功していればキャッシュを使う (提出0件のユーザーも含む)
    if meta is not None and ((meta[0] and meta[0] > 0) or (meta[1] and meta[1] > 0)):
      rows = conn.execute(f"""
        SELECT problem_id, date(epoch_second, 'unixepoch', '{JST_OFFSET}') AS d, MAX(point)
        FROM ac_submissions_cache
        WHERE atcoder_name = ? AND epoch_second >= ? AND epoch_second < ?
        GROUP BY problem_id, d
      """, (atcoder_name, period_start_unix, period_end_unix)).fetchall()
      new_ac = conn.execute("""
        SELECT COUNT(*) FROM (
          SELECT MIN(epoch_second) AS first_ac FROM ac_submissions_cache
          WHERE atcoder_name = ? GROUP BY problem_id
        ) WHERE first_ac >= ? AND first_ac < ?
      """, (atcoder_name, period_start_unix, period_end_unix)).fetchone()[0]
      return [len(rows), math.ceil(sum(point or 0 for _, _, point in rows)), new_ac]

  # kenkoooo API は from_id を無視するため、from_second を進めてページ送りする
  # (from_second を固定したままだと500件以上ある場合に同じページを取り続けてしまう)
  s = set()  # (problem_id, JSTの日付)
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
        key = (problem_id, datetime.fromtimestamp(submission["epoch_second"], JST).date())
        if "ahc" not in problem_id and key not in s:
          s.add(key)
          ac_point_sum += submission.get("point", 0) or 0
    if len(data) < 500:
      break
    next_from = data[-1]["epoch_second"]
    from_second = next_from if next_from > from_second else from_second + 1
  return [len(s), math.ceil(ac_point_sum), None]

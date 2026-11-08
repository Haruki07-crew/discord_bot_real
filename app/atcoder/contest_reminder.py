"""ABC の開始前リマインド。kenkoooo の一覧には未来のコンテストが無いので atcoder.jp の予定表を読む。"""
import re
import time
from datetime import datetime

from atcoder import db
from atcoder import http_client

REFRESH_SEC = 60 * 60
REMIND_BEFORE_SEC = 30 * 60
_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_TIME_RE = re.compile(r"<time[^>]*>([^<]+)</time>")
_ABC_RE = re.compile(r'href="/contests/(abc\d+)">([^<]+)</a>')

_cache = {"at": 0.0, "contests": []}


def parse_upcoming_abc(page):
  """予定表の HTML から [{id, title, start}] を返す (start は Unix 秒)。"""
  _, found, rest = page.partition('id="contest-table-upcoming"')
  if not found:
    return []
  contests = []
  for row in _ROW_RE.findall(rest.split("</table>", 1)[0]):
    when, abc = _TIME_RE.search(row), _ABC_RE.search(row)
    if when and abc:
      start = datetime.strptime(when.group(1).strip(), "%Y-%m-%d %H:%M:%S%z")
      contests.append({"id": abc.group(1), "title": abc.group(2), "start": int(start.timestamp())})
  return contests


async def get_upcoming_abc(now=None):
  """予定中の ABC を返す。1時間に1回だけ取得し、失敗したら前回の結果を使う。"""
  now = time.time() if now is None else now
  if now - _cache["at"] >= REFRESH_SEC:
    _cache["at"] = now  # 失敗しても毎分アクセスしないよう、先に記録する
    try:
      status, page = await http_client.get("https://atcoder.jp/contests/", log="コンテスト予定を取得", as_text=True)
      if status == 200:
        _cache["contests"] = parse_upcoming_abc(page)
    except Exception as e:
      print(f"[contest_reminder] {type(e).__name__}: {e}")
  return _cache["contests"]


def due_reminders(contests, db_file, now=None):
  """いまリマインドすべきで、まだ送っていないコンテストを返す。"""
  now = time.time() if now is None else now
  due = [c for c in contests if 0 < c["start"] - now <= REMIND_BEFORE_SEC]
  with db.connect(db_file) as conn:
    return [c for c in due if conn.execute(
      "SELECT 1 FROM auto_posted_contests WHERE contest_id = ?", (f"reminder:{c['id']}",)
    ).fetchone() is None]


def mark_reminded(contest_id, db_file):
  with db.connect(db_file) as conn:
    conn.execute("INSERT OR IGNORE INTO auto_posted_contests VALUES (?, ?)", (f"reminder:{contest_id}", time.time()))

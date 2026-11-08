import time
from atcoder import http_client

async def get_latest_ended_abc_number(with_end_time=False):
  """直近に終了したABCの番号を返す。with_end_time=True なら (番号, 終了Unix秒) を返す。"""
  now = time.time()
  url = "https://kenkoooo.com/atcoder/resources/contests.json"
  try:
    contests = await http_client.get_json(url, log="コンテスト一覧取得")
  except Exception:
    return None

  abc_contests = [
    c for c in contests
    if c["id"].startswith("abc")
    and c["start_epoch_second"] + c["duration_second"] < now
  ]
  if not abc_contests:
    return None

  latest = max(abc_contests, key=lambda c: c["start_epoch_second"])
  try:
    number = int(latest["id"][3:])
  except (ValueError, IndexError):
    return None
  if with_end_time:
    return number, latest["start_epoch_second"] + latest["duration_second"]
  return number

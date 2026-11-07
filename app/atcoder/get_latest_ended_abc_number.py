import aiohttp
import time
import discord_logger

async def get_latest_ended_abc_number(with_end_time=False):
  """直近に終了したABCの番号を返す。with_end_time=True なら (番号, 終了Unix秒) を返す。"""
  now = time.time()
  url = "https://kenkoooo.com/atcoder/resources/contests.json"
  await discord_logger.log_api("APIを叩いた: コンテスト一覧取得 (get_latest_ended_abc_number)")
  try:
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    async with aiohttp.ClientSession() as session:
      async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        contests = await resp.json(content_type=None)
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

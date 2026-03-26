import aiohttp
import time
import discord_logger

async def get_upcoming_abc_contests(days=14):
  now = time.time()
  limit = now + days * 86400
  url = "https://kenkoooo.com/atcoder/resources/contests.json"
  await discord_logger.log_api("APIを叩いた: 今後のコンテスト取得 (get_upcoming_abc_contests)")
  try:
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    async with aiohttp.ClientSession() as session:
      async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        contests = await resp.json(content_type=None)
  except Exception:
    return []

  upcoming = [
    c for c in contests
    if c["id"].startswith("abc")
    and now <= c["start_epoch_second"] <= limit
  ]
  upcoming.sort(key=lambda c: c["start_epoch_second"])
  return upcoming

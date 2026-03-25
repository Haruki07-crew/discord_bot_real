import aiohttp
import sqlite3
from datetime import datetime
import discord_logger

async def get_latest_rating(atcoder_name):
  url = f"https://atcoder.jp/users/{atcoder_name}/history/json"
  _timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
  print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}][get_latest_rating] HTTP request: {url}")
  await discord_logger.log_api(f"APIを叩いた: AtCoderレート取得 (get_latest_rating) [{atcoder_name}]")
  try:
    async with aiohttp.ClientSession() as session:
      async with session.get(url, timeout=_timeout) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
  except Exception as e:
    print(f"[get_latest_rating] {atcoder_name}: {type(e).__name__}: {e}")
    return f"{atcoder_name}は存在しません"
  if not isinstance(data, list) or len(data) == 0:
    return f"{atcoder_name}は存在しません"
  latest_rating = data[-1]["NewRating"]
  return f"{atcoder_name}の現在のレートは{latest_rating}です"

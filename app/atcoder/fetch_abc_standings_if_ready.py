import aiohttp
import discord_logger
from atcoder.build_abc_standings import build_abc_standings

async def fetch_abc_standings_if_ready(contest_number, db_file):
  """
  ABCコンテストの results/json を1回だけ叩いて、
  レーティング確定済みなら (rated, unrated) を返す。
  未確定またはエラー時は None を返す。
  """
  contest_id = f"abc{contest_number:03d}"
  url = f"https://atcoder.jp/contests/{contest_id}/results/json"
  await discord_logger.log_api(f"APIを叩いた: ABCスタンディング取得 [{contest_id}]")

  try:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AtCoderBot/1.0)"}
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    async with aiohttp.ClientSession(headers=headers) as session:
      async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
  except Exception:
    return None

  if not isinstance(data, list) or len(data) == 0:
    return None

  rated_entries = [e for e in data if e.get("IsRated", False)]
  if not any(e.get("NewRating", 0) > 0 for e in rated_entries):
    return None

  return await build_abc_standings(data, contest_number, db_file)

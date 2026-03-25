import aiohttp
from datetime import datetime, timezone, timedelta
import discord_logger

problem_cache = None
JST = timezone(timedelta(hours=9))

async def fetch_problem():
  global problem_cache
  if problem_cache is None:
    url = "https://kenkoooo.com/atcoder/resources/problem-models.json"
    await discord_logger.log_api("APIを叩いた: 問題モデル取得 (fetch_problem)")
    async with aiohttp.ClientSession() as session:
      async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        problem_cache = await resp.json(content_type=None)
  return problem_cache

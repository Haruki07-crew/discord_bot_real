import aiohttp
import discord_logger
from atcoder.build_abc_standings import build_abc_standings

async def get_abc_standings(contest_number, db_file):
  contest_id = f"abc{contest_number:03d}"
  url = f"https://atcoder.jp/contests/{contest_id}/results/json"
  await discord_logger.log_api(f"APIを叩いた: ABCスタンディング取得 (get_abc_standings) [{contest_id}]")

  _timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
  _headers = {"User-Agent": "Mozilla/5.0 (compatible; AtCoderBot/1.0)"}
  async with aiohttp.ClientSession(headers=_headers) as session:
    async with session.get(url, timeout=_timeout) as resp:
      resp.raise_for_status()
      data = await resp.json(content_type=None)

  if not isinstance(data, list):
    return [], []

  return await build_abc_standings(data, contest_number, db_file)

import aiohttp
import discord_logger

async def is_abc_results_ready(contest_number):
  contest_id = f"abc{contest_number:03d}"
  url = f"https://atcoder.jp/contests/{contest_id}/results/json"
  await discord_logger.log_api(f"APIを叩いた: ABC結果確認 (is_abc_results_ready) [{contest_id}]")
  try:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AtCoderBot/1.0)"}
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    async with aiohttp.ClientSession(headers=headers) as session:
      async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    if not isinstance(data, list) or len(data) == 0:
      return False
    rated_entries = [e for e in data if e.get("IsRated", False)]
    return any(e.get("NewRating", 0) > 0 for e in rated_entries)
  except Exception:
    return False

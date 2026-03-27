import aiohttp
import sqlite3
import discord_logger

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

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT atcoder_name, discord_name FROM users")
    user_dict = {row[0]: row[1] for row in cursor.fetchall()}

  if not user_dict:
    return [], []

  rated = []
  unrated = []

  for entry in data:
    atcoder_name = entry.get("UserScreenName", "")
    if atcoder_name not in user_dict:
      continue

    old_rating = entry.get("OldRating", 0)
    new_rating = entry.get("NewRating", 0)
    record = {
      "atcoder_name": atcoder_name,
      "discord_name": user_dict[atcoder_name],
      "rank": entry.get("Place", 0),
      "performance": entry.get("Performance", 0),
      "old_rating": old_rating,
      "new_rating": new_rating,
      "rate_change": new_rating - old_rating,
    }

    if entry.get("IsRated", False):
      rated.append(record)
    else:
      unrated.append(record)

  rated.sort(key=lambda x: x["rank"])
  unrated.sort(key=lambda x: x["rank"])

  return rated, unrated

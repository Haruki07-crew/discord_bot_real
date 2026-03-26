import aiohttp
import sqlite3
import discord_logger

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

  standings = data

  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT atcoder_name, discord_name FROM users")
    user_dict = {row[0]: row[1] for row in cursor.fetchall()}

  if not user_dict:
    return [], []

  rated = []
  unrated = []

  for entry in standings:
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

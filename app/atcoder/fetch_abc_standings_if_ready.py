import aiohttp
import time
from atcoder.parse_atcoder_time import parse_atcoder_time
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
    # コンテストが unrated になった場合はレートが確定しないので、終了から24時間経っていれば確定扱いにする
    # (そうしないと以降のABCの自動投稿が全て止まる)
    end_dt = parse_atcoder_time(data[0].get("EndTime"))
    if end_dt is None or time.time() - end_dt.timestamp() < 24 * 60 * 60:
      return None

  rated, unrated = await build_abc_standings(data, contest_number, db_file)

  # kenkoooo はコンテストの提出を遅れて取り込むことがあり、取り込み前だと全員のAC数が0になる。
  # 一度投稿すると次のコンテストへ進んでしまうので、全員0なら終了から48時間までは待って再試行する。
  participants = rated + unrated
  if participants and all(d["ac_count"] == 0 for d in participants):
    end_dt = parse_atcoder_time(data[0].get("EndTime"))
    if end_dt is not None and time.time() - end_dt.timestamp() < 48 * 60 * 60:
      print(f"[fetch_abc_standings_if_ready] {contest_id}: kenkoooo にまだ提出が無いため待機")
      return None

  return rated, unrated

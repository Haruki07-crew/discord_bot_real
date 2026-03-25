import aiohttp
import asyncio
import math
from datetime import datetime, timezone, timedelta
import discord_logger

async def count_period_ac2(atcoder_name, day):
  # fetch_problem と get_diff は atcoder.problem から使用
  from atcoder.fetch_problem import fetch_problem
  from atcoder.get_diff import get_diff
  model = await fetch_problem()
  time_difference = timezone(timedelta(hours=9))
  now = datetime.now(time_difference)
  if day == 1:
    start_time = datetime(now.year, now.month, now.day, tzinfo=time_difference)
  else:
    start_time = now - timedelta(days=day)
  unix_time = int(start_time.timestamp())
  s = set()
  ac_point_sum = 0
  diff_sum = 0
  last_submission_id = None
  async with aiohttp.ClientSession() as session:
    while True:
      url = f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions?user={atcoder_name}&from_second={unix_time}"
      if last_submission_id:
        url += f"&from_id={last_submission_id + 1}"
      await discord_logger.log_api(f"APIを叩いた: 期間AC数取得(diff付き) (count_period_ac2) [{atcoder_name}]")
      async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await resp.json(content_type=None)
      if not data:
        break
      for submission in data:
        last_submission_id = submission["id"]
        if submission["result"] == "AC":
          problem_id = submission["problem_id"]
          if "ahc" not in problem_id and problem_id not in s:
            s.add(problem_id)
            ac_point_sum += submission["point"]
            raw_diff = model.get(problem_id, {}).get("difficulty")
            diff_sum += get_diff(raw_diff) or 0
      if len(data) < 500:
        break
      await asyncio.sleep(0.8)
  return [len(s), math.ceil(ac_point_sum), diff_sum]

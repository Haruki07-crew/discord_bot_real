import asyncio

async def initial_fetch_user_data(atcoder_name, db_file):
  from atcoder.fetch_and_cache_contest_history import fetch_and_cache_contest_history
  from atcoder.fetch_and_cache_ac_submissions import fetch_and_cache_ac_submissions
  await fetch_and_cache_contest_history(atcoder_name, db_file)
  await asyncio.sleep(1.0)
  await fetch_and_cache_ac_submissions(atcoder_name, db_file)

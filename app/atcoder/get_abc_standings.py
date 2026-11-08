from atcoder import http_client
from atcoder.build_abc_standings import build_abc_standings


async def get_abc_standings(contest_number, db_file):
  contest_id = f"abc{contest_number:03d}"
  url = f"https://atcoder.jp/contests/{contest_id}/results/json"
  data = await http_client.get_json(url, log=f"ABCスタンディング取得 [{contest_id}]")
  if not isinstance(data, list):
    return [], []
  return await build_abc_standings(data, contest_number, db_file)

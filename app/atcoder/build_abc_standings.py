import sqlite3
from atcoder.get_contest_ac_count import get_contest_ac_count
from atcoder.parse_atcoder_time import parse_atcoder_time
from atcoder.fetch_and_cache_ac_submissions import fetch_and_cache_ac_submissions


async def build_abc_standings(results, contest_number, db_file):
  """AtCoder の results/json の結果から登録ユーザーを抽出し (rated, unrated) を返す。

  - AtCoder のユーザー名は大文字小文字を区別しないため、小文字で照合する
  - コンテスト中のAC数を正しく数えるため、参加者の提出キャッシュを先に更新する
    (daily_update は1:00にしか走らないので、コンテスト直後はキャッシュが古い)
  - コンテスト終了時刻は results/json の EndTime を使う
    (contest_history は daily_update まで更新されず、unrated 参加者の行も無いため)
  """
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT atcoder_name, discord_name FROM users")
    users_by_lower = {row[0].lower(): (row[0], row[1]) for row in cursor.fetchall()}

  if not users_by_lower:
    return [], []

  participants = []
  for entry in results:
    screen_name = entry.get("UserScreenName", "")
    user = users_by_lower.get(screen_name.lower())
    if user is not None:
      participants.append((entry, user))

  # 1秒に1回の制限は http_client が守るので、ここでは待たない
  for _entry, (atcoder_name, _discord_name) in participants:
    try:
      await fetch_and_cache_ac_submissions(atcoder_name, db_file)
    except Exception as e:
      print(f"[build_abc_standings] refresh failed for {atcoder_name}: {e}")

  rated = []
  unrated = []
  for entry, (atcoder_name, discord_name) in participants:
    old_rating = entry.get("OldRating", 0)
    new_rating = entry.get("NewRating", 0)

    ac_count = 0
    end_dt = parse_atcoder_time(entry.get("EndTime"))
    if end_dt is not None:
      ac_count = get_contest_ac_count(atcoder_name, contest_number, int(end_dt.timestamp()), db_file)

    record = {
      "atcoder_name": atcoder_name,
      "discord_name": discord_name,
      "rank": entry.get("Place", 0),
      "performance": max(entry.get("Performance", 0), 0),
      "old_rating": old_rating,
      "new_rating": new_rating,
      "rate_change": new_rating - old_rating,
      "ac_count": ac_count,
    }

    if entry.get("IsRated", False):
      rated.append(record)
    else:
      unrated.append(record)

  rated.sort(key=lambda x: x["rank"])
  unrated.sort(key=lambda x: x["rank"])

  return rated, unrated

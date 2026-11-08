"""実績バッジの判定。"""
import time

from atcoder import db
from atcoder.get_ac_streak import get_ac_streak
from atcoder.problem_data import COLOR_BANDS, color_name, problem_difficulty

STREAK_BADGES = (7, 30, 100, 365)
AC_COUNT_BADGES = (100, 300, 500, 1000, 2000, 3000)
INITIALIZED = "_initialized"  # 初回判定済みの印 (過去の分をまとめて投稿しないため)


def _earned_badges(atcoder_name, db_file, models):
  """いま満たしている実績を {badge: 説明} で返す。"""
  with db.connect(db_file) as conn:
    problem_ids = [r[0] for r in conn.execute(
      "SELECT DISTINCT problem_id FROM ac_submissions_cache WHERE atcoder_name = ?", (atcoder_name,)
    )]
    contests = conn.execute(
      "SELECT contest_screen_name, new_rating FROM contest_history WHERE atcoder_name = ? ORDER BY end_time ASC",
      (atcoder_name,),
    ).fetchall()

  earned = {}
  streak = get_ac_streak(atcoder_name, db_file)
  for days in STREAK_BADGES:
    if streak >= days:
      earned[f"streak:{days}"] = f"🔥 {days}日連続AC"
  for count in AC_COUNT_BADGES:
    if len(problem_ids) >= count:
      earned[f"ac:{count}"] = f"🎯 {count}問AC"
  for problem_id in problem_ids:
    difficulty = problem_difficulty(problem_id, models)
    if difficulty is not None and difficulty >= COLOR_BANDS[1][0]:
      name = color_name(difficulty)
      earned[f"diff:{name}"] = f"💎 初の{name}diff AC"
  if contests:
    rating = contests[-1][1]
    for lower, name in COLOR_BANDS[1:]:
      if rating >= lower:
        earned[f"color:{name}"] = f"🌈 {name}色に到達"
    if len(contests) >= 2 and rating > max(c[1] for c in contests[:-1]):
      earned[f"best:{contests[-1][0]}"] = f"📈 レート自己ベスト更新 ({rating})"
  return earned


def find_new_achievements(db_file, models):
  """未記録の実績を [(atcoder_name, discord_name, badge, 説明), ...] で返す。
  まだ判定したことがないユーザーは、過去の実績を黙って記録するだけで返さない。
  データの取得が済んでいないユーザーは飛ばす。投稿に成功したら record_achievements を呼ぶこと。"""
  with db.connect(db_file) as conn:
    users = conn.execute("""
      SELECT u.atcoder_name, u.discord_name FROM users u
      JOIN update_bookmark b ON b.atcoder_name = u.atcoder_name
      WHERE b.submission_last_fetch > 0 AND b.contest_last_fetched > 0
    """).fetchall()
    known = {}
    for name, badge in conn.execute("SELECT atcoder_name, badge FROM achievements"):
      known.setdefault(name, set()).add(badge)

  new = []
  for name, discord_name in users:
    earned = _earned_badges(name, db_file, models)
    if INITIALIZED not in known.get(name, set()):
      record_achievements([(name, b) for b in list(earned) + [INITIALIZED]], db_file)
      continue
    new.extend((name, discord_name, b, text) for b, text in earned.items() if b not in known[name])
  return new


def record_achievements(pairs, db_file):
  with db.connect(db_file) as conn:
    conn.executemany(
      "INSERT OR IGNORE INTO achievements VALUES (?, ?, ?)",
      [(name, badge, time.time()) for name, badge in pairs],
    )

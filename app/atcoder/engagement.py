"""おすすめ問題・精進スコア・比較・レート進捗・週次ふり返りの計算。"""
import random

from atcoder import db
from atcoder.count_period_ac import get_period_start_unix
from atcoder.problem_data import COLOR_BANDS, color_name, problem_difficulty, problem_score

RECOMMEND_BANDS = [("易しめ", -300, -100), ("ちょうどいい", -100, 100), ("挑戦", 100, 300)]
RECOMMEND_CONTEST_PREFIXES = ("abc", "arc", "agc")
NO_RATING_BASE = 200  # レートがまだ無い人はこの値を基準におすすめする


def get_solved_problems(atcoder_name, db_file):
  with db.connect(db_file) as conn:
    return {r[0] for r in conn.execute(
      "SELECT DISTINCT problem_id FROM ac_submissions_cache WHERE atcoder_name = ?", (atcoder_name,)
    )}


def pick_recommendations(rating, solved, models, problems, rng=random):
  """レート付近の未 AC 問題を、難易度帯ごとに1問ずつ選ぶ。戻り値: [(帯の名前, 問題ID, difficulty), ...]"""
  base = rating if rating and rating > 0 else NO_RATING_BASE
  picks = []
  for label, low, high in RECOMMEND_BANDS:
    candidates = []
    for problem_id, model in models.items():
      if problem_id in solved or problem_id not in problems or model.get("is_experimental"):
        continue
      if not problem_id.startswith(RECOMMEND_CONTEST_PREFIXES):
        continue
      difficulty = problem_difficulty(problem_id, models)
      if difficulty is not None and base + low <= difficulty < base + high:
        candidates.append((problem_id, difficulty))
    if candidates:
      problem_id, difficulty = rng.choice(sorted(candidates))
      picks.append((label, problem_id, difficulty))
  return picks


def get_period_score(atcoder_name, day, db_file, models, end_unix=None):
  """期間内の精進スコア。解き直しで稼げないよう、期間内に初めて AC した問題だけを数える。"""
  start = get_period_start_unix(day)
  end = end_unix if end_unix is not None else 2 ** 62
  with db.connect(db_file) as conn:
    rows = conn.execute("""
      SELECT problem_id FROM ac_submissions_cache WHERE atcoder_name = ?
      GROUP BY problem_id HAVING MIN(epoch_second) >= ? AND MIN(epoch_second) < ?
    """, (atcoder_name, start, end)).fetchall()
  return sum(problem_score(r[0], models) for r in rows)


def rating_progress_text(atcoder_name, db_file, recent=5):
  """「水色まであと43」とレート推移の文字列。レートが無ければ None。"""
  with db.connect(db_file) as conn:
    rows = conn.execute(
      "SELECT new_rating FROM contest_history WHERE atcoder_name = ? ORDER BY end_time DESC LIMIT ?",
      (atcoder_name, recent),
    ).fetchall()
  if not rows:
    return None
  rating = rows[0][0]
  trend = " → ".join(str(r[0]) for r in reversed(rows))
  next_bands = [(lower, name) for lower, name in COLOR_BANDS if lower > rating]
  if next_bands:
    lower, name = next_bands[0]
    return f"現在 **{rating}** ({color_name(rating)}色)　{name}色まであと **{lower - rating}**\n直近: {trend}"
  return f"現在 **{rating}** ({color_name(rating)}色)\n直近: {trend}"


def next_wall_slot(atcoder_name, latest_abc, db_file, contests=100):
  """直近 contests 回の ABC で、解いた割合が初めて50%を切る問題の記号と割合を返す。無ければ None。"""
  if latest_abc is None:
    return None
  first = max(1, latest_abc - contests + 1)
  ids = {f"abc{n:03d}" for n in range(first, latest_abc + 1)}
  solved = {}
  for problem_id in get_solved_problems(atcoder_name, db_file):
    contest, _, slot = problem_id.partition("_")
    if contest in ids:
      solved[slot] = solved.get(slot, 0) + 1
  for slot in "abcdef":
    ratio = solved.get(slot, 0) / len(ids)
    if ratio < 0.5:
      return slot.upper(), ratio
  return None

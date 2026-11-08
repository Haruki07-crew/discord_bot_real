"""問題の難易度・タイトルと、難易度・レートの色に関する処理。"""
import math
import time

from atcoder import http_client

CACHE_TTL_SEC = 24 * 60 * 60
# (下限, 色の名前)。レートと difficulty で共通
COLOR_BANDS = [
  (0, "灰"), (400, "茶"), (800, "緑"), (1200, "水"),
  (1600, "青"), (2000, "黄"), (2400, "橙"), (2800, "赤"),
]
DEFAULT_SCORE = 10  # 難易度が不明な問題の精進スコア

_cache = {"at": 0.0, "models": None, "problems": None}


def index_problems(problems):
  """問題ID → 問題情報の辞書を作る。ADT などにも同じ問題が載っているので、元のコンテストの情報を優先する。"""
  index = {}
  for p in problems:
    original = p["contest_id"] == p["id"].rsplit("_", 1)[0]
    if original or p["id"] not in index:
      index[p["id"]] = p
  return index


async def get_problem_data():
  """(models, problems) を返す。models: {問題ID: モデル}, problems: {問題ID: 問題情報}。
  1日1回だけ取得し、取り直しに失敗したら古いデータを使う。一度も取得できていなければ例外。"""
  if _cache["models"] is not None and time.time() - _cache["at"] < CACHE_TTL_SEC:
    return _cache["models"], _cache["problems"]
  try:
    models = await http_client.get_json("https://kenkoooo.com/atcoder/resources/problem-models.json", log="問題の難易度を取得")
    problems = await http_client.get_json("https://kenkoooo.com/atcoder/resources/problems.json", log="問題の一覧を取得")
  except Exception:
    if _cache["models"] is None:
      raise
    print("[problem_data] 取得に失敗したので古いデータを使います")
    return _cache["models"], _cache["problems"]
  _cache.update(at=time.time(), models=models, problems=index_problems(problems))
  return _cache["models"], _cache["problems"]


def clip_difficulty(raw):
  """AtCoder Problems と同じ補正。400未満の difficulty を正の値に収める。None はそのまま。"""
  if raw is None:
    return None
  return raw if raw >= 400 else round(400 / math.exp((400 - raw) / 400))


def problem_difficulty(problem_id, models):
  return clip_difficulty((models.get(problem_id) or {}).get("difficulty"))


def color_name(value):
  """レートや difficulty に対応する色の名前を返す。"""
  name = COLOR_BANDS[0][1]
  for lower, band in COLOR_BANDS:
    if value >= lower:
      name = band
  return name


def color_range(name):
  """色の名前から (下限, 上限(含まない)) を返す。"""
  for i, (lower, band) in enumerate(COLOR_BANDS):
    if band == name:
      upper = COLOR_BANDS[i + 1][0] if i + 1 < len(COLOR_BANDS) else 10 ** 9
      return lower, upper
  raise ValueError(name)


def problem_score(problem_id, models):
  """精進スコア。400上がるごとに2倍 (灰10, 茶20, 緑40, 水80, 青160, 黄320, 橙640, 赤1280)。"""
  difficulty = problem_difficulty(problem_id, models)
  if difficulty is None:
    return DEFAULT_SCORE
  return round(DEFAULT_SCORE * 2 ** (min(difficulty, 4000) / 400))


def problem_url(problem_id, problems):
  info = problems.get(problem_id)
  contest = info["contest_id"] if info else problem_id.rsplit("_", 1)[0]
  return f"https://atcoder.jp/contests/{contest}/tasks/{problem_id}"


def problem_link(problem_id, problems):
  """Discord の Embed 用のリンク文字列を返す。"""
  info = problems.get(problem_id) or {}
  title = (info.get("title") or problem_id).replace("[", "(").replace("]", ")")
  label = f"{info['contest_id'].upper()} {title}" if info.get("contest_id") else title
  return f"[{label}]({problem_url(problem_id, problems)})"

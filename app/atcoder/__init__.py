## @file __init__.py
## @brief atcoderパッケージの公開APIを定義する

from atcoder.get_latest_rating.get_latest_rating import get_latest_rating
from atcoder.get_latest_rating_nofstring.get_latest_rating_nofstring import get_latest_rating_nofstring
from atcoder.get_rate_heart.get_rate_heart import get_rate_heart
from atcoder.get_latest_rating_from_db.get_latest_rating_from_db import get_latest_rating_from_db
from atcoder.get_ac_count.get_ac_count import get_ac_count
from atcoder.count_period_ac.count_period_ac import count_period_ac
from atcoder.count_period_ac2.count_period_ac2 import count_period_ac2
from atcoder.AC_print.AC_print import AC_print
from atcoder.AC_fight.AC_fight import AC_fight
from atcoder.make_ranking.make_ranking import make_ranking
from atcoder.make_growth_ranking.make_growth_ranking import make_growth_ranking
from atcoder.fetch_problem.fetch_problem import fetch_problem
from atcoder.get_diff.get_diff import get_diff
from atcoder.init_progress_tables.init_progress_tables import init_progress_tables
from atcoder.parse_atcoder_time.parse_atcoder_time import parse_atcoder_time
from atcoder.fetch_and_cache_contest_history.fetch_and_cache_contest_history import fetch_and_cache_contest_history
from atcoder.fetch_and_cache_ac_submissions.fetch_and_cache_ac_submissions import fetch_and_cache_ac_submissions
from atcoder.initial_fetch_user_data.initial_fetch_user_data import initial_fetch_user_data
from atcoder.get_progress_data.get_progress_data import get_progress_data
from atcoder.create_progress_graph.create_progress_graph import create_progress_graph
from atcoder.get_ac_rate_change_data.get_ac_rate_change_data import get_ac_rate_change_data
from atcoder.create_ac_rate_graph.create_ac_rate_graph import create_ac_rate_graph
from atcoder.get_abc_standings.get_abc_standings import get_abc_standings
from atcoder.init_db.init_db import init_db
from atcoder.get_user_dict.get_user_dict import get_user_dict
from atcoder.get_registered_user.get_registered_user import get_registered_user
from atcoder.register_user.register_user import register_user
from atcoder.get_resister_id.get_resister_id import get_resister_id
from atcoder.delete_user.delete_user import delete_user
from atcoder.get_all_users_with_discord_id.get_all_users_with_discord_id import get_all_users_with_discord_id
from atcoder.is_contest_auto_posted.is_contest_auto_posted import is_contest_auto_posted
from atcoder.mark_contest_auto_posted.mark_contest_auto_posted import mark_contest_auto_posted

# main.py が使う CONTEST_CACHE_TTL と get_abc_graph_data, get_latest_ended_abc_number, is_abc_results_ready は
# contest_ranking.py から来ているが、今は get_abc_standings のみ実装済み
# 以下はダミー定義（main.pyがエラーにならないように）
CONTEST_CACHE_TTL = 3600

async def get_abc_graph_data():
  return None

async def get_latest_ended_abc_number():
  return None

async def is_abc_results_ready(_contest_number=None):
  return False

__all__ = [
  "get_latest_rating",
  "get_latest_rating_nofstring",
  "get_rate_heart",
  "get_latest_rating_from_db",
  "get_ac_count",
  "count_period_ac",
  "count_period_ac2",
  "AC_print",
  "AC_fight",
  "make_ranking",
  "make_growth_ranking",
  "fetch_problem",
  "get_diff",
  "CONTEST_CACHE_TTL",
  "init_progress_tables",
  "parse_atcoder_time",
  "fetch_and_cache_contest_history",
  "fetch_and_cache_ac_submissions",
  "initial_fetch_user_data",
  "get_progress_data",
  "create_progress_graph",
  "get_ac_rate_change_data",
  "create_ac_rate_graph",
  "get_abc_standings",
  "get_abc_graph_data",
  "get_latest_ended_abc_number",
  "is_abc_results_ready",
  "init_db",
  "get_user_dict",
  "get_registered_user",
  "register_user",
  "get_resister_id",
  "delete_user",
  "get_all_users_with_discord_id",
  "is_contest_auto_posted",
  "mark_contest_auto_posted",
]

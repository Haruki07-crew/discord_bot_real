"""AtCoder のデータ取得・集計・グラフ作成。main.py は `from atcoder import *` で使う。
新しい関数を足したら、下の import と __all__ の両方に追加する。"""

# ユーザー管理
from atcoder.init_db import init_db
from atcoder.init_progress_tables import init_progress_tables
from atcoder.register_user import register_user
from atcoder.delete_user import delete_user
from atcoder.get_user_dict import get_user_dict
from atcoder.get_registered_user import get_registered_user
from atcoder.get_register_id import get_register_id
from atcoder.get_registered_by_discord_id import get_registered_by_discord_id
from atcoder.atcoder_user_exists import atcoder_user_exists

# データ取得・キャッシュ
from atcoder.fetch_and_cache_contest_history import fetch_and_cache_contest_history
from atcoder.fetch_and_cache_ac_submissions import fetch_and_cache_ac_submissions
from atcoder.initial_fetch_user_data import initial_fetch_user_data, refresh_users_data
from atcoder.backup_database import backup_database
from atcoder.background_sync import sync_step, request_contest_resync, get_oldest_submission_sync

# 集計
from atcoder.parse_atcoder_time import parse_atcoder_time
from atcoder.get_ac_count import get_ac_count
from atcoder.count_period_ac import count_period_ac, get_period_start_unix
from atcoder.AC_fight import AC_fight
from atcoder.make_growth_ranking import make_growth_ranking
from atcoder.get_ac_rate_change_data import get_ac_rate_change_data
from atcoder.get_progress_data import get_progress_data
from atcoder.get_ac_streak import get_ac_streak
from atcoder.get_latest_rating_from_db import get_latest_rating_from_db
from atcoder.get_rate_heart import get_rate_heart

# グラフ
from atcoder.create_ac_rate_graph import create_ac_rate_graph
from atcoder.create_progress_graph import create_progress_graph
from atcoder.create_weekly_graph import create_weekly_graph

# ABC コンテスト
from atcoder.get_abc_standings import get_abc_standings
from atcoder.fetch_abc_standings_if_ready import fetch_abc_standings_if_ready
from atcoder.get_contest_ac_count import get_contest_ac_count
from atcoder.get_latest_ended_abc_number import get_latest_ended_abc_number
from atcoder.get_prev_contest import get_prev_contest
from atcoder.set_prev_contest import set_prev_contest

# 週次サイクル
from atcoder.weekly_cycle_helpers import (
  get_weekly_cycle_state, advance_weekly_cycle, save_weekly_snapshot, get_weekly_snapshots,
  get_weekly_last_posted, set_weekly_last_posted,
)

__all__ = [
  "init_db", "init_progress_tables", "register_user", "delete_user", "get_user_dict",
  "get_registered_user", "get_register_id", "get_registered_by_discord_id", "atcoder_user_exists",
  "fetch_and_cache_contest_history", "fetch_and_cache_ac_submissions",
  "initial_fetch_user_data", "refresh_users_data", "backup_database",
  "sync_step", "request_contest_resync", "get_oldest_submission_sync",
  "parse_atcoder_time", "get_ac_count", "count_period_ac", "get_period_start_unix", "AC_fight",
  "make_growth_ranking", "get_ac_rate_change_data", "get_progress_data", "get_ac_streak",
  "get_latest_rating_from_db", "get_rate_heart",
  "create_ac_rate_graph", "create_progress_graph", "create_weekly_graph",
  "get_abc_standings", "fetch_abc_standings_if_ready", "get_contest_ac_count",
  "get_latest_ended_abc_number", "get_prev_contest", "set_prev_contest",
  "get_weekly_cycle_state", "advance_weekly_cycle", "save_weekly_snapshot", "get_weekly_snapshots",
  "get_weekly_last_posted", "set_weekly_last_posted",
]

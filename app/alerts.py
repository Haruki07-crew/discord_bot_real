"""管理者への通知と、直近のエラーの記録。

- notify_admin: 管理者 (ADMIN_ID) に DM を送る。同じ key の通知は cooldown 秒の間に1回だけ (障害時に DM が大量に届かないように)。
- record_error: 直近のエラーを保存し、/admin status で見られるようにする。
"""
import time
import traceback
from collections import deque

DEFAULT_COOLDOWN_SEC = 60 * 60
MAX_RECENT_ERRORS = 10

_client = None
_admin_id = None
_last_sent = {}
recent_errors = deque(maxlen=MAX_RECENT_ERRORS)  # (unix秒, 場所, 1行の説明)
started_at = time.time()


def setup(client, admin_id):
  global _client, _admin_id
  _client = client
  _admin_id = admin_id


def record_error(where, error):
  """エラーを記録してログに出す。戻り値: 通知などに使う1行の説明"""
  summary = f"{type(error).__name__}: {error}"[:300]
  recent_errors.append((time.time(), where, summary))
  print(f"[{where}] {summary}")
  traceback.print_exception(type(error), error, error.__traceback__)
  return summary


async def notify_admin(key, text, cooldown=DEFAULT_COOLDOWN_SEC):
  """管理者に DM を送る。cooldown 秒以内に同じ key で送っていれば送らない。戻り値: 送ったかどうか"""
  now = time.time()
  if now - _last_sent.get(key, float("-inf")) < cooldown:
    return False
  _last_sent[key] = now
  print(f"[alert] {text}")
  if _client is None or not _admin_id:
    return False
  try:
    user = _client.get_user(int(_admin_id)) or await _client.fetch_user(int(_admin_id))
    await user.send(f"🚨 {text}"[:1900])
    return True
  except Exception as e:
    print(f"[alert] DM の送信に失敗: {e}")
    return False

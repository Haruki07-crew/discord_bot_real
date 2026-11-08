"""テスト用の共通処理。

main.py は読み込むと Discord に接続してしまうので、最後の server_thread() と client.run() を除いて
exec し、その名前空間 (コマンド・タスク・ヘルパー) を返す。Discord の代わりに偽のオブジェクトを使う。
"""
import datetime as _dt
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
  sys.path.insert(0, APP)

JST = _dt.timezone(_dt.timedelta(hours=9))


def load_main(db_path=None):
  """main.py を Discord に接続せずに読み込み、名前空間を返す。DB は一時ファイル (または db_path)。"""
  if db_path is None:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
  os.environ["DB_PATH"] = db_path
  import config
  config.DB_PATH = db_path
  with open(os.path.join(APP, "main.py"), encoding="utf-8") as f:
    src = f.read()
  marker = "server_thread()\nclient.run(config.DISCORD_TOKEN)"
  assert marker in src, "main.py の末尾が想定と違う (support.load_main を更新すること)"
  ns = {"__name__": "main_under_test"}
  exec(compile(src.replace(marker, ""), os.path.join(APP, "main.py"), "exec"), ns)
  ns["init_db"](db_path)
  return ns


def freeze_now(ns, when):
  """main.py の datetime.datetime.now() を固定する (when は JST の aware datetime)。"""
  class Frozen(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
      return when.astimezone(tz) if tz else when
  ns["datetime"] = types.SimpleNamespace(
    datetime=Frozen, timezone=_dt.timezone, timedelta=_dt.timedelta, time=_dt.time
  )


class Recorder:
  """送信されたメッセージを記録する。"""
  def __init__(self):
    self.sent = []

  def titles(self):
    return [e.title if e is not None else c for _, e, c in self.sent]


class FakeChannel:
  def __init__(self, recorder, fail_times=0):
    self.recorder = recorder
    self.fail_times = fail_times

  async def send(self, content=None, embed=None, file=None, **kw):
    if self.fail_times > 0:
      self.fail_times -= 1
      raise RuntimeError("simulated send failure")
    self.recorder.sent.append(("channel", embed, content))


class _FakeFollowup:
  def __init__(self, recorder):
    self.recorder = recorder

  async def send(self, content=None, embed=None, **kw):
    self.recorder.sent.append(("followup", embed, content))


class _FakeResponse:
  async def defer(self, **kw):
    pass

  def is_done(self):
    return True


class FakeInteraction:
  def __init__(self, recorder, user_id=1):
    self.recorder = recorder
    self.response = _FakeResponse()
    self.followup = _FakeFollowup(recorder)
    self.created_at = _dt.datetime.now(_dt.timezone.utc)
    self.user = types.SimpleNamespace(id=user_id)
    self.command = None

  async def edit_original_response(self, content=None, embed=None, attachments=None, **kw):
    self.recorder.sent.append(("edit", embed, content))


async def no_refresh(*args, **kwargs):
  """refresh_users_data の代わり (ネットワークに出ない)。"""
  return None

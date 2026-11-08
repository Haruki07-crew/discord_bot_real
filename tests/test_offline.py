"""ネットワークにも Discord にも出ないテスト。CI で毎回実行する。

実行: python -m unittest discover -s tests -v
"""
import asyncio
import datetime as _dt
import sqlite3
import time
import unittest

import support
from support import JST, Recorder, FakeChannel, FakeInteraction, load_main, freeze_now, no_refresh


def today_start():
  now = _dt.datetime.now(JST)
  return _dt.datetime(now.year, now.month, now.day, tzinfo=JST)


def add_user(db, name, display="x", uid=1):
  with sqlite3.connect(db) as c:
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (name, display, uid, uid))
    # 提出の取得に成功済みの状態にする (キャッシュが使われる)
    c.execute(
      "INSERT OR REPLACE INTO update_bookmark (atcoder_name, contest_last_fetched, submission_last_id, submission_cache_from, submission_last_fetch) VALUES (?, ?, 0, 0, ?)",
      (name, time.time(), time.time()),
    )


def add_ac(db, name, sid, problem, epoch, point=100):
  with sqlite3.connect(db) as c:
    c.execute("INSERT INTO ac_submissions_cache VALUES (?, ?, ?, ?, ?)", (name, sid, problem, int(epoch), point))


def add_contest(db, name, contest, end_dt, old, new):
  with sqlite3.connect(db) as c:
    c.execute("INSERT INTO contest_history VALUES (?, ?, ?, ?, ?)", (name, contest, end_dt.isoformat(), new, old))


class Base(unittest.TestCase):
  def setUp(self):
    self.ns = load_main()
    self.db = self.ns["DB_FILE"]
    self.rec = Recorder()

  def run_async(self, coro):
    return asyncio.run(coro)


class TestPeriod(Base):
  def test_period_counts_today_as_one_day(self):
    from atcoder.count_period_ac import get_period_start_unix
    t0 = today_start()
    self.assertEqual(get_period_start_unix(1), int(t0.timestamp()))
    self.assertEqual(get_period_start_unix(7), int((t0 - _dt.timedelta(days=6)).timestamp()))
    self.assertEqual(get_period_start_unix(8), int((t0 - _dt.timedelta(days=7)).timestamp()))


class TestCounting(Base):
  def test_count_period_ac_unique_and_end_bound(self):
    t0 = today_start()
    add_user(self.db, "alice")
    add_ac(self.db, "alice", 1, "abc100_a", t0.timestamp() + 10, 100)
    add_ac(self.db, "alice", 2, "abc100_a", t0.timestamp() + 20, 100)  # 同じ問題の再AC
    add_ac(self.db, "alice", 3, "abc100_b", t0.timestamp() + 30, 200)
    add_ac(self.db, "alice", 4, "abc100_c", t0.timestamp() - 10, 300)  # 昨日
    count = self.run_async(self.ns["count_period_ac"]("alice", 1, self.db))
    self.assertEqual(count, [2, 300])
    count = self.run_async(self.ns["count_period_ac"]("alice", 1, self.db, end_unix=int(t0.timestamp()) + 25))
    self.assertEqual(count, [1, 100])

  def test_zero_submission_user_uses_cache(self):
    add_user(self.db, "nobody")
    self.assertEqual(self.run_async(self.ns["get_ac_count"]("nobody", self.db)), 0)

  def test_contest_ac_count_window(self):
    from atcoder.get_contest_ac_count import get_contest_ac_count
    end = 1_800_000_000
    add_user(self.db, "bob")
    add_ac(self.db, "bob", 1, "abc480_a", end - 100 * 60)      # 開始ちょうど
    add_ac(self.db, "bob", 2, "abc480_b", end)                 # 終了ちょうど
    add_ac(self.db, "bob", 3, "abc480_c", end - 100 * 60 - 1)  # 開始前
    add_ac(self.db, "bob", 4, "abc479_d", end - 60)            # 別コンテスト
    self.assertEqual(get_contest_ac_count("bob", 480, end, self.db), 2)

  def test_rate_change_end_bound(self):
    t0 = today_start()
    add_user(self.db, "carol")
    add_contest(self.db, "carol", "abc1", t0 - _dt.timedelta(days=2), 1000, 1100)
    add_contest(self.db, "carol", "abc2", t0 + _dt.timedelta(hours=1), 1100, 1150)
    f = self.ns["get_ac_rate_change_data"]
    self.assertEqual(self.run_async(f({"carol": "C"}, 7, self.db))["carol"]["rate_change"], 150)
    self.assertEqual(
      self.run_async(f({"carol": "C"}, 7, self.db, end_unix=int(t0.timestamp())))["carol"]["rate_change"], 100
    )


class TestEmbeds(Base):
  def test_build_embeds_respects_limits(self):
    fields = [(f"user{i}" + "名" * 300, "x" * 2000) for i in range(60)]
    embeds = self.ns["build_embeds"]("T" * 300, 0, None, fields)
    for e in embeds:
      self.assertLessEqual(len(e.fields), 25)
      self.assertLessEqual(len(e), 6000)
      self.assertLessEqual(len(e.title), 256)
      for f in e.fields:
        self.assertLessEqual(len(f.name), 256)
        self.assertLessEqual(len(f.value), 1024)
    self.assertEqual(sum(len(e.fields) for e in embeds), 60)

  def test_lines_to_fields(self):
    fields = self.ns["lines_to_fields"]("U", ["y" * 100 for _ in range(30)])
    self.assertTrue(all(len(v) <= 1024 for _, v in fields))
    self.assertEqual(sum(v.count("y" * 100) for _, v in fields), 30)


class TestNames(Base):
  def test_valid_names(self):
    ok = self.ns["is_valid_atcoder_name"]
    for name in ["abc", "hanaosi", "Un_titled", "_x1", "a" * 16]:
      self.assertTrue(ok(name), name)
    for name in ["ab", "a" * 17, "x/../..", "hanaosi?a", "a b", "名前名前"]:
      self.assertFalse(ok(name), name)

  def test_register_rejects_invalid_name_without_network(self):
    it = FakeInteraction(self.rec)
    self.run_async(self.ns["user_register"].callback(it, "x/../..", "z"))
    self.assertIn("存在しません", self.rec.titles()[0])


class TestUsers(Base):
  def test_unregister_removes_caches(self):
    add_user(self.db, "dave", uid=1)
    add_ac(self.db, "dave", 1, "abc1_a", 1)
    it = FakeInteraction(self.rec, user_id=1)
    self.run_async(self.ns["user_unregister"].callback(it, "DAVE"))
    with sqlite3.connect(self.db) as c:
      for table in ("users", "ac_submissions_cache", "update_bookmark"):
        self.assertEqual(c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

  def test_unregister_by_other_user_is_refused(self):
    add_user(self.db, "erin", uid=1)
    it = FakeInteraction(self.rec, user_id=999)
    self.run_async(self.ns["user_unregister"].callback(it, "erin"))
    with sqlite3.connect(self.db) as c:
      self.assertEqual(c.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)


class TestWeekly(Base):
  def setUp(self):
    super().setUp()
    self.ns["refresh_users_data"] = no_refresh
    self.ns["client"].get_channel = lambda _id: FakeChannel(self.rec)
    self.ns["ranking_channel_id"] = 123
    add_user(self.db, "frank", "F")
    monday = today_start() - _dt.timedelta(days=today_start().weekday())
    add_ac(self.db, "frank", 1, "abc1_a", (monday - _dt.timedelta(days=1)).timestamp())  # 先週の日曜
    add_ac(self.db, "frank", 2, "abc1_b", (monday + _dt.timedelta(minutes=5)).timestamp())  # 今週
    self.monday = monday

  def test_posts_once_per_monday(self):
    freeze_now(self.ns, self.monday + _dt.timedelta(minutes=15))
    self.run_async(self.ns["weekly_ranking_post"].coro())
    self.run_async(self.ns["weekly_ranking_post"].coro())
    weekly = [t for t in self.rec.titles() if t and "Diligence" in t]
    self.assertEqual(len(weekly), 1)
    self.assertEqual(self.ns["get_weekly_cycle_state"](self.db), (1, 1))
    snaps = self.ns["get_weekly_snapshots"](1, self.db)
    self.assertEqual(snaps["frank"][0][1], 1)  # 日曜のACだけが先週分

  def test_catch_up_only_after_schedule(self):
    freeze_now(self.ns, self.monday + _dt.timedelta(minutes=10))
    self.run_async(self.ns["catch_up_weekly_ranking_post"]())
    self.assertEqual(self.rec.sent, [])
    freeze_now(self.ns, self.monday + _dt.timedelta(hours=9))
    self.run_async(self.ns["catch_up_weekly_ranking_post"]())
    self.assertTrue(any(t and "Diligence" in t for t in self.rec.titles()))


class TestBackup(Base):
  def test_backup_keeps_latest(self):
    import os
    from atcoder.backup_database import backup_database
    add_user(self.db, "gina")
    path = backup_database(self.db, keep=2)
    with sqlite3.connect(path) as c:
      self.assertEqual(c.execute("SELECT atcoder_name FROM users").fetchall(), [("gina",)])
    backup_dir = os.path.dirname(path)
    for d in ("20000101", "20000102", "20000103"):
      open(os.path.join(backup_dir, f"database-{d}.db"), "w").close()
    backup_database(self.db, keep=2)
    remaining = sorted(f for f in os.listdir(backup_dir) if f.startswith("database-"))
    self.assertEqual(len(remaining), 2)
    self.assertIn(os.path.basename(path), remaining)


class TestRateLimit(unittest.TestCase):
  def test_same_host_is_spaced_and_other_hosts_are_not(self):
    from atcoder import http_client
    original = http_client.MIN_INTERVAL_SEC
    http_client.MIN_INTERVAL_SEC = 0.2
    try:
      async def run():
        stamps = []
        async def hit(host):
          await http_client.wait_turn(host)
          stamps.append((host, time.monotonic()))
        await asyncio.gather(*(hit("a.example") for _ in range(4)), hit("b.example"))
        return stamps
      stamps = asyncio.run(run())
    finally:
      http_client.MIN_INTERVAL_SEC = original
    a = sorted(t for h, t in stamps if h == "a.example")
    gaps = [b - a_ for a_, b in zip(a, a[1:])]
    self.assertTrue(all(g >= 0.19 for g in gaps), gaps)
    b_time = [t for h, t in stamps if h == "b.example"][0]
    self.assertLess(b_time - a[0], 0.1)  # 別ホストは待たされない


class TestLogger(unittest.TestCase):
  def test_chunks_fit_discord_limit(self):
    import discord_logger
    chunks = list(discord_logger._chunks(["z" * 300 for _ in range(50)]))
    self.assertTrue(all(len(c) <= 2000 for c in chunks))
    self.assertEqual(sum(c.count("z" * 300) for c in chunks), 50)


if __name__ == "__main__":
  unittest.main()

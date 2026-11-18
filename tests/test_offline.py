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
from atcoder.db import connect as dbconn


def today_start():
  now = _dt.datetime.now(JST)
  return _dt.datetime(now.year, now.month, now.day, tzinfo=JST)


def add_user(db, name, display="x", uid=1):
  with dbconn(db) as c:
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (name, display, uid, uid))
    # 提出の取得に成功済みの状態にする (キャッシュが使われる)
    c.execute(
      "INSERT OR REPLACE INTO update_bookmark (atcoder_name, contest_last_fetched, submission_last_id, submission_cache_from, submission_last_fetch) VALUES (?, ?, 0, 0, ?)",
      (name, time.time(), time.time()),
    )


def add_ac(db, name, sid, problem, epoch, point=100):
  with dbconn(db) as c:
    c.execute("INSERT INTO ac_submissions_cache VALUES (?, ?, ?, ?, ?)", (name, sid, problem, int(epoch), point))


def add_contest(db, name, contest, end_dt, old, new):
  with dbconn(db) as c:
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
  def test_count_period_ac_same_day_once(self):
    t0 = today_start()
    add_user(self.db, "alice")
    add_ac(self.db, "alice", 1, "abc100_a", t0.timestamp() + 10, 100)
    add_ac(self.db, "alice", 2, "abc100_a", t0.timestamp() + 20, 100)  # 同じ日の再AC → 数えない
    add_ac(self.db, "alice", 3, "abc100_b", t0.timestamp() + 30, 200)
    add_ac(self.db, "alice", 4, "abc100_c", t0.timestamp() - 10, 300)  # 昨日 (期間外)
    count = self.run_async(self.ns["count_period_ac"]("alice", 1, self.db))
    self.assertEqual(count, [2, 300, 2])
    count = self.run_async(self.ns["count_period_ac"]("alice", 1, self.db, end_unix=int(t0.timestamp()) + 25))
    self.assertEqual(count, [1, 100, 1])

  def test_reac_on_another_day_counts_in_total_not_new(self):
    t0 = today_start()
    add_user(self.db, "amy")
    add_ac(self.db, "amy", 1, "abc1_a", (t0 - _dt.timedelta(days=10)).timestamp(), 100)  # 期間前に解いた
    add_ac(self.db, "amy", 2, "abc1_a", (t0 - _dt.timedelta(days=2)).timestamp(), 100)   # 期間内に解き直し
    add_ac(self.db, "amy", 3, "abc1_a", t0.timestamp() + 5, 100)                         # 今日も解き直し
    add_ac(self.db, "amy", 4, "abc1_b", (t0 - _dt.timedelta(days=1)).timestamp(), 200)   # 期間内に初めて
    total, point, new = self.run_async(self.ns["count_period_ac"]("amy", 7, self.db))
    self.assertEqual((total, point, new), (3, 400, 1))

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
    with dbconn(self.db) as c:
      for table in ("users", "ac_submissions_cache", "update_bookmark"):
        self.assertEqual(c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

  def test_unregister_by_other_user_is_refused(self):
    add_user(self.db, "erin", uid=1)
    it = FakeInteraction(self.rec, user_id=999)
    self.run_async(self.ns["user_unregister"].callback(it, "erin"))
    with dbconn(self.db) as c:
      self.assertEqual(c.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)


class TestRegister(Base):
  def setUp(self):
    super().setUp()
    async def exists(name):
      return True
    self.ns["atcoder_user_exists"] = exists
    self.ns["initial_fetch_user_data"] = no_refresh
    self.ns["admin_id"] = "999"

  def users(self):
    with dbconn(self.db) as c:
      return c.execute("SELECT atcoder_name, discord_name, discord_id FROM users ORDER BY atcoder_name").fetchall()

  def test_member_can_register_only_one_account(self):
    it = FakeInteraction(self.rec, user_id=5)
    it.user.display_name = "表示名"
    self.run_async(self.ns["user_register"].callback(it, "first_acc", None))
    self.run_async(self.ns["user_register"].callback(it, "second_acc", "x"))
    self.assertEqual(self.users(), [("first_acc", "表示名", 5)])
    self.assertIn("1人1アカウント", self.rec.titles()[-1])

  def test_admin_can_register_many(self):
    it = FakeInteraction(self.rec, user_id=999)
    self.run_async(self.ns["user_register"].callback(it, "acc_one", "A"))
    self.run_async(self.ns["user_register"].callback(it, "acc_two", "B"))
    self.assertEqual([u[0] for u in self.users()], ["acc_one", "acc_two"])

  def test_member_can_reregister_after_unregister(self):
    it = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["user_register"].callback(it, "first_acc", "A"))
    self.run_async(self.ns["user_unregister"].callback(it, "first_acc"))
    self.run_async(self.ns["user_register"].callback(it, "second_acc", "A"))
    self.assertEqual([u[0] for u in self.users()], ["second_acc"])


class TestBulkRegister(Base):
  def test_admin_only_and_registers_group(self):
    self.ns["initial_fetch_user_data"] = no_refresh
    self.ns["admin_id"] = "999"
    self.ns["BULK_GROUPS"]["test"] = {"aaa": "A", "bbb": "B"}
    sent = []

    class Resp:
      async def send_message(self, content=None, ephemeral=False):
        sent.append(content)

      async def defer(self, **kw):
        pass
    import discord
    choice = discord.app_commands.Choice(name="t", value="test")
    member = FakeInteraction(self.rec, user_id=1)
    member.response = Resp()
    self.run_async(self.ns["bulk_register"].callback(member, choice))
    self.assertIn("管理者だけ", sent[0])
    admin = FakeInteraction(self.rec, user_id=999)
    self.run_async(self.ns["bulk_register"].callback(admin, choice))
    self.run_async(self.ns["bulk_register"].callback(admin, choice))  # 2回目は登録済みとして飛ばす
    with dbconn(self.db) as c:
      self.assertEqual(sorted(r[0] for r in c.execute("SELECT atcoder_name FROM users")), ["aaa", "bbb"])
    self.assertTrue(any("既に登録済み" in (t or "") for t in self.rec.titles()))

  def test_no_privileged_intents(self):
    intents = self.ns["intents"]
    self.assertFalse(intents.message_content or intents.members or intents.presences)


class TestVerification(Base):
  def setUp(self):
    super().setUp()
    import config
    self.config = config
    config.REQUIRE_ATCODER_VERIFICATION = True
    async def exists(name):
      return True
    self.ns["atcoder_user_exists"] = exists
    self.ns["initial_fetch_user_data"] = no_refresh
    self.ns["admin_id"] = "999"
    self.affiliation = ""
    async def contains(name, code):
      return code in self.affiliation
    self.ns["affiliation_contains"] = contains

  def tearDown(self):
    self.config.REQUIRE_ATCODER_VERIFICATION = False

  def registered(self):
    with dbconn(self.db) as c:
      return [r[0] for r in c.execute("SELECT atcoder_name FROM users")]

  def test_member_must_put_code_in_affiliation(self):
    it = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["user_register"].callback(it, "my_acc", "A"))
    self.assertEqual(self.registered(), [])
    code = self.ns["get_pending_verification"](5, self.db)[2]
    self.assertIn(code, self.rec.titles()[-1])
    self.run_async(self.ns["user_verify"].callback(it))
    self.assertIn("見つかりません", self.rec.titles()[-1])
    self.affiliation = f"Some Univ {code}"
    self.run_async(self.ns["user_verify"].callback(it))
    self.assertEqual(self.registered(), ["my_acc"])
    self.assertIsNone(self.ns["get_pending_verification"](5, self.db))

  def test_code_expires(self):
    import time as _time
    self.ns["create_pending_verification"](5, "my_acc", "A", self.db)
    self.assertIsNone(self.ns["get_pending_verification"](5, self.db, now=_time.time() + 3601))

  def test_admin_skips_verification(self):
    it = FakeInteraction(self.rec, user_id=999)
    self.run_async(self.ns["user_register"].callback(it, "someone", "S"))
    self.assertEqual(self.registered(), ["someone"])

  def test_affiliation_parser(self):
    from atcoder.verification import affiliation_of
    page = ('<tr><th class="no-break">Affiliation</th><td class="break-all"> AtCoder Inc. &amp; atcbot-1a2b3c4d</td></tr>'
            '<p>atcbot-ffffffff</p>')
    self.assertEqual(affiliation_of(page), "AtCoder Inc. & atcbot-1a2b3c4d")
    self.assertEqual(affiliation_of('<th>所属</th><td>大学</td>'), "大学")
    self.assertEqual(affiliation_of("<html></html>"), "")


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

  def test_many_users_post_top10_and_file(self):
    for i in range(14):
      add_user(self.db, f"user{i:02d}", f"U{i}")
    freeze_now(self.ns, self.monday + _dt.timedelta(minutes=15))
    self.run_async(self.ns["weekly_ranking_post"].coro())
    weekly = [e for _, e, _ in self.rec.sent if e is not None and "Diligence" in e.title]
    self.assertEqual(len(weekly), 1)
    self.assertEqual(len(weekly[0].fields), 11)  # 上位10人 + 「ほか N 人」
    self.assertIn("📄 全員の順位", [c for _, e, c in self.rec.sent if e is None])

  def test_failed_send_is_retried_without_advancing_week(self):
    original = self.ns["send_with_retry"]

    async def fast_retry(make_coro, attempts=3, delay=60):
      return await original(make_coro, attempts=attempts, delay=0)
    self.ns["send_with_retry"] = fast_retry
    channel = FakeChannel(self.rec, fail_times=3)  # 1回目の投稿は3回とも失敗する
    self.ns["client"].get_channel = lambda _id: channel
    freeze_now(self.ns, self.monday + _dt.timedelta(minutes=15))
    self.run_async(self.ns["weekly_ranking_post"].coro())
    self.assertIsNone(self.ns["get_weekly_last_posted"](self.db))  # 投稿済みにならない
    self.assertEqual(self.ns["get_weekly_cycle_state"](self.db), (1, 1))
    freeze_now(self.ns, self.monday + _dt.timedelta(hours=1, minutes=15))
    self.run_async(self.ns["catch_up_weekly_ranking_post"]())  # 1時間後のやり直し
    self.assertEqual(self.ns["get_weekly_cycle_state"](self.db), (1, 1))  # 週は進まない
    self.assertIsNotNone(self.ns["get_weekly_last_posted"](self.db))
    self.assertEqual(len([t for t in self.rec.titles() if t and "Diligence" in t]), 1)

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
    with dbconn(path) as c:
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


class TestBackgroundSync(Base):
  def setUp(self):
    super().setUp()
    import sys
    self.bs = sys.modules["atcoder.background_sync"]
    self.bs._pause_until.update({"submission": 0.0, "contest": 0.0})
    self.bs._user_backoff.clear()
    self.bs.fail_streak.update({"submission": 0, "contest": 0})
    self.fail_names = set()
    self.calls = []
    self.fail = set()
    db = self.db

    async def fake_subs(name, db_file):
      self.calls.append(("submission", name))
      if "submission" not in self.fail and name not in self.fail_names:
        with dbconn(db_file) as c:
          c.execute("INSERT OR IGNORE INTO update_bookmark (atcoder_name) VALUES (?)", (name,))
          c.execute("UPDATE update_bookmark SET submission_last_fetch = ? WHERE atcoder_name = ?", (time.time(), name))

    async def fake_contest(name, db_file, force=False):
      self.calls.append(("contest", name))
      if "contest" not in self.fail:
        with dbconn(db_file) as c:
          c.execute("INSERT OR IGNORE INTO update_bookmark (atcoder_name) VALUES (?)", (name,))
          c.execute("UPDATE update_bookmark SET contest_last_fetched = ? WHERE atcoder_name = ?", (time.time(), name))

    self._orig = (self.bs.fetch_and_cache_ac_submissions, self.bs.fetch_and_cache_contest_history)
    self.bs.fetch_and_cache_ac_submissions = fake_subs
    self.bs.fetch_and_cache_contest_history = fake_contest
    with dbconn(db) as c:
      for i, name in enumerate(["u1", "u2", "u3"]):
        c.execute("INSERT INTO users VALUES (?, ?, 1, 1)", (name, name))
      # u2 は提出が一番古い、u3 は一度も同期していない (bookmark なし)
      c.execute("INSERT INTO update_bookmark (atcoder_name, submission_last_fetch, contest_last_fetched) VALUES ('u1', ?, ?)", (time.time() - 400, time.time()))
      c.execute("INSERT INTO update_bookmark (atcoder_name, submission_last_fetch, contest_last_fetched) VALUES ('u2', ?, ?)", (time.time() - 1000, time.time()))

  def tearDown(self):
    self.bs.fetch_and_cache_ac_submissions, self.bs.fetch_and_cache_contest_history = self._orig

  def test_picks_most_stale_first_and_finishes(self):
    order = []
    for _ in range(5):
      picked = self.run_async(self.bs.sync_step(self.db))
      order.append((picked["submission"], picked["contest"]))
    self.assertEqual([o[0] for o in order], ["u3", "u2", "u1", None, None])
    self.assertEqual([o[1] for o in order], ["u3", None, None, None, None])

  def test_contest_resync_request_is_prioritized(self):
    self.run_async(self.bs.sync_step(self.db))  # u3 の初回同期
    self.ns["request_contest_resync"](["U1"], self.db)
    picked = self.run_async(self.bs.sync_step(self.db))
    self.assertEqual(picked["contest"], "u1")

  def test_one_failing_user_does_not_block_others(self):
    self.fail_names.add("u3")
    order = [self.run_async(self.bs.sync_step(self.db))["submission"] for _ in range(4)]
    self.assertEqual(order, ["u3", "u2", "u1", None])  # u3 は待機中なので飛ばされ、ほかの人は同期される
    self.assertEqual(self.bs.fail_streak["submission"], 0)

  def test_failures_across_users_pause_that_kind(self):
    self.fail.add("submission")
    for _ in range(3):
      self.run_async(self.bs.sync_step(self.db))  # u3, u2, u1 が続けて失敗
    picked = self.run_async(self.bs.sync_step(self.db))
    self.assertIsNone(picked["submission"])  # API 障害とみなして一時停止中
    self.assertEqual(self.bs.fail_streak["submission"], 3)

  def test_unregistered_during_sync_leaves_no_rows(self):
    async def subs_then_unregister(name, db_file):
      with dbconn(db_file) as c:
        c.execute("DELETE FROM users WHERE atcoder_name = ?", (name,))
        c.execute("INSERT OR REPLACE INTO update_bookmark (atcoder_name, submission_last_fetch) VALUES (?, ?)", (name, time.time()))
        c.execute("INSERT INTO ac_submissions_cache VALUES (?, 1, 'abc1_a', 1, 100)", (name,))
    self.bs.fetch_and_cache_ac_submissions = subs_then_unregister
    self.run_async(self.bs.sync_step(self.db))
    with dbconn(self.db) as c:
      self.assertEqual(c.execute("SELECT COUNT(*) FROM ac_submissions_cache WHERE atcoder_name='u3'").fetchone()[0], 0)
      self.assertEqual(c.execute("SELECT COUNT(*) FROM update_bookmark WHERE atcoder_name='u3'").fetchone()[0], 0)
    self.assertEqual(self.bs.fail_streak["submission"], 0)

  def test_footer_reports_age(self):
    self.assertIn("同期中", self.ns["sync_footer"]())  # u3 は未同期
    for _ in range(3):
      self.run_async(self.bs.sync_step(self.db))
    self.assertIn("最大0分前", self.ns["sync_footer"]())


class TestPaging(Base):
  def test_pages_of_ten_with_page_numbers(self):
    fields = [(f"{i + 1}位", f"v{i}") for i in range(25)]
    pages = self.ns["build_pages"]("T", 0, None, fields, footer="最新")
    self.assertEqual([len(p.fields) for p in pages], [10, 10, 5])
    self.assertEqual(pages[0].footer.text, "1/3 ページ　最新")
    self.assertTrue(all(p.title == "T" for p in pages))
    self.assertEqual(len(self.ns["build_pages"]("T", 0, None, fields[:3])), 1)

  def test_buttons_move_between_pages(self):
    pages = self.ns["build_pages"]("T", 0, None, [(str(i), "v") for i in range(25)])
    shown = []

    class Resp:
      async def edit_message(self, embed=None, view=None):
        shown.append(embed)

    async def run():
      view = self.ns["PageView"](pages)
      self.assertTrue(view.prev_button.disabled)
      inter = type("I", (), {"response": Resp()})()
      await view.next_button.callback(inter)
      await view.next_button.callback(inter)
      self.assertTrue(view.next_button.disabled)
      await view.prev_button.callback(inter)
      return view.index
    self.assertEqual(self.run_async(run()), 1)
    self.assertEqual([e.footer.text for e in shown], ["2/3 ページ", "3/3 ページ", "2/3 ページ"])

  def test_timeout_disables_buttons_with_bot_token(self):
    pages = self.ns["build_pages"]("T", 0, None, [(str(i), "v") for i in range(25)])
    edited = []

    class Partial:
      async def edit(self, view=None):
        edited.append([item.disabled for item in view.children])

    class Channel:
      def get_partial_message(self, message_id):
        return Partial()

    async def run():
      view = self.ns["PageView"](pages)
      view.message = type("M", (), {"id": 1, "channel": Channel()})()
      await view.on_timeout()
    self.run_async(run())
    self.assertEqual(edited, [[True, True]])

  def test_top_fields_and_text_file(self):
    fields = [(f"{i + 1}位 : u{i}", f"Rate: **+{i}**") for i in range(15)]
    top = self.ns["top_fields"](fields)
    self.assertEqual(len(top), 11)
    self.assertIn("ほか 5 人", top[-1][0])
    f = self.ns["ranking_text_file"]("タイトル", fields, "x.txt")
    text = f.fp.read().decode("utf-8")
    self.assertIn("15位 : u14", text)
    self.assertNotIn("**", text)

  def test_abc_auto_fields_count_people(self):
    def rec(i):
      return {"atcoder_name": f"u{i}", "discord_name": "d", "rank": i, "performance": 1000, "old_rating": 1000, "new_rating": 1000, "rate_change": 0, "ac_count": 3}
    rated = [rec(i) for i in range(12)]
    unrated = [rec(100 + i) for i in range(40)]
    fields = self.ns["abc_auto_fields"](rated, unrated)
    self.assertEqual(len(fields), 11)
    self.assertIn("ほか 42 人", fields[-1][0])
    self.assertIn("unrated 参加の 40 人", fields[-1][1])
    few = self.ns["abc_auto_fields"](rated[:3], unrated[:2])
    self.assertTrue(any("Unrated" in name for name, _ in few))

  def test_my_rank(self):
    add_user(self.db, "me_user", uid=42)
    ranking = [{"atcoder_name": "other", "place": 1}, {"atcoder_name": "Me_User", "place": 2}]
    it = FakeInteraction(self.rec, user_id=42)
    self.assertIn("2位", self.ns["my_rank_text"](it, ranking, 2))
    self.assertIsNone(self.ns["my_rank_text"](FakeInteraction(self.rec, user_id=7), ranking, 2))


class TestMonitoring(Base):
  def setUp(self):
    super().setUp()
    import alerts
    self.alerts = alerts
    alerts._last_sent.clear()
    alerts.recent_errors.clear()
    self.dms = []
    dms = self.dms

    class Admin:
      async def send(self, text):
        dms.append(text)

    class Client:
      def get_user(self, _id):
        return Admin()
    alerts.setup(Client(), "999")
    import sys
    self.bs = sys.modules["atcoder.background_sync"]
    self.bs.fail_streak.update({"submission": 0, "contest": 0})
    self.ns["_sync_alerted"].clear()

  def tearDown(self):
    self.alerts.setup(None, None)
    self.bs.fail_streak.update({"submission": 0, "contest": 0})

  def test_notify_cooldown(self):
    self.assertTrue(self.run_async(self.alerts.notify_admin("k", "one")))
    self.assertFalse(self.run_async(self.alerts.notify_admin("k", "two")))
    self.assertTrue(self.run_async(self.alerts.notify_admin("other", "three")))
    self.assertEqual(len(self.dms), 2)

  def test_command_error_is_reported(self):
    def boom(_db):
      raise RuntimeError("db is broken")
    self.ns["get_user_dict"] = boom
    it = FakeInteraction(self.rec)
    self.run_async(self.ns["everyone_state"].callback(it))
    self.assertIn("管理者に自動で通知", self.rec.titles()[-1])
    self.assertIn("/ranking total", self.dms[0])
    self.assertIn("db is broken", self.dms[0])
    self.assertEqual(len(self.alerts.recent_errors), 1)

  def test_sync_alert_and_recovery(self):
    self.bs.fail_streak["submission"] = 10
    self.run_async(self.ns["check_sync_alerts"]())
    self.run_async(self.ns["check_sync_alerts"]())  # 2回目は送らない
    self.bs.fail_streak["submission"] = 0
    self.run_async(self.ns["check_sync_alerts"]())
    self.assertEqual(len(self.dms), 2)
    self.assertIn("失敗", self.dms[0])
    self.assertIn("復旧", self.dms[1])

  def test_bot_status_is_admin_only(self):
    sent = []

    class Resp:
      async def send_message(self, content=None, embed=None, ephemeral=False):
        sent.append((content, embed, ephemeral))
    self.ns["admin_id"] = "999"
    self.ns["bot_health"] = lambda: (True, {"discord_connected": True, "sync_fail_streak": {"submission": 0, "contest": 0}, "oldest_submission_sync_age_sec": 120, "uptime_sec": 3600})
    self.ns["client"].latency  # 例外にならないこと
    for uid in (1, 999):
      it = FakeInteraction(self.rec, user_id=uid)
      it.response = Resp()
      self.run_async(self.ns["bot_status"].callback(it))
    self.assertIn("管理者だけ", sent[0][0])
    self.assertTrue(sent[1][2])  # 本人にだけ見える
    self.assertIn("提出データの古さ (最大): 2分", sent[1][1].description)

  def test_health_endpoint(self):
    import server
    server.health_provider = lambda: (False, {"discord_connected": False})
    resp = server.health()
    self.assertEqual(resp.status_code, 503)
    server.health_provider = lambda: (True, {"discord_connected": True})
    self.assertEqual(server.health().status_code, 200)
    server.health_provider = None


class TestGraphThread(Base):
  def test_event_loop_keeps_running_while_drawing(self):
    data = {f"user{i}": [(x, 1000 + x) for x in range(200)] for i in range(10)}

    async def run():
      ticks = 0
      done = False

      async def ticker():
        nonlocal ticks
        while not done:
          ticks += 1
          await asyncio.sleep(0.01)
      t = asyncio.create_task(ticker())
      bufs = await asyncio.gather(
        self.ns["render_graph"](self.ns["create_progress_graph"], data),
        self.ns["render_graph"](self.ns["create_progress_graph"], data, x_label="点数"),
      )
      done = True
      await t
      return ticks, bufs
    ticks, bufs = self.run_async(run())
    self.assertTrue(all(b is not None and b.getbuffer().nbytes > 0 for b in bufs))
    self.assertGreater(ticks, 3)  # 描画中もイベントループが回っている


class TestEngagement(Base):
  def setUp(self):
    super().setUp()
    self.models = {
      "abc1_a": {"difficulty": 100}, "abc1_b": {"difficulty": 800}, "abc1_c": {"difficulty": 1000},
      "abc1_d": {"difficulty": 1200}, "abc1_e": {"difficulty": 1000, "is_experimental": True},
    }
    self.problems = {k: {"id": k, "contest_id": "abc1", "title": f"T {k}"} for k in self.models}
    async def data():
      return self.models, self.problems
    self.ns["get_problem_data"] = data
    self.ns["refresh_users_data"] = no_refresh
    self.dms = []
    async def dm(discord_id, text):
      self.dms.append((discord_id, text))
      return True
    self.ns["send_dm"] = dm
    self.channel = FakeChannel(self.rec)
    self.ns["client"].get_channel = lambda _id: self.channel
    self.ns["ranking_channel_id"] = 123
    add_user(self.db, "alice", "A", uid=5)
    add_user(self.db, "bob", "B", uid=6)

  def test_colors_and_score(self):
    from atcoder.problem_data import clip_difficulty, problem_score
    self.assertEqual(self.ns["color_name"](399), "灰")
    self.assertEqual(self.ns["color_name"](2399), "黄")
    self.assertEqual(self.ns["color_name"](2800), "赤")
    self.assertEqual(self.ns["get_rate_heart"](2400), "🧡")
    self.assertGreater(clip_difficulty(-800), 0)
    self.assertEqual(problem_score("abc1_b", self.models), 40)
    self.assertEqual(problem_score("unknown", self.models), 10)

  def test_problem_links_prefer_original_contest(self):
    from atcoder.problem_data import index_problems, problem_link
    rows = [{"id": "abc229_d", "contest_id": "abc229", "title": "D. X"}, {"id": "abc229_d", "contest_id": "adt_all_1", "title": "G. X"}]
    for ordered in (rows, rows[::-1]):
      self.assertIn("/contests/abc229/tasks/abc229_d", problem_link("abc229_d", index_problems(ordered)))

  def test_recommendations_skip_solved_and_experimental(self):
    picks = self.ns["pick_recommendations"](1000, {"abc1_d"}, self.models, self.problems)
    self.assertEqual([(p[0], p[1]) for p in picks], [("易しめ", "abc1_b"), ("ちょうどいい", "abc1_c")])

  def test_recommend_command(self):
    add_contest(self.db, "alice", "abc0", today_start() - _dt.timedelta(days=3), 900, 1000)
    it = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["recommend"].callback(it))
    self.assertIn("alice", self.rec.sent[-1][1].title)

  def test_score_counts_only_first_ac(self):
    t0 = today_start()
    add_ac(self.db, "alice", 1, "abc1_b", (t0 - _dt.timedelta(days=30)).timestamp())  # 期間前に解いた
    add_ac(self.db, "alice", 2, "abc1_b", t0.timestamp() + 1)                         # 解き直し
    add_ac(self.db, "alice", 3, "abc1_d", t0.timestamp() + 2)
    self.assertEqual(self.ns["get_period_score"]("alice", 7, self.db, self.models), 80)

  def test_score_ranking_and_color_filter(self):
    add_contest(self.db, "alice", "abc0", today_start() - _dt.timedelta(days=3), 900, 1000)
    add_contest(self.db, "bob", "abc0", today_start() - _dt.timedelta(days=3), 1200, 1300)
    add_ac(self.db, "alice", 1, "abc1_d", today_start().timestamp() + 1)
    import discord
    Choice = discord.app_commands.Choice
    it = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["diligence_score"].callback(it, Choice(name="1週間", value=7), Choice(name="水色", value="水")))
    embed = self.rec.sent[-1][1]
    self.assertEqual([f.name for f in embed.fields], ["1位 : bob(B)"])

  def test_versus(self):
    add_ac(self.db, "bob", 1, "abc1_d", today_start().timestamp() + 1)
    it = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["versus"].callback(it, "BOB"))
    text = " ".join(f.name + f.value for f in self.rec.sent[-1][1].fields)
    self.assertIn("bob だけが解いた問題 (1問", text)
    self.assertIn("/contests/abc1/tasks/abc1_d", text)

  def test_rating_progress(self):
    add_contest(self.db, "alice", "abc0", today_start() - _dt.timedelta(days=9), 900, 1000)
    add_contest(self.db, "alice", "abc2", today_start() - _dt.timedelta(days=3), 1000, 1157)
    text = self.ns["rating_progress_text"]("alice", self.db)
    self.assertIn("水色まであと **43**", text)
    self.assertIn("1000 → 1157", text)
    self.assertIsNone(self.ns["rating_progress_text"]("bob", self.db))

  def test_parse_and_remind_once(self):
    from atcoder.contest_reminder import parse_upcoming_abc
    page = ('<div id="contest-table-upcoming"><table><tbody><tr><td><time class="x">2026-11-14 21:00:00+0900</time></td>'
            '<td><a href="/contests/abc484">AtCoder Beginner Contest 484</a></td></tr>'
            '<tr><td><time>2026-11-08 21:00:00+0900</time></td><td><a href="/contests/agc079">AGC</a></td></tr></tbody></table></div>')
    parsed = parse_upcoming_abc(page)
    self.assertEqual([c["id"] for c in parsed], ["abc484"])
    upcoming = [{"id": "abc484", "title": "ABC 484", "start": int(time.time()) + 600}]
    async def get():
      return upcoming
    self.ns["get_upcoming_abc"] = get
    self.run_async(self.ns["abc_reminder_task"].coro())
    self.run_async(self.ns["abc_reminder_task"].coro())
    self.assertEqual(len(self.rec.sent), 1)
    self.assertIn("ABC 484", self.rec.sent[0][2])
    upcoming[0].update(id="abc485", start=int(time.time()) + 3600)
    self.run_async(self.ns["abc_reminder_task"].coro())
    self.assertEqual(len(self.rec.sent), 1)  # 30分より前は送らない

  def test_remind_30_and_10_minutes_before(self):
    from atcoder.contest_reminder import due_reminders, mark_reminded
    start = 1_000_000
    contests = [{"id": "abc500", "title": "ABC 500", "start": start}]
    def due(minutes_left):
      found = due_reminders(contests, self.db, now=start - minutes_left * 60)
      for contest, minutes in found:
        mark_reminded(contest["id"], minutes, self.db)
      return [m for _c, m in found]
    self.assertEqual(due(40), [])
    self.assertEqual(due(29), [30])
    self.assertEqual(due(20), [])   # 30分前の分は送信済み
    self.assertEqual(due(9), [10])
    self.assertEqual(due(5), [])    # 10分前の分も送信済み
    # 開始8分前に起動した場合は、10分前の分だけ送る (30分前の分をまとめて送らない)
    contests[0]["id"] = "abc501"
    self.assertEqual(due(8), [10])
    self.assertEqual(due(7), [])

  def test_cumulative_series_matches_period_count(self):
    t0 = today_start().timestamp()
    add_ac(self.db, "alice", 1, "abc1_a", t0 - 10 * 86400)   # 期間より前に解いた
    add_ac(self.db, "alice", 2, "abc1_a", t0 - 2 * 86400)    # 解き直し (総合ACだけ数える)
    add_ac(self.db, "alice", 3, "abc1_b", t0 - 2 * 86400 + 5)
    add_ac(self.db, "alice", 4, "abc1_b", t0 - 2 * 86400 + 9)  # 同じ日の再AC は数えない
    add_ac(self.db, "alice", 5, "abc1_c", t0 + 60)
    get = self.ns["get_cumulative_ac_series"]
    total, new = get("alice", 7, self.db, "total"), get("alice", 7, self.db, "new")
    counted = self.run_async(self.ns["count_period_ac"]("alice", 7, self.db))
    self.assertEqual([n for _t, n in total], [1, 2, 3])
    self.assertEqual(total[-1][1], counted[0])
    self.assertEqual(new[-1][1], counted[2])
    self.assertEqual([t for t, _n in total], sorted(t for t, _n in total))
    png = self.ns["create_cumulative_ac_graph"]({"alice": total, "bob": []}, 7, "test")
    self.assertTrue(png.getvalue().startswith(b"\x89PNG"))
    self.assertIsNone(self.ns["create_cumulative_ac_graph"]({"bob": []}, 7, "test"))

  def test_cumulative_graph_command(self):
    import discord
    t0 = today_start().timestamp()
    add_ac(self.db, "alice", 1, "abc1_a", t0 + 60)
    add_ac(self.db, "bob", 2, "abc1_a", t0 + 60)
    add_ac(self.db, "bob", 3, "abc1_b", t0 + 120)
    week = discord.app_commands.Choice(name="1週間", value=7)
    it = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["cumulative_graph"].callback(it, week, None, None))
    embed = self.rec.sent[-1][1]
    self.assertIn("累積総合AC", embed.title)
    self.assertIn("bob", embed.fields[0].name)        # 多い順
    self.assertIn("1位", embed.fields[0].name)
    self.assertIn("alice", embed.description)          # 実行した本人の順位
    it2 = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["cumulative_graph"].callback(it2, week, None, "nobody"))
    self.assertIn("登録されていません", self.rec.sent[-1][2])

  def test_commands_are_grouped_and_help_lists_them(self):
    tree = self.ns["tree"]
    top = {c.name for c in tree.get_commands()}
    self.assertEqual(top, {"user", "ranking", "syozin", "notify", "admin", "help"})
    for group in tree.get_commands():
      if hasattr(group, "commands"):
        self.assertLessEqual(len(group.commands), 25)  # Discord の上限
    embed = self.ns["build_help_embed"]()
    text = "".join(f.value for f in embed.fields)
    for name in ("/user register", "/ranking ac", "/syozin graph", "/notify contest", "/admin status"):
      self.assertIn(name, text)

  def test_contest_dm_command_and_delivery(self):
    import discord
    from atcoder.contest_dm import due_contest_dms, mark_contest_dm
    choice = lambda m: discord.app_commands.Choice(name=f"{m}分前", value=m)
    it = FakeInteraction(self.rec, user_id=5)
    self.run_async(self.ns["contest_dm"].callback(it, choice(15), True))
    self.run_async(self.ns["contest_dm"].callback(it, choice(60), True))
    self.assertEqual(len(self.dms), 2)  # 設定のたびに確認の DM
    self.assertEqual(self.ns["get_contest_dm"](5, self.db), [60, 15])
    # 登録していない人は使えない
    stranger = FakeInteraction(self.rec, user_id=99)
    self.run_async(self.ns["contest_dm"].callback(stranger, choice(15), True))
    self.assertEqual(self.ns["get_contest_dm"](99, self.db), [])

    start = 2_000_000
    contests = [{"id": "abc600", "title": "ABC 600", "start": start}]
    def due(minutes_left):
      found = due_contest_dms(contests, self.db, now=start - minutes_left * 60)
      for discord_id, _name, contest, minutes in found:
        mark_contest_dm(discord_id, contest["id"], minutes, self.db)
      return [(d, n, m) for d, n, _c, m in found]
    self.assertEqual(due(90), [])
    self.assertEqual(due(59), [(5, "alice", 60)])
    self.assertEqual(due(30), [])
    self.assertEqual(due(14), [(5, "alice", 15)])
    self.assertEqual(due(3), [])
    # オフにすると届かない
    self.run_async(self.ns["contest_dm"].callback(it, choice(15), False))
    contests[0]["id"] = "abc601"
    self.assertEqual(due(14), [(5, "alice", 60)])  # 60分前の設定だけが残っている (開始直前なら一度だけ)
    self.assertEqual(due(10), [])

  def test_contest_dm_sent_by_reminder_task(self):
    self.ns["set_contest_dm"](6, 10, True, self.db)
    upcoming = [{"id": "abc700", "title": "ABC 700", "start": int(time.time()) + 300}]
    async def get():
      return upcoming
    self.ns["get_upcoming_abc"] = get
    self.run_async(self.ns["abc_reminder_task"].coro())
    self.run_async(self.ns["abc_reminder_task"].coro())
    self.assertEqual([d[0] for d in self.dms], [6])
    self.assertIn("あと10分で **ABC 700**", self.dms[0][1])
    self.assertEqual(len(self.rec.sent), 1)  # チャンネルの10分前リマインドも1回

  def test_achievements_backfill_silently_then_post_once(self):
    add_ac(self.db, "alice", 1, "abc1_b", today_start().timestamp() - 5)
    self.run_async(self.ns["achievements_task"].coro())
    self.assertEqual(self.rec.sent, [])  # 過去の分は投稿しない
    add_ac(self.db, "alice", 2, "abc1_d", today_start().timestamp() - 4)
    self.run_async(self.ns["achievements_task"].coro())
    self.run_async(self.ns["achievements_task"].coro())
    self.assertEqual(len(self.rec.sent), 1)
    self.assertIn("初の水diff", self.rec.sent[0][1].fields[0].value)

  def test_achievement_is_retried_when_post_fails(self):
    self.run_async(self.ns["achievements_task"].coro())
    add_ac(self.db, "alice", 1, "abc1_d", today_start().timestamp() - 4)
    self.channel.fail_times = 1
    self.run_async(self.ns["achievements_task"].coro())
    self.run_async(self.ns["achievements_task"].coro())
    self.assertEqual(len(self.rec.sent), 1)

  def test_streak_reminder(self):
    it = FakeInteraction(self.rec, user_id=5)
    import discord
    kind = discord.app_commands.Choice(name="連続", value="streak")
    self.run_async(self.ns["notify"].callback(it, kind, True))
    t0 = today_start()
    add_ac(self.db, "alice", 1, "abc1_a", (t0 - _dt.timedelta(days=1)).timestamp())
    self.run_async(self.ns["streak_reminder_task"].coro())
    self.run_async(self.ns["streak_reminder_task"].coro())  # 同じ日は1回だけ
    self.assertEqual(len(self.dms), 1)
    self.assertEqual(self.dms[0][0], 5)
    self.assertIn("連続1日", self.dms[0][1])

  def test_streak_reminder_survives_one_user_failure(self):
    t0 = today_start()
    for i, (uid, name) in enumerate(((5, "alice"), (6, "bob"))):
      self.ns["set_notification"](uid, name, "streak", True, self.db)
      add_ac(self.db, name, i + 1, "abc1_a", (t0 - _dt.timedelta(days=1)).timestamp())
    async def refresh(names, _db):
      if names == ["alice"]:
        raise RuntimeError("boom")
    self.ns["refresh_users_data"] = refresh
    async def notify(*_args, **_kwargs):
      return None
    self.addCleanup(setattr, self.ns["alerts"], "notify_admin", self.ns["alerts"].notify_admin)
    self.ns["alerts"].notify_admin = notify
    self.run_async(self.ns["streak_reminder_task"].coro())
    self.assertEqual([d[0] for d in self.dms], [6])

  def test_relink_drops_previous_owner_notifications(self):
    self.ns["set_notification"](5, "alice", "streak", True, self.db)
    self.assertTrue(self.ns["link_discord_account"]("alice", 5, self.db))
    self.assertEqual(self.ns["get_notification_targets"]("streak", self.db), [(5, "alice")])
    self.assertTrue(self.ns["link_discord_account"]("ALICE", 7, self.db))
    self.assertEqual(self.ns["get_notification_targets"]("streak", self.db), [])

  def test_parse_unescapes_title(self):
    from atcoder.contest_reminder import parse_upcoming_abc
    page = ('<div id="contest-table-upcoming"><table><tr><td><time>2026-11-14 21:00:00+0900</time></td>'
            '<td><a href="/contests/abc484">A &amp; B Contest</a></td></tr></table></div>')
    self.assertEqual(parse_upcoming_abc(page)[0]["title"], "A & B Contest")

  def test_no_streak_reminder_after_ac_today(self):
    self.ns["set_notification"](5, "alice", "streak", True, self.db)
    t0 = today_start()
    add_ac(self.db, "alice", 1, "abc1_a", (t0 - _dt.timedelta(days=1)).timestamp())
    add_ac(self.db, "alice", 2, "abc1_b", t0.timestamp() + 1)
    self.run_async(self.ns["streak_reminder_task"].coro())
    self.assertEqual(self.dms, [])

  def test_weekly_review(self):
    monday = today_start() - _dt.timedelta(days=today_start().weekday())
    freeze_now(self.ns, monday + _dt.timedelta(hours=9))
    self.ns["set_notification"](5, "alice", "weekly_review", True, self.db)
    self.ns["set_prev_contest"](2, self.db)
    add_ac(self.db, "alice", 1, "abc1_a", (monday - _dt.timedelta(days=1)).timestamp())
    if today_start().weekday() == 0:
      self.run_async(self.ns["weekly_review_task"].coro())
      self.run_async(self.ns["weekly_review_task"].coro())
      self.assertEqual(len(self.dms), 1)
    text = self.run_async(self.ns["build_weekly_review"]("alice", int(monday.timestamp()), self.models))
    self.assertIn("alice", text)

  def test_weak_slot(self):
    add_ac(self.db, "alice", 1, "abc001_a", 1)
    add_ac(self.db, "alice", 2, "abc002_a", 1)
    self.assertEqual(self.ns["next_wall_slot"]("alice", 2, self.db), ("B", 0.0))

  def test_user_link_enables_notify(self):
    self.ns["admin_id"] = "999"
    import types
    admin = FakeInteraction(self.rec, user_id=999)
    self.run_async(self.ns["user_link"].callback(admin, "ALICE", types.SimpleNamespace(id=77)))
    self.assertEqual(self.ns["get_registered_by_discord_id"](77, self.db), "alice")

  def test_unregister_removes_preferences(self):
    self.ns["set_notification"](5, "alice", "streak", True, self.db)
    self.ns["record_achievements"]([("alice", "ac:100")], self.db)
    self.ns["delete_user"]("alice", self.db)
    self.assertEqual(self.ns["get_notification_targets"]("streak", self.db), [])
    with dbconn(self.db) as c:
      self.assertEqual(c.execute("SELECT COUNT(*) FROM achievements").fetchone()[0], 0)


class TestLogger(unittest.TestCase):
  def test_chunks_fit_discord_limit(self):
    import discord_logger
    chunks = list(discord_logger._chunks(["z" * 300 for _ in range(50)]))
    self.assertTrue(all(len(c) <= 2000 for c in chunks))
    self.assertEqual(sum(c.count("z" * 300) for c in chunks), 50)


if __name__ == "__main__":
  unittest.main()

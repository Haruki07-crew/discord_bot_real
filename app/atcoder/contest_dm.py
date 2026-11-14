"""ABC 開始前の個人 DM (/contest_dm)。何分前に受け取るかを人ごとに保存し、送信済みを記録する。
コンテストの予定は contest_reminder.get_upcoming_abc をそのまま使うので、人数が増えても外部APIへのアクセスは増えない。"""
import time

from atcoder import db

MINUTE_CHOICES = (5, 10, 15, 30, 60, 120)


def init_contest_dm_tables(db_file):
  with db.connect(db_file) as conn:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS contest_dm_prefs (
        discord_id INTEGER,
        minutes    INTEGER,
        PRIMARY KEY (discord_id, minutes)
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS contest_dm_sent (
        discord_id INTEGER,
        contest_id TEXT,
        minutes    INTEGER,
        sent_at    REAL,
        PRIMARY KEY (discord_id, contest_id, minutes)
      )
    """)


def set_contest_dm(discord_id, minutes, enabled, db_file):
  with db.connect(db_file) as conn:
    if enabled:
      conn.execute("INSERT OR IGNORE INTO contest_dm_prefs VALUES (?, ?)", (discord_id, minutes))
    else:
      conn.execute("DELETE FROM contest_dm_prefs WHERE discord_id = ? AND minutes = ?", (discord_id, minutes))


def get_contest_dm(discord_id, db_file):
  """その人が設定している「何分前」の一覧 (大きい順)。"""
  with db.connect(db_file) as conn:
    rows = conn.execute(
      "SELECT minutes FROM contest_dm_prefs WHERE discord_id = ? ORDER BY minutes DESC", (discord_id,)
    ).fetchall()
  return [r[0] for r in rows]


def due_contest_dms(contests, db_file, now=None):
  """いま送るべきで、まだ送っていない DM を [(discord_id, atcoder_name, コンテスト, 何分前), ...] で返す。
  自分で登録した (または /user_link で紐づけられた) 人だけが対象。
  1人につき、残り時間に合う一番短い区切りだけを返す (60分前に設定した直後が開始20分前なら、30分前の分だけ送る)。"""
  now = time.time() if now is None else now
  upcoming = [c for c in contests if 0 < c["start"] - now <= max(MINUTE_CHOICES) * 60]
  if not upcoming:
    return []
  with db.connect(db_file) as conn:
    prefs = conn.execute("""
      SELECT p.discord_id, u.atcoder_name, p.minutes FROM contest_dm_prefs p
      JOIN users u ON u.discord_id = p.discord_id AND u.register_id = p.discord_id
      GROUP BY p.discord_id, p.minutes
    """).fetchall()
    windows = {}
    for discord_id, atcoder_name, minutes in prefs:
      windows.setdefault((discord_id, atcoder_name), []).append(minutes)
    due = []
    for contest in upcoming:
      left = contest["start"] - now
      for (discord_id, atcoder_name), minutes_list in windows.items():
        fitting = [m for m in minutes_list if left <= m * 60]
        if not fitting:
          continue
        minutes = min(fitting)
        sent = conn.execute(
          "SELECT 1 FROM contest_dm_sent WHERE discord_id = ? AND contest_id = ? AND minutes = ?",
          (discord_id, contest["id"], minutes),
        ).fetchone()
        if sent is None:
          due.append((discord_id, atcoder_name, contest, minutes))
  return due


def mark_contest_dm(discord_id, contest_id, minutes, db_file):
  with db.connect(db_file) as conn:
    conn.execute(
      "INSERT OR IGNORE INTO contest_dm_sent VALUES (?, ?, ?, ?)", (discord_id, contest_id, minutes, time.time())
    )
    # 古い送信記録は不要なので消す (人数 × コンテスト数で増え続けないように)
    conn.execute("DELETE FROM contest_dm_sent WHERE sent_at < ?", (time.time() - 30 * 24 * 60 * 60,))

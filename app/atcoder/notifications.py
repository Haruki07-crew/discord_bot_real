"""DM 通知の希望 (連続ACのリマインド・週次ふり返り) の保存と読み出し。"""
from atcoder import db

KINDS = ("streak", "weekly_review")


def init_engagement_tables(db_file):
  with db.connect(db_file) as conn:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS notification_prefs (
        discord_id   INTEGER,
        atcoder_name TEXT,
        kind         TEXT,
        PRIMARY KEY (discord_id, kind)
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS achievements (
        atcoder_name TEXT,
        badge        TEXT,
        achieved_at  REAL,
        PRIMARY KEY (atcoder_name, badge)
      )
    """)


def set_notification(discord_id, atcoder_name, kind, enabled, db_file):
  with db.connect(db_file) as conn:
    if enabled:
      conn.execute("INSERT OR REPLACE INTO notification_prefs VALUES (?, ?, ?)", (discord_id, atcoder_name, kind))
    else:
      conn.execute("DELETE FROM notification_prefs WHERE discord_id = ? AND kind = ?", (discord_id, kind))


def get_notification_targets(kind, db_file):
  """登録中のユーザーのうち、その通知を希望している [(discord_id, atcoder_name), ...]。"""
  with db.connect(db_file) as conn:
    return conn.execute("""
      SELECT n.discord_id, u.atcoder_name FROM notification_prefs n
      JOIN users u ON u.atcoder_name = n.atcoder_name COLLATE NOCASE
      WHERE n.kind = ?
    """, (kind,)).fetchall()


def link_discord_account(atcoder_name, discord_id, db_file):
  """登録済みの AtCoder アカウントを Discord ユーザーに紐づける。戻り値: 紐づけられたか"""
  with db.connect(db_file) as conn:
    cur = conn.execute(
      "UPDATE users SET discord_id = ?, register_id = ? WHERE atcoder_name = ? COLLATE NOCASE",
      (discord_id, discord_id, atcoder_name),
    )
    # 別の人が受け取っていた通知は引き継がない (前の持ち主に DM が届き続けないように)
    conn.execute(
      "DELETE FROM notification_prefs WHERE atcoder_name = ? COLLATE NOCASE AND discord_id != ?",
      (atcoder_name, discord_id),
    )
    return cur.rowcount > 0


def get_state(key, db_file):
  with db.connect(db_file) as conn:
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
  return row[0] if row else None


def set_state(key, value, db_file):
  with db.connect(db_file) as conn:
    conn.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)", (key, value))

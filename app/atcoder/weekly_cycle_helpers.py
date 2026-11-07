import sqlite3


def get_weekly_cycle_state(db_file):
  """現在のcycle_idとcurrent_weekを返す。未初期化なら(1, 0)で初期化する。"""
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT cycle_id, current_week FROM weekly_cycle WHERE id = 1")
    row = cursor.fetchone()
    if row is None:
      cursor.execute("INSERT INTO weekly_cycle (id, cycle_id, current_week) VALUES (1, 1, 0)")
      conn.commit()
      return (1, 0)
    return (row[0], row[1])


def advance_weekly_cycle(db_file):
  """週を1つ進める。12週に達したらcycle_idを増やしてリセットする。
  進めた後の(cycle_id, current_week)を返す。"""
  cycle_id, current_week = get_weekly_cycle_state(db_file)
  current_week += 1
  if current_week > 12:
    cycle_id += 1
    current_week = 1
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute(
      "UPDATE weekly_cycle SET cycle_id = ?, current_week = ? WHERE id = 1",
      (cycle_id, current_week)
    )
    conn.commit()
  return (cycle_id, current_week)


def save_weekly_snapshot(cycle_id, week_number, user_data_list, db_file):
  """週次データを保存する。
  user_data_list: [{"atcoder_name": str, "ac_count": int, "ac_point": int, "rate_change": int}, ...]
  """
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    for d in user_data_list:
      cursor.execute("""
        INSERT OR REPLACE INTO weekly_snapshots
        (cycle_id, week_number, atcoder_name, ac_count, ac_point, rate_change)
        VALUES (?, ?, ?, ?, ?, ?)
      """, (cycle_id, week_number, d["atcoder_name"], d["ac_count"], d["ac_point"], d["rate_change"]))
    conn.commit()


def get_weekly_snapshots(cycle_id, db_file):
  """指定サイクルの全スナップショットを取得する。
  戻り値: {atcoder_name: [(week, ac_count, ac_point, rate_change), ...], ...}
  週番号順にソート済み。"""
  with sqlite3.connect(db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("""
      SELECT week_number, atcoder_name, ac_count, ac_point, rate_change
      FROM weekly_snapshots
      WHERE cycle_id = ?
      ORDER BY week_number ASC
    """, (cycle_id,))
    rows = cursor.fetchall()

  result = {}
  for week, name, ac, point, rc in rows:
    if name not in result:
      result[name] = []
    result[name].append((week, ac, point, rc))
  return result


def get_weekly_last_posted(db_file):
  """最後に週次投稿を行った日付 (JST, 'YYYY-MM-DD') を返す。未投稿なら None。"""
  with sqlite3.connect(db_file) as conn:
    row = conn.execute("SELECT value FROM bot_state WHERE key = 'weekly_last_posted'").fetchone()
  return row[0] if row else None


def set_weekly_last_posted(date_str, db_file):
  """週次投稿を行った日付を記録する (同じ日に二重に週を進めないため)。"""
  with sqlite3.connect(db_file) as conn:
    conn.execute(
      "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('weekly_last_posted', ?)",
      (date_str,)
    )
    conn.commit()

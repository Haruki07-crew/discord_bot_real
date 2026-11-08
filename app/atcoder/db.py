import sqlite3
from contextlib import contextmanager


@contextmanager
def connect(db_file):
  """SQLite に接続し、抜けるときに必ず閉じる。

  `with sqlite3.connect(...) as conn:` は commit / rollback をするだけで接続を閉じないため、
  常時動く Bot では閉じ忘れた接続が溜まっていく。ここでは commit / rollback に加えて close する。
  timeout は、バックグラウンド同期の書き込みとコマンドの読み書きが重なったときに待つ秒数。"""
  conn = sqlite3.connect(db_file, timeout=30)
  try:
    with conn:  # 正常終了なら commit、例外なら rollback
      yield conn
  finally:
    conn.close()

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))


def backup_database(db_file, keep=14):
  """DB を <DBのあるフォルダ>/backups/database-YYYYMMDD.db にコピーし、古いものは keep 個まで残す。
  sqlite3 の backup API を使うので、Bot が動いている最中でも壊れないコピーが取れる。
  戻り値: 作成したバックアップのパス"""
  backup_dir = os.path.join(os.path.dirname(os.path.abspath(db_file)), "backups")
  os.makedirs(backup_dir, exist_ok=True)
  # 前回途中で落ちたときの一時ファイルを消す
  for leftover in os.listdir(backup_dir):
    if leftover.endswith(".db.tmp"):
      os.remove(os.path.join(backup_dir, leftover))
  name = f"database-{datetime.now(JST).strftime('%Y%m%d')}.db"
  path = os.path.join(backup_dir, name)
  tmp = path + ".tmp"
  with closing(sqlite3.connect(db_file)) as src, closing(sqlite3.connect(tmp)) as dst:
    src.backup(dst)
  os.replace(tmp, path)  # 途中で落ちても壊れたファイルが残らないよう、書き終えてから置き換える

  backups = sorted(f for f in os.listdir(backup_dir) if f.startswith("database-") and f.endswith(".db"))
  for old in backups[:-keep] if keep > 0 else []:
    os.remove(os.path.join(backup_dir, old))
  return path

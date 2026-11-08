"""AtCoder アカウントの本人確認。

登録したい人に確認コードを発行し、AtCoder のプロフィールの「所属 (Affiliation)」に書いてもらう。
プロフィールページの所属欄にコードがあれば、そのアカウントを編集できる本人だと分かる。
"""
import html
import re
import secrets
import time

from atcoder import db
from atcoder import http_client

CODE_TTL_SEC = 60 * 60  # 確認コードの有効期限
_AFFILIATION_RE = re.compile(r"<th[^>]*>\s*(?:Affiliation|所属)\s*</th>\s*<td[^>]*>(.*?)</td>", re.S)


def init_verification_table(db_file):
  with db.connect(db_file) as conn:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS pending_verifications (
        discord_id   INTEGER PRIMARY KEY,
        atcoder_name TEXT,
        discord_name TEXT,
        code         TEXT,
        created_at   REAL
      )
    """)


def create_pending_verification(discord_id, atcoder_name, discord_name, db_file):
  """確認コードを発行して保存する (同じ人の前のコードは置き換える)。戻り値: コード"""
  code = f"atcbot-{secrets.token_hex(4)}"
  with db.connect(db_file) as conn:
    conn.execute(
      "INSERT OR REPLACE INTO pending_verifications VALUES (?, ?, ?, ?, ?)",
      (discord_id, atcoder_name, discord_name, code, time.time()),
    )
  return code


def get_pending_verification(discord_id, db_file, now=None):
  """有効期限内の確認待ちを (atcoder_name, discord_name, code) で返す。無ければ None。"""
  now = time.time() if now is None else now
  with db.connect(db_file) as conn:
    row = conn.execute(
      "SELECT atcoder_name, discord_name, code, created_at FROM pending_verifications WHERE discord_id = ?",
      (discord_id,),
    ).fetchone()
  if row is None or now - row[3] > CODE_TTL_SEC:
    return None
  return row[0], row[1], row[2]


def delete_pending_verification(discord_id, db_file):
  with db.connect(db_file) as conn:
    conn.execute("DELETE FROM pending_verifications WHERE discord_id = ?", (discord_id,))


def affiliation_of(page_html):
  """プロフィールページの HTML から所属欄の文字列を取り出す (無ければ空文字)。"""
  m = _AFFILIATION_RE.search(page_html or "")
  return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


async def affiliation_contains(atcoder_name, code):
  """所属欄に code が書かれていれば True、無ければ False、取得できなければ None。"""
  try:
    status, page = await http_client.get(
      f"https://atcoder.jp/users/{atcoder_name}", log=f"本人確認 [{atcoder_name}]", as_text=True
    )
  except Exception as e:
    print(f"[verification] {atcoder_name}: {type(e).__name__}: {e}")
    return None
  if status != 200:
    return None
  return code in affiliation_of(page)

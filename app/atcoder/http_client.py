"""外部API (atcoder.jp / kenkoooo.com) へのリクエストを1か所にまとめる。

同じホストへのリクエストは、Bot 全体で必ず MIN_INTERVAL_SEC 秒以上の間隔を空ける。
コマンドと自動タスクが同時に動いても、ここを通る限り1秒に1回を超えない。
"""
import asyncio
import time
from urllib.parse import urlsplit

import aiohttp
import discord_logger

MIN_INTERVAL_SEC = 1.0
TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AtCoderBot/1.0)"}

# イベントループごとに分ける (テストで asyncio.run を何度も呼んでも Lock が壊れないように)
_state = {}  # loop_id -> {"locks": {host: Lock}, "last": {host: monotonic秒}}


def _loop_state():
  loop_id = id(asyncio.get_running_loop())
  st = _state.get(loop_id)
  if st is None:
    st = _state[loop_id] = {"locks": {}, "last": {}}
  return st


async def wait_turn(host):
  """host へのリクエスト枠が空くまで待つ。前回のリクエスト開始から MIN_INTERVAL_SEC 秒以上空ける。"""
  st = _loop_state()
  lock = st["locks"].setdefault(host, asyncio.Lock())
  async with lock:
    wait = st["last"].get(host, float("-inf")) + MIN_INTERVAL_SEC - time.monotonic()
    if wait > 0:
      await asyncio.sleep(wait)
    st["last"][host] = time.monotonic()


async def get(url, log=None, parse_json=True):
  """GET して (status, data) を返す。data は status が 200 のときだけ JSON (parse_json=False なら None)。
  通信エラーやタイムアウトは例外として呼び出し元に投げる。
  log を渡すと discord_logger に「APIを叩いた: {log}」と記録する。"""
  await wait_turn(urlsplit(url).hostname)
  if log:
    await discord_logger.log_api(f"APIを叩いた: {log}")
  async with aiohttp.ClientSession(headers=HEADERS) as session:
    async with session.get(url, timeout=TIMEOUT) as resp:
      if resp.status != 200 or not parse_json:
        return resp.status, None
      return resp.status, await resp.json(content_type=None)


async def get_json(url, log=None):
  """GET して JSON を返す。200 以外は aiohttp.ClientResponseError 相当の例外を投げる。"""
  status, data = await get(url, log=log)
  if status != 200:
    raise RuntimeError(f"HTTP {status}: {url}")
  return data

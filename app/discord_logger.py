import asyncio
import datetime

JST = datetime.timezone(datetime.timedelta(hours=9))

# APIを叩くたびに1通ずつ送って送信完了を待つと、全員分の更新で数十通になり
# Discord のレート制限 (1チャンネル約5通/5秒) で本来の処理が数十秒止まってしまう。
# そのため log_api はバッファに貯めるだけにして、まとめて別タスクで送る。
FLUSH_INTERVAL_SEC = 5
MESSAGE_MAX = 1900  # Discord のメッセージ上限は2000文字
BUFFER_MAX = 500    # 送信できない状態が続いてもメモリを食い潰さないように上限を設ける

_channel = None
_buffer = []
_flush_task = None


def set_log_channel(channel):
  global _channel
  _channel = channel


def _chunks(lines):
  chunk = []
  size = 0
  for line in lines:
    line = line[:MESSAGE_MAX]
    if chunk and size + len(line) + 1 > MESSAGE_MAX:
      yield "\n".join(chunk)
      chunk, size = [], 0
    chunk.append(line)
    size += len(line) + 1
  if chunk:
    yield "\n".join(chunk)


async def _flush_later():
  global _flush_task, _buffer
  try:
    await asyncio.sleep(FLUSH_INTERVAL_SEC)
    lines, _buffer = _buffer, []
    channel = _channel
    if channel is None:
      return
    for text in _chunks(lines):
      try:
        await channel.send(text)
      except Exception as e:
        print(f"[discord_logger] 通知失敗: {e}")
  finally:
    _flush_task = None
    if _buffer and _channel is not None:
      _schedule_flush()


def _schedule_flush():
  global _flush_task
  if _flush_task is None:
    try:
      _flush_task = asyncio.get_running_loop().create_task(_flush_later())
    except RuntimeError:
      pass  # イベントループ外 (テストなど) では送らない


async def log_api(message):
  if _channel is None:
    return
  now = datetime.datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')
  _buffer.append(f"{message} [{now}]")
  if len(_buffer) > BUFFER_MAX:
    del _buffer[:len(_buffer) - BUFFER_MAX]
  _schedule_flush()

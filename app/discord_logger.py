import datetime

JST = datetime.timezone(datetime.timedelta(hours=9))

_channel = None


def set_log_channel(channel):
  global _channel
  _channel = channel


async def log_api(message):
  if _channel is not None:
    try:
      now = datetime.datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')
      await _channel.send(f"{message} [{now}]\n")
    except Exception as e:
      print(f"[discord_logger] 通知失敗: {e}")

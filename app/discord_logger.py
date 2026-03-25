_channel = None


def set_log_channel(channel):
  global _channel
  _channel = channel


async def log_api(message):
  if _channel is not None:
    try:
      await _channel.send(message)
    except Exception as e:
      print(f"[discord_logger] 通知失敗: {e}")

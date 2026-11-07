import aiohttp
import discord_logger

async def atcoder_user_exists(atcoder_name):
  """AtCoderユーザーが存在するかをユーザーページのステータスで判定する。

  history/json は存在しないユーザーでもコンテスト未参加のユーザーでも 200 [] を返すため、
  存在確認には使えない。ユーザーページは存在しない場合 404 を返す。

  戻り値: True (存在する) / False (存在しない) / None (通信エラー等で判定不能)
  """
  url = f"https://atcoder.jp/users/{atcoder_name}"
  await discord_logger.log_api(f"APIを叩いた: ユーザー存在確認 (atcoder_user_exists) [{atcoder_name}]")
  headers = {"User-Agent": "Mozilla/5.0 (compatible; AtCoderBot/1.0)"}
  timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
  try:
    async with aiohttp.ClientSession(headers=headers) as session:
      async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
        if resp.status == 200:
          return True
        if resp.status == 404:
          return False
        return None
  except Exception as e:
    print(f"[atcoder_user_exists] {atcoder_name}: {type(e).__name__}: {e}")
    return None

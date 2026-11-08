from atcoder import http_client


async def atcoder_user_exists(atcoder_name):
  """AtCoderユーザーが存在するかをユーザーページのステータスで判定する。

  history/json は存在しないユーザーでもコンテスト未参加のユーザーでも 200 [] を返すため、
  存在確認には使えない。ユーザーページは存在しない場合 404 を返す。

  戻り値: True (存在する) / False (存在しない) / None (通信エラー等で判定不能)
  """
  url = f"https://atcoder.jp/users/{atcoder_name}"
  try:
    status, _ = await http_client.get(url, log=f"ユーザー存在確認 [{atcoder_name}]", parse_json=False)
  except Exception as e:
    print(f"[atcoder_user_exists] {atcoder_name}: {type(e).__name__}: {e}")
    return None
  if status == 200:
    return True
  if status == 404:
    return False
  return None

import asyncio

async def initial_fetch_user_data(atcoder_name, db_file, force_contest=False):
  from atcoder.fetch_and_cache_contest_history import fetch_and_cache_contest_history
  from atcoder.fetch_and_cache_ac_submissions import fetch_and_cache_ac_submissions
  # 同じサーバーへのアクセス間隔 (1秒に1回) は http_client が守る
  await fetch_and_cache_contest_history(atcoder_name, db_file, force=force_contest)
  await fetch_and_cache_ac_submissions(atcoder_name, db_file)


async def refresh_users_data(atcoder_names, db_file, interval=0.0, force_contest=False):
  """集計の直前に、指定ユーザーのコンテスト履歴とAC提出キャッシュを差分更新する。
  daily_update は1日1回しか走らないため、これを呼ばないと当日分のACやレート変化が反映されない。
  1人失敗しても他のユーザーの更新は続ける。
  force_contest=True ならコンテスト履歴をキャッシュの有効期限に関係なく取り直す。
  API のアクセス間隔は http_client が守るので、interval は追加で空けたい場合だけ指定する。"""
  from atcoder.get_registered_user import get_registered_user
  for i, atcoder_name in enumerate(atcoder_names):
    if i > 0 and interval > 0:
      await asyncio.sleep(interval)
    # 更新中に /user unregister されたユーザーのキャッシュを書き戻さないよう、直前に登録を確認する
    if get_registered_user(atcoder_name, db_file) is None:
      continue
    try:
      await initial_fetch_user_data(atcoder_name, db_file, force_contest=force_contest)
    except Exception as e:
      print(f"[refresh_users_data] {atcoder_name}: {type(e).__name__}: {e}")

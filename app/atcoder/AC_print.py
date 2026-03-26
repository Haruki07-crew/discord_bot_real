async def AC_print(atcoder_name, db_file="database.db"):
  from atcoder.get_ac_count import get_ac_count
  from atcoder.count_period_ac import count_period_ac
  ac_sum = await get_ac_count(atcoder_name, db_file)
  daily_ac_sum, daily_ac_point_sum = await count_period_ac(atcoder_name, 1, db_file)
  if daily_ac_sum == 0:
    result = f"{atcoder_name}さんの今までのAC数は{ac_sum}\n今日のAC数は{daily_ac_sum}です。精進せんかい"
  else:
    result = f"{atcoder_name}さんの今までのAC数は{ac_sum}\n今日のAC数は{daily_ac_sum}で{daily_ac_point_sum}点取得しました"
  return result

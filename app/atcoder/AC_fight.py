async def AC_fight(user_name_dict, day, db_file="database.db"):
  from atcoder.count_period_ac import count_period_ac
  result = []
  for atcoder_name, discord_name in user_name_dict.items():
    ac_count = await count_period_ac(atcoder_name, day, db_file)
    result.append({"atcoder_name": atcoder_name, "discord_name": discord_name, "ac": ac_count})
  sorted_result = sorted(result, key=lambda x: (x["ac"][0], x["ac"][1]), reverse=True)
  return sorted_result

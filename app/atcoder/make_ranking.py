async def make_ranking(user_name_dict, day, db_file="database.db"):
  from atcoder.AC_fight import AC_fight
  result = await AC_fight(user_name_dict, day, db_file)
  if not result:
    return []
  ranking = []
  cur_place = 0
  prev_ac = -1
  prev_point = -1
  for i, d in enumerate(result):
    ac_num = d["ac"][0]
    ac_point = d["ac"][1]
    if ac_num != prev_ac or ac_point != prev_point:
      cur_place = i + 1
    if cur_place == 1:
      figure = " 🥇 "
    elif cur_place == 2:
      figure = " 🥈 "
    elif cur_place == 3:
      figure = " 🥉 "
    else:
      figure = " 👤 "
    ranking.append({
      "place": cur_place,
      "figure": figure,
      "atcoder_name": d["atcoder_name"],
      "discord_name": d["discord_name"],
      "ac": ac_num,
      "point": ac_point
    })
    prev_ac = ac_num
    prev_point = ac_point
  return ranking

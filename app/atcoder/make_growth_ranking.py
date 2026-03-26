async def make_growth_ranking(user_name_dict, day, db_file="database.db"):
  from atcoder.AC_fight import AC_fight
  from atcoder.get_ac_rate_change_data import get_ac_rate_change_data
  ac_list = await AC_fight(user_name_dict, day, db_file)
  rate_data = await get_ac_rate_change_data(user_name_dict, day, db_file)

  merged = []
  for entry in ac_list:
    name = entry["atcoder_name"]
    merged.append({
      "atcoder_name": name,
      "discord_name": entry["discord_name"],
      "ac": entry["ac"][0],
      "point": entry["ac"][1],
      "rate_change": rate_data.get(name, {}).get("rate_change", 0),
    })

  sorted_data = sorted(merged, key=lambda x: (x["rate_change"], x["ac"]), reverse=True)

  ranking = []
  prev_rc, prev_ac = None, None
  cur_place = 0
  for i, d in enumerate(sorted_data):
    if d["rate_change"] != prev_rc or d["ac"] != prev_ac:
      cur_place = i + 1
    if cur_place == 1:
      figure = " 🥇 "
    elif cur_place == 2:
      figure = " 🥈 "
    elif cur_place == 3:
      figure = " 🥉 "
    else:
      figure = " 👤 "
    ranking.append({**d, "place": cur_place, "figure": figure})
    prev_rc = d["rate_change"]
    prev_ac = d["ac"]

  return ranking

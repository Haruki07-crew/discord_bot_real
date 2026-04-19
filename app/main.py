## @file main.py
## @brief Discord BotのメインファイルおよびSlashコマンド定義
## @details discord.pyのapp_commandsを使用してAtCoder関連のコマンドを提供する。

import discord
from discord import app_commands
from discord.ext import tasks
import config as config
from atcoder import *
import asyncio
import datetime
from server import server_thread
import discord_logger

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

admin_id = config.ADMIN_ID
ranking_channel_id = int(config.RANKING_CHANNEL_ID) if config.RANKING_CHANNEL_ID else None
DB_FILE = "database.db"


## @brief 毎日0時(JST)に全登録ユーザーのデータをAPIから更新するバックグラウンドタスク
JST = datetime.timezone(datetime.timedelta(hours=9))

@tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=JST))
async def daily_update():
  print("[daily_update] Starting daily data update...")
  users = list(get_user_dict(DB_FILE).keys())
  for atcoder_name in users:
    try:
      await initial_fetch_user_data(atcoder_name, DB_FILE)
      print(f"[daily_update] Updated {atcoder_name}")
    except Exception as e:
      print(f"[daily_update] Error updating {atcoder_name}: {e}")
    await asyncio.sleep(1.5)
  print("[daily_update] Daily update complete")


## @brief 毎週月曜0:15(JST)に週次ランキングと累積グラフを投稿するタスク
## @details 直近1週間のAC数・点数・レート変化をテキストで表示し、
##          12週サイクルの累積折れ線グラフ(AC数版・点数版)を投稿する。
@tasks.loop(time=datetime.time(hour=0, minute=15, tzinfo=JST))
async def weekly_ranking_post():
  now = datetime.datetime.now(JST)
  if now.weekday() != 0:  # 月曜日のみ
    return

  print("[weekly_ranking_post] Starting weekly post...")

  if ranking_channel_id is None:
    print("[weekly_ranking_post] RANKING_CHANNEL_ID not set, skipping")
    return
  channel = client.get_channel(ranking_channel_id)
  if channel is None:
    print("[weekly_ranking_post] Channel not found, skipping")
    return

  try:
    user = get_user_dict(DB_FILE)
    if not user:
      print("[weekly_ranking_post] No registered users, skipping")
      return

    # 今週のデータを取得 (直近7日)
    ranking_data = await make_growth_ranking(user, 7, DB_FILE)
    if not ranking_data:
      print("[weekly_ranking_post] No ranking data, skipping")
      return

    # 週次サイクルを進める
    cycle_id, week_number = advance_weekly_cycle(DB_FILE)
    print(f"[weekly_ranking_post] cycle={cycle_id}, week={week_number}")

    # スナップショットを保存
    snapshot_data = [
      {
        "atcoder_name": d["atcoder_name"],
        "ac_count": d["ac"],
        "ac_point": d["point"],
        "rate_change": d["rate_change"],
      }
      for d in ranking_data
    ]
    save_weekly_snapshot(cycle_id, week_number, snapshot_data, DB_FILE)

    # テキスト embed (今週の結果)
    embed = discord.Embed(
      title=f"🏆 Diligence & Growth [{week_number}週目]",
      color=0xFFD700,
      timestamp=now
    )
    for data in ranking_data:
      rc = data["rate_change"]
      rc_str = f"+{rc}" if rc >= 0 else str(rc)
      embed.add_field(
        name=f"{data['figure']}{data['place']}位 : {data['atcoder_name']}({data['discord_name']})",
        value=f"Rate: **{rc_str}**　AC数 : **{data['ac']}** AC  点数 : **{data['point']}** 点",
        inline=False
      )

    # 累積グラフ用データを取得
    snapshots = get_weekly_snapshots(cycle_id, DB_FILE)

    # AC数版グラフ
    graph_ac = create_weekly_graph(snapshots, week_number, x_axis="ac")
    # 点数版グラフ
    graph_point = create_weekly_graph(snapshots, week_number, x_axis="point")

    files = []
    if graph_ac:
      file_ac = discord.File(graph_ac, filename="weekly_ac.png")
      files.append(file_ac)
      embed.set_image(url="attachment://weekly_ac.png")

    await channel.send(embed=embed, files=files if files else discord.utils.MISSING)

    # 点数版は別embedで投稿
    if graph_point:
      embed_point = discord.Embed(
        title=f"📊 累積点数 vs レート変化 [{week_number}週目]",
        color=0x3498db,
        timestamp=now
      )
      file_point = discord.File(graph_point, filename="weekly_point.png")
      embed_point.set_image(url="attachment://weekly_point.png")
      await channel.send(embed=embed_point, file=file_point)

    print(f"[weekly_ranking_post] Posted week {week_number} of cycle {cycle_id}")

  except Exception as e:
    print(f"[weekly_ranking_post] Error: {e}")

@weekly_ranking_post.before_loop
async def before_weekly_ranking_post():
  await client.wait_until_ready()


## @brief 1時間ごとに prev_contest+1 のABC結果を確認し、確定したら自動でランキングを投稿するタスク
## @details DBに保存した prev_contest の次の番号のコンテスト結果を AtCoder API で確認し、
##          レーティング更新済みデータが現れたら投稿して prev_contest を更新する。
##          RANKING_CHANNEL_ID が未設定の場合はスキップする。
@tasks.loop(hours=1)
async def auto_abc_ranking():
  now_str = datetime.datetime.now(JST).strftime('%H:%M:%S.%f')[:-3]
  print(f"[{now_str}][auto_abc_ranking] tick")

  if ranking_channel_id is None:
    print(f"[{now_str}][auto_abc_ranking] RANKING_CHANNEL_ID not set, skipping")
    return

  try:
    prev = get_prev_contest(DB_FILE)
    if prev is None:
      print(f"[{now_str}][auto_abc_ranking] prev_contest not set, skipping")
      return

    next_number = prev + 1
    contest_id = f"abc{next_number:03d}"

    result = await fetch_abc_standings_if_ready(next_number, DB_FILE)
    if result is None:
      print(f"[{now_str}][auto_abc_ranking] {contest_id} results not ready yet, skipping")
      return

    rated, unrated = result

    # 結果確定 → prev_contest を更新（参加者なしでも二重投稿を防ぐ）
    set_prev_contest(next_number, DB_FILE)
    print(f"[auto_abc_ranking] Results ready for {contest_id}, posting...")

    if not rated and not unrated:
      print(f"[auto_abc_ranking] No registered users participated in {contest_id}")
      return

    channel = client.get_channel(ranking_channel_id)
    if channel is None:
      print(f"[auto_abc_ranking] Channel {ranking_channel_id} not found")
      return

    embed = discord.Embed(
      title=f"🏆 ABC{next_number:03d} 登録ユーザーランキング",
      description="コンテスト結果が確定しました！",
      color=0xFFD700,
      timestamp=datetime.datetime.now(JST)
    )

    prev_rank = -1
    place = 0
    for i, d in enumerate(rated):
      if d["rank"] != prev_rank:
        place = i + 1
      figure = "🥇" if place == 1 else "🥈" if place == 2 else "🥉" if place == 3 else "👤"
      rc = d.get("rate_change", 0)
      rc_str = f"+{rc}" if rc >= 0 else str(rc)
      embed.add_field(
        name=f"{figure} {place}位 : {d['atcoder_name']}({d['discord_name']})",
        value=f"Rank: **{d['rank']}** 位　AC: **{d.get('ac_count', 0)}** 問　Perf: **{d['performance']}**　Rate: **{rc_str}** ({d['old_rating']} → {d['new_rating']})",
        inline=False
      )
      prev_rank = d["rank"]

    if unrated:
      unrated_lines = [
        f"{d['atcoder_name']}({d['discord_name']})  {d['rank']}位  AC: {d.get('ac_count', 0)}問"
        for d in unrated
      ]
      embed.add_field(
        name="📋 Unrated参加者",
        value="\n".join(unrated_lines),
        inline=False
      )

    await channel.send(embed=embed)
    print(f"[auto_abc_ranking] Posted {contest_id} ranking")

  except Exception as e:
    print(f"[auto_abc_ranking] Error: {e}")

@auto_abc_ranking.before_loop
async def before_auto_abc_ranking():
  await client.wait_until_ready()


## @brief Bot起動時のイベントハンドラ
## @details DBの初期化とSlashコマンドの同期を行う
@client.event
async def on_ready():
  init_db(DB_FILE)
  await tree.sync()
  if not daily_update.is_running():
    daily_update.start()
  if not weekly_ranking_post.is_running():
    weekly_ranking_post.start()
  if not auto_abc_ranking.is_running():
    auto_abc_ranking.start()
  # prev_contest が未設定の場合、APIで直近コンテスト番号を自動取得して初期化
  if get_prev_contest(DB_FILE) is None:
    try:
      number = await get_latest_ended_abc_number()
      if number is not None:
        set_prev_contest(number, DB_FILE)
        print(f"[on_ready] prev_contest initialized to {number} (from API)")
      else:
        set_prev_contest(454, DB_FILE)
        print("[on_ready] prev_contest initialized to 450 (API fallback)")
    except Exception:
      set_prev_contest(454, DB_FILE)
      print("[on_ready] prev_contest initialized to 450 (error fallback)")
  log_channel = client.get_channel(1486382744153100469)
  discord_logger.set_log_channel(log_channel)
  print("activate the bot  now!!!!")


TEST_USERS = {
  "hanaosi": "東原遙希",
  "yuukougun": "後藤勇輝",
  "mrkm1627": "村上功一",
  "asyogo": "赤澤翔悟",
  "Kanata0724": "中井奏汰",
  "kmiarrbxy": "鎌田瑞生",
  "ponkura": "伊戸寛哲",
  "yudai17": "山口雄大",
  "misuke3779": "石川涼介",
  "sky7": "宮武幸斗",
  "KawataAki": "川田晃弘",
}

OTHER_KOSEN_USERS = {
  "bandai0412": "バンダイ君",
  "googology": "googologyくん",
  "Un_titled": "アンタイトルド",
  "yuukougun": "yuukougun",
  "hanaosi": "hanaosi",
  "mrkm1627": "mrkm1627",
  "Cafe_j19419": "Cafe_j19419",
  "Not_Leonian": "Not_Leonian",
  "yiwiy9": "yiwiy9",
}

_registration_lock = asyncio.Lock()

async def _bulk_register(message, user_dict):
  """指定されたユーザー辞書を一括登録する共通処理"""
  if str(message.author.id) != str(admin_id):
    return
  if _registration_lock.locked():
    await message.channel.send("⚠️ 現在登録処理中です。完了するまでお待ちください。")
    return
  async with _registration_lock:
    register_id = message.author.id
    discord_id = message.author.id

    total = len(user_dict)
    await message.channel.send(f"ユーザー登録を開始します（{total}人）...")

    done = 0
    for atcoder_name, discord_name in user_dict.items():
      try:
        exist = get_registered_user(atcoder_name, DB_FILE)
        if exist:
          await message.channel.send(f"⏭️ {atcoder_name}({discord_name}) は既に登録済みです")
          continue
        register_user(atcoder_name, discord_name, discord_id, register_id, DB_FILE)
        await initial_fetch_user_data(atcoder_name, DB_FILE)
        done += 1
        await message.channel.send(f"✅ {atcoder_name}({discord_name}) を登録しました ({done}/{total})")
      except Exception as e:
        await message.channel.send(f"⚠️ {atcoder_name} の登録に失敗: {e}")

    await message.channel.send("✅ ユーザー登録がすべて完了しました！")

@client.event
async def on_message(message):
  if message.author.bot:
    return
  text = message.content.strip()
  if text == "テスト用にユーザー登録":
    await _bulk_register(message, TEST_USERS)
  elif text == "他高専テスト用に登録":
    await _bulk_register(message, OTHER_KOSEN_USERS)


## @brief ユーザーの精進記録をEmbedで返すコマンド
## @details 今日および通算のAC数・獲得点数を表示する
## @param interaction Discordのインタラクション
## @param atcoder_name 対象のAtCoderユーザー名
@tree.command(name = "syozin", description="Atcoderの精進記録を返します")
async def rating_command(interaction: discord.Interaction, atcoder_name: str):
  await interaction.response.defer()
  try:
    ac_sum = await get_ac_count(atcoder_name, DB_FILE)
    ac_daily = await count_period_ac(atcoder_name, 1, DB_FILE)
    problems_url = f"https://kenkoooo.com/atcoder/#/user/{atcoder_name}?userPageTab=Progress+Charts"
    embed = discord.Embed(
      title = f"{atcoder_name}さんの精進記録",
      color = 0x2ecc71,
      url = problems_url,
      timestamp = interaction.created_at
    )
    embed.add_field(
      name = "これまでのAC数",
      value = f"**{ac_sum}** AC",
      inline = True
    )
    embed.add_field(
      name = "今日のAC数",
      value = f"**{ac_daily[0]}** AC",
      inline = True
    )
    embed.add_field(
      name = "今日の獲得点数",
      value = f"**{round(ac_daily[1])}** 点",
      inline = True
    )
    if ac_daily[0] == 0:
      embed.set_footer(text = "精進せんかい雑魚bro\n")
    else:
      embed.set_footer(text = "偉すぎるぜbro\n")
    await interaction.edit_original_response(embed = embed)
  except Exception as e:
    print(e)
    await interaction.edit_original_response(content=f"⚠️ エラーが発生しました。お手数ですが(<@{admin_id}>)までご連絡ください。")


## @brief ユーザーをDBに登録するコマンド
## @details AtCoderの存在確認後にDBへ登録する。既登録の場合はエラーを返す。
## @param interaction Discordのインタラクション
## @param atcoder_name 登録するAtCoderユーザー名
## @param discord_name 登録するDiscordユーザー名 (手動入力)
@tree.command(name = "user_register", description="ユーザーを登録します")
async def user_register(interaction: discord.Interaction, atcoder_name: str, discord_name: str):
  await interaction.response.defer()
  try:
    register_id = interaction.user.id
    discord_id = interaction.user.id

    exist_user = get_registered_user(atcoder_name, DB_FILE)
    if exist_user:
      await interaction.followup.send(f"⚠️エラー: {atcoder_name} さんはすでに<@{exist_user[1]}>さんによって登録されています")
      return
    check = await get_latest_rating_nofstring(atcoder_name)
    if "存在しません" in str(check):
      await interaction.followup.send(f"⚠️エラー : {atcoder_name}は存在しません")
      return
    register_user(atcoder_name, discord_name, discord_id, register_id, DB_FILE)
    await interaction.followup.send(
      f"{discord_name} さんを {atcoder_name} で登録しました\n"
      f"提出履歴を取得中です...（提出数が多い場合は数分かかります）"
    )
    await asyncio.sleep(1.0)  # 存在確認のAtCoder APIから1秒空けてから全件取得
    await initial_fetch_user_data(atcoder_name, DB_FILE)
    await interaction.followup.send(f"✅ {atcoder_name} のデータ取得が完了しました")
  except Exception as e:
    print(e)
    await interaction.followup.send(content=f"⚠️ エラーが発生しました。お手数ですが(<@{admin_id}>)までご連絡ください。")


## @brief user_unregister の atcoder_name オートコンプリート (登録済みユーザー一覧)
async def registered_atcoder_autocomplete(interaction: discord.Interaction, current: str):
  users = get_user_dict(DB_FILE)
  return [
    app_commands.Choice(name=f"{atcoder} ({discord_name})", value=atcoder)
    for atcoder, discord_name in users.items()
    if current.lower() in atcoder.lower()
  ][:25]


## @brief ユーザーの登録を解除するコマンド
## @details 登録者本人またはadminのみ解除可能
## @param interaction Discordのインタラクション
## @param atcoder_name 登録解除するAtCoderユーザー名
@tree.command(name = "user_unregister", description="登録されているユーザーの登録を解除します")
@app_commands.autocomplete(atcoder_name=registered_atcoder_autocomplete)
async def user_unregister(interaction: discord.Interaction, atcoder_name: str):
  await interaction.response.defer()
  user_id = interaction.user.id
  register_id = get_register_id(atcoder_name, DB_FILE)
  if register_id is None:
    await interaction.followup.send(f"{atcoder_name}さんは登録されていません")
    return
  if user_id == register_id or user_id == int(admin_id):
    delete_user(atcoder_name, DB_FILE)
    await interaction.followup.send(f"{atcoder_name}さんの登録を解除しました")
  else:
    await interaction.followup.send(f"他人の登録を勝手に消すのはNGだぜbro")


## @brief 登録済みユーザーの一覧とレートをEmbedで表示するコマンド
## @param interaction Discordのインタラクション
@tree.command(name = "user_list", description="登録済みユーザーおよびレートを表示します")
async def user_list(interaction: discord.Interaction):
  await interaction.response.defer()
  try:
    user = get_user_dict(DB_FILE)
    if not user:
      await interaction.edit_original_response(content="登録されているユーザーがいません")
      return
    embed = discord.Embed(
      title = "登録ユーザー",
      color = 0x3498db,
      timestamp = interaction.created_at
    )
    for atcoder_name, discor_name in user.items():
      latest_rating = get_latest_rating_from_db(atcoder_name, DB_FILE)
      atcoder_url = f"https://atcoder.jp/users/{atcoder_name}"
      embed.add_field(
        name = f"{get_rate_heart(latest_rating)} {discor_name}",
        value = f"Atcoder_ID: [{atcoder_name}]({atcoder_url})\n Rating: **{latest_rating}**",
        inline = False
      )
    await interaction.edit_original_response(embed = embed)
  except Exception as e:
    print(e)
    await interaction.edit_original_response(content=f"⚠️ エラーが発生しました。お手数ですが(<@{admin_id}>)までご連絡ください。")


## @brief レート変化を主軸にしたランキングを表示するコマンド
## @details 第1キー: レート変化(降順)、第2キー: AC数(降順) でランキングを生成する
## @param interaction Discordのインタラクション
## @param period 比較期間
@tree.command(name="diligence_growth", description="レート変化とAC数のランキングを表示します")
@app_commands.choices(period=[
  app_commands.Choice(name = "1日",  value = 1),
  app_commands.Choice(name = "1週間", value = 7),
  app_commands.Choice(name = "1ヶ月", value = 30),
  app_commands.Choice(name = "3ヶ月", value = 90),
  app_commands.Choice(name = "半年",  value = 180),
  app_commands.Choice(name = "1年",  value = 365),
])
async def diligence_growth(interaction: discord.Interaction, period: app_commands.Choice[int]):
  await interaction.response.defer()
  try:
    user = get_user_dict(DB_FILE)
    day = period.value
    label = period.name
    ranking_data = await make_growth_ranking(user, day, DB_FILE)

    if not ranking_data:
      await interaction.edit_original_response(content="登録されているユーザーがいません")
      return

    embed = discord.Embed(
      title = f"🏆 Diligence & Growth [{label}]🏆",
      color = 0xFFD700,
      timestamp = interaction.created_at
    )
    for data in ranking_data:
      rc = data["rate_change"]
      rc_str = f"+{rc}" if rc >= 0 else str(rc)
      embed.add_field(
        name = f"{data['figure']}{data['place']}位 : {data['atcoder_name']}({data['discord_name']})",
        value = f"Rate: **{rc_str}**　AC数 : **{data['ac']}** AC  点数 : **{data['point']}** 点",
        inline = False
      )

    if day <= 7:
      ac_rate_data = {d["atcoder_name"]: d for d in ranking_data}
      graph_buf = create_ac_rate_graph(ac_rate_data, label)
    else:
      all_user_data = {}
      for atcoder_name in user:
        all_user_data[atcoder_name] = await get_progress_data(atcoder_name, day, DB_FILE)
      graph_buf = create_progress_graph(all_user_data)

    if graph_buf is None:
      await interaction.edit_original_response(embed=embed)
      return

    file = discord.File(graph_buf, filename="ac_rate.png")
    embed.set_image(url="attachment://ac_rate.png")
    await interaction.edit_original_response(content=None, embed=embed, attachments=[file])
  except Exception as e:
    print(e)
    await interaction.edit_original_response(content=f"⚠️ エラーが発生しました。お手数ですが(<@{admin_id}>)までご連絡ください。")


## @brief 点数を主軸にしたランキングを表示するコマンド (diligence_growthの点数版)
## @details 第1キー: レート変化(降順)、第2キー: 点数(降順) でランキングを生成する
## @param interaction Discordのインタラクション
## @param period 比較期間
@tree.command(name="diligence_growth_point", description="レート変化と点数のランキングを表示します")
@app_commands.choices(period=[
  app_commands.Choice(name = "1日",  value = 1),
  app_commands.Choice(name = "1週間", value = 7),
  app_commands.Choice(name = "1ヶ月", value = 30),
  app_commands.Choice(name = "3ヶ月", value = 90),
  app_commands.Choice(name = "半年",  value = 180),
  app_commands.Choice(name = "1年",  value = 365),
])
async def diligence_growth_point(interaction: discord.Interaction, period: app_commands.Choice[int]):
  await interaction.response.defer()
  try:
    user = get_user_dict(DB_FILE)
    day = period.value
    label = period.name
    ranking_data = await make_growth_ranking(user, day, DB_FILE)

    if not ranking_data:
      await interaction.edit_original_response(content="登録されているユーザーがいません")
      return

    # 点数でソートし直す (第1キー: レート変化, 第2キー: 点数)
    sorted_data = sorted(ranking_data, key=lambda x: (x["rate_change"], x["point"]), reverse=True)
    prev_rc, prev_pt = None, None
    cur_place = 0
    for i, d in enumerate(sorted_data):
      if d["rate_change"] != prev_rc or d["point"] != prev_pt:
        cur_place = i + 1
      if cur_place == 1:
        d["figure"] = " 🥇 "
      elif cur_place == 2:
        d["figure"] = " 🥈 "
      elif cur_place == 3:
        d["figure"] = " 🥉 "
      else:
        d["figure"] = " 👤 "
      d["place"] = cur_place
      prev_rc = d["rate_change"]
      prev_pt = d["point"]

    embed = discord.Embed(
      title = f"🏆 Diligence & Growth [点数] [{label}]🏆",
      color = 0x2ecc71,
      timestamp = interaction.created_at
    )
    for data in sorted_data:
      rc = data["rate_change"]
      rc_str = f"+{rc}" if rc >= 0 else str(rc)
      embed.add_field(
        name = f"{data['figure']}{data['place']}位 : {data['atcoder_name']}({data['discord_name']})",
        value = f"Rate: **{rc_str}**　点数 : **{data['point']}** 点  AC数 : **{data['ac']}** AC",
        inline = False
      )

    if day <= 7:
      # 散布図 (横軸: 点数, 縦軸: レート変化)
      point_rate_data = {d["atcoder_name"]: {"ac": d["point"], "rate_change": d["rate_change"]} for d in sorted_data}
      graph_buf = create_ac_rate_graph(point_rate_data, f"{label} (点数)")
    else:
      all_user_data = {}
      for atcoder_name in user:
        all_user_data[atcoder_name] = await get_progress_data(atcoder_name, day, DB_FILE)
      graph_buf = create_progress_graph(all_user_data)

    if graph_buf is None:
      await interaction.edit_original_response(embed=embed)
      return

    file = discord.File(graph_buf, filename="point_rate.png")
    embed.set_image(url="attachment://point_rate.png")
    await interaction.edit_original_response(content=None, embed=embed, attachments=[file])
  except Exception as e:
    print(e)
    await interaction.edit_original_response(content=f"⚠️ エラーが発生しました。お手数ですが(<@{admin_id}>)までご連絡ください。")


## @brief 全登録ユーザーの現在のAC数と連続AC日数を表示するコマンド
## @param interaction Discordのインタラクション
@tree.command(name="everyone_state", description="全員の総AC数と連続AC日数を表示します")
async def everyone_state(interaction: discord.Interaction):
  await interaction.response.defer()
  try:
    user = get_user_dict(DB_FILE)
    if not user:
      await interaction.edit_original_response(content="登録されているユーザーがいません")
      return

    embed = discord.Embed(
      title="全員の精進状況",
      color=0x3498db,
      timestamp=interaction.created_at
    )

    for atcoder_name, discord_name in user.items():
      ac_count = await get_ac_count(atcoder_name, DB_FILE)
      streak = get_ac_streak(atcoder_name, DB_FILE)
      streak_text = f"{streak}日連続" if streak > 0 else "0日"
      embed.add_field(
        name=f"{discord_name} ({atcoder_name})",
        value=f"総AC数: **{ac_count}** AC　連続AC: **{streak_text}**",
        inline=False
      )

    await interaction.edit_original_response(embed=embed)
  except Exception as e:
    print(e)
    await interaction.edit_original_response(content=f"⚠️ エラーが発生しました。お手数ですが(<@{admin_id}>)までご連絡ください。")


## @brief 指定したABCコンテストの登録ユーザーランキングを表示するコマンド
## @details AtCoderのstandings APIを1回叩き、登録ユーザーをratedとunratedに分類して表示する。
##          0問の場合は参加なしとみなし除外する。unrated参加者はランキング外に別途表示する。
## @param interaction Discordのインタラクション
## @param contest_number ABCのコンテスト番号 (例: 400)
@tree.command(name="abc_ranking", description="指定したABCコンテストの登録ユーザーランキングを表示します (例: 400)")
async def abc_ranking(interaction: discord.Interaction, contest_number: int):
  await interaction.response.defer()
  try:
    if not (1 <= contest_number <= 999):
      await interaction.edit_original_response(content="⚠️ コンテスト番号は1〜999の範囲で入力してください")
      return

    rated, unrated = await get_abc_standings(contest_number, DB_FILE)

    if not rated and not unrated:
      await interaction.edit_original_response(
        content=f"ABC{contest_number:03d} に参加した登録ユーザーがいません"
      )
      return

    embed = discord.Embed(
      title=f"🏆 ABC{contest_number:03d} 登録ユーザーランキング",
      color=0xFFD700,
      timestamp=interaction.created_at
    )

    prev_rank = -1
    place = 0
    for i, d in enumerate(rated):
      if d["rank"] != prev_rank:
        place = i + 1
      if place == 1:
        figure = "🥇"
      elif place == 2:
        figure = "🥈"
      elif place == 3:
        figure = "🥉"
      else:
        figure = "👤"
      rc = d.get("rate_change", 0)
      rc_str = f"+{rc}" if rc >= 0 else str(rc)
      embed.add_field(
        name=f"{figure} {place}位 : {d['atcoder_name']}({d['discord_name']})",
        value=f"Rank: **{d['rank']}** 位　AC: **{d.get('ac_count', 0)}** 問　Perf: **{d['performance']}**　Rate: **{rc_str}** ({d['old_rating']} → {d['new_rating']})",
        inline=False
      )
      prev_rank = d["rank"]

    if unrated:
      unrated_lines = [
        f"{d['atcoder_name']}({d['discord_name']})  {d['rank']}位  AC: {d.get('ac_count', 0)}問"
        for d in unrated
      ]
      embed.add_field(
        name="📋 Unrated参加者",
        value="\n".join(unrated_lines),
        inline=False
      )

    await interaction.edit_original_response(embed=embed)
  except Exception as e:
    print(e)
    await interaction.edit_original_response(
      content=f"⚠️ エラーが発生しました。ABC{contest_number:03d} は存在しないか、まだ終了していない可能性があります。お手数ですが(<@{admin_id}>)までご連絡ください。"
    )


## @brief Slashコマンドのエラーをキャッチしてadminに通知するハンドラ
## @param interaction Discordのインタラクション
## @param error 発生したAppCommandError
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
  error_message = f"<@{admin_id}> エラー起きたぞ"
  print(f"コマンド'{interaction.command.name}'でエラー発生")
  try:
    if interaction.response.is_done():
      await interaction.followup.send(content=error_message, ephemeral=True)
    else:
      await interaction.response.send_message(error_message, ephemeral=True)
    admin = await client.fetch_user(admin_id)
    await admin.send(f"エラー\n: '/{interaction.command.name}'\n実行者: {interaction.user}\nエラー内容{error}")
  except Exception as e:
    print(f"エラー発生: {e}")

server_thread()
client.run(config.DISCORD_TOKEN)

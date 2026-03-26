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

## @brief 指定期間のランキング(embed)とAC数/レート変化グラフをチャンネルに投稿する
## @param channel 投稿先Discordチャンネル
## @param days 集計期間 (日数)
## @param label 期間ラベル (例: "1週間")
## @param filename グラフ画像のファイル名
async def _post_period_summary(channel, days, label, filename):
  user = get_user_dict(DB_FILE)
  if not user:
    return

  ranking_data = await make_growth_ranking(user, days, DB_FILE)
  if not ranking_data:
    return

  embed = discord.Embed(
    title=f"🏆 Diligence & Growth [{label}]",
    color=0xFFD700,
    timestamp=datetime.datetime.now(JST)
  )
  for data in ranking_data:
    rc = data["rate_change"]
    rc_str = f"+{rc}" if rc >= 0 else str(rc)
    embed.add_field(
      name=f"{data['figure']}{data['place']}位 : {data['atcoder_name']}({data['discord_name']})",
      value=f"Rate: **{rc_str}**　AC数 : **{data['ac']}** AC  点数 : **{data['point']}** 点",
      inline=False
    )

  if days <= 7:
    ac_rate_data = {d["atcoder_name"]: d for d in ranking_data}
    graph_buf = create_ac_rate_graph(ac_rate_data, label)
  else:
    all_user_data = {}
    for atcoder_name in user:
      all_user_data[atcoder_name] = await get_progress_data(atcoder_name, days, DB_FILE)
    graph_buf = create_progress_graph(all_user_data)

  if graph_buf is None:
    await channel.send(embed=embed)
    print(f"[auto_period_ranking] Posted [{label}] (no graph)")
    return

  file = discord.File(graph_buf, filename=filename)
  embed.set_image(url=f"attachment://{filename}")
  await channel.send(embed=embed, file=file)
  print(f"[auto_period_ranking] Posted [{label}]")


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

  if ranking_channel_id is None:
    return
  channel = client.get_channel(ranking_channel_id)
  if channel is None:
    return

  now = datetime.datetime.now(JST)
  # (days, label, filename, 投稿するかどうか)
  periods = [
    (7,   "1週間", "ranking_weekly.png",  now.weekday() == 0),
    (30,  "1ヶ月", "ranking_monthly.png", now.day == 1),
    (90,  "3ヶ月", "ranking_3month.png",  now.day == 1 and now.month in (1, 4, 7, 10)),
    (180, "半年",  "ranking_6month.png",  now.day == 1 and now.month in (1, 7)),
    (365, "1年",   "ranking_yearly.png",  now.day == 1 and now.month == 1),
  ]
  for days, label, filename, should_post in periods:
    if should_post:
      try:
        await _post_period_summary(channel, days, label, filename)
      except Exception as e:
        print(f"[auto_period_ranking] Error posting [{label}]: {e}")


## @brief 5分ごとにABCの結果が出たか確認し、出ていたら自動でランキングを投稿するタスク
## @details kenkoooo contests.json から直近の終了済みABCを特定し、
##          AtCoderのresults APIにレーティング更新済みデータが現れたら投稿する。
##          RANKING_CHANNEL_ID が未設定の場合はスキップする。
@tasks.loop(minutes=5)
async def auto_abc_ranking():
  now_str = datetime.datetime.now(JST).strftime('%H:%M:%S.%f')[:-3]
  print(f"[{now_str}][auto_abc_ranking] tick")

  if ranking_channel_id is None:
    print(f"[{now_str}][auto_abc_ranking] RANKING_CHANNEL_ID not set, skipping")
    return

  try:
    contest_number = await get_latest_ended_abc_number()
    if contest_number is None:
      print(f"[{now_str}][auto_abc_ranking] No ended ABC contest found, skipping")
      return

    contest_id = f"abc{contest_number:03d}"
    if is_contest_auto_posted(contest_id, DB_FILE):
      print(f"[{now_str}][auto_abc_ranking] {contest_id} already posted, skipping")
      return

    if not await is_abc_results_ready(contest_number):
      print(f"[{now_str}][auto_abc_ranking] {contest_id} results not ready yet, skipping")
      return

    # 結果確定 → ランキングを投稿
    print(f"[auto_abc_ranking] Results ready for {contest_id}, posting...")
    rated, unrated = await get_abc_standings(contest_number, DB_FILE)

    # 投稿済みとして記録 (参加者なしでも二重チェックを防ぐ)
    mark_contest_auto_posted(contest_id, DB_FILE)

    if not rated and not unrated:
      print(f"[auto_abc_ranking] No registered users participated in {contest_id}")
      return

    channel = client.get_channel(ranking_channel_id)
    if channel is None:
      print(f"[auto_abc_ranking] Channel {ranking_channel_id} not found")
      return

    embed = discord.Embed(
      title=f"🏆 ABC{contest_number:03d} 登録ユーザーランキング",
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
        value=f"Rank: **{d['rank']}** 位　Perf: **{d['performance']}**　Rate: **{rc_str}** ({d['old_rating']} → {d['new_rating']})",
        inline=False
      )
      prev_rank = d["rank"]

    if unrated:
      unrated_lines = [
        f"{d['atcoder_name']}({d['discord_name']})  {d['rank']}位"
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
  await asyncio.sleep(300)  # 起動直後の実行を5分遅らせる


## @brief Bot起動時のイベントハンドラ
## @details DBの初期化とSlashコマンドの同期を行う
@client.event
async def on_ready():
  init_db(DB_FILE)
  await tree.sync()
  daily_update.start()
  auto_abc_ranking.start()
  log_channel = client.get_channel(1486382744153100469)
  discord_logger.set_log_channel(log_channel)
  print("activate the bot  now!!!!")


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
##          discord_userにはDiscordユーザーをメンションで指定する。
## @param interaction Discordのインタラクション
## @param atcoder_name 登録するAtCoderユーザー名
## @param discord_user 登録するDiscordユーザー (メンション選択)
@tree.command(name = "user_resister", description="ユーザーを登録します")
async def user_resister(interaction: discord.Interaction, atcoder_name: str, discord_user: discord.Member):
  await interaction.response.defer()
  try:
    resister_id = interaction.user.id
    discord_name = discord_user.display_name
    discord_id = discord_user.id

    exist_user = get_registered_user(atcoder_name, DB_FILE)
    if exist_user:
      await interaction.followup.send(f"⚠️エラー: {atcoder_name} さんはすでに<@{exist_user[1]}>さんによって登録されています")
      return
    check = await get_latest_rating_nofstring(atcoder_name)
    if "存在しません" in str(check):
      await interaction.followup.send(f"⚠️エラー : {atcoder_name}は存在しません")
      return
    register_user(atcoder_name, discord_name, discord_id, resister_id, DB_FILE)
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


## @brief user_unresister の atcoder_name オートコンプリート (登録済みユーザー一覧)
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
@tree.command(name = "user_unresister", description="登録されているユーザーの登録を解除します")
@app_commands.autocomplete(atcoder_name=registered_atcoder_autocomplete)
async def user_unresister(interaction: discord.Interaction, atcoder_name: str):
  await interaction.response.defer()
  user_id = interaction.user.id
  resister_id = get_resister_id(atcoder_name, DB_FILE)
  if resister_id is None:
    await interaction.followup.send(f"{atcoder_name}さんは登録されていません")
    return
  if user_id == resister_id or user_id == int(admin_id):
    delete_user(atcoder_name, DB_FILE)
    await interaction.followup.send(f"{atcoder_name}さんの登録を解除しました")
  else:
    await interaction.followup.send(f"他人の登録を勝手に消すのはNGだぜbro")


## @brief 登録済みユーザーの一覧とレートをEmbedで表示するコマンド
## @param interaction Discordのインタラクション
@tree.command(name = "user_list", description="登録済みユーザーおよびレートを表示します")
async def user_list(interaction: discord.Interaction):
  user = get_user_dict(DB_FILE)
  if not user:
    await interaction.response.send_message("登録されているユーザーがいません")
    return
  await interaction.response.defer()
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


## @brief AC数を主軸にしたランキングを表示するコマンド
## @param interaction Discordのインタラクション
## @param period 比較期間
@tree.command(name="ac_fight", description="AC数ランキングを表示します")
@app_commands.choices(period=[
  app_commands.Choice(name = "1日",  value = 1),
  app_commands.Choice(name = "1週間", value = 7),
  app_commands.Choice(name = "1ヶ月", value = 30),
  app_commands.Choice(name = "3ヶ月", value = 90),
  app_commands.Choice(name = "半年",  value = 180),
  app_commands.Choice(name = "1年",  value = 365),
])
async def ac_fight(interaction: discord.Interaction, period: app_commands.Choice[int]):
  await interaction.response.defer()
  try:
    user = get_user_dict(DB_FILE)
    day = period.value
    label = period.name
    ranking_data = await make_ranking(user, day, DB_FILE)

    if not ranking_data:
      await interaction.edit_original_response(content="登録されているユーザーがいません")
      return

    embed = discord.Embed(
      title = f"🏆 AC Fight [{label}]🏆",
      color = 0x2ecc71,
      timestamp = interaction.created_at
    )
    for data in ranking_data:
      embed.add_field(
        name = f"{data['figure']}{data['place']}位 : {data['atcoder_name']}({data['discord_name']})",
        value = f"AC数 : **{data['ac']}** AC  点数 : **{data['point']}** 点",
        inline = False
      )

    if day <= 7:
      rate_data = await get_ac_rate_change_data(user, day, DB_FILE)
      graph_buf = create_ac_rate_graph(rate_data, label)
    else:
      all_user_data = {}
      for atcoder_name in user:
        all_user_data[atcoder_name] = await get_progress_data(atcoder_name, day, DB_FILE)
      graph_buf = create_progress_graph(all_user_data)

    if graph_buf is None:
      await interaction.edit_original_response(embed=embed)
      return

    file = discord.File(graph_buf, filename="ac_fight.png")
    embed.set_image(url="attachment://ac_fight.png")
    await interaction.edit_original_response(content=None, embed=embed, attachments=[file])
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


## @brief Botの使い方をEmbedで表示するコマンド
## @param interaction Discordのインタラクション
@tree.command(name="user_guide", description="このBotの使い方を表示します")
async def user_guide(interaction: discord.Interaction):
  embed = discord.Embed(
    title="📖 Bot 使い方ガイド",
    description="AtCoder精進管理Botのコマンド一覧です",
    color=0x3498db,
    timestamp=interaction.created_at
  )
  embed.add_field(
    name="👤 ユーザー管理",
    value=(
      "`/user_resister [atcoder_name] [discord_user]`\n"
      "　AtCoderユーザーをBotに登録します\n\n"
      "`/user_unresister [atcoder_name]`\n"
      "　登録を解除します (登録者本人のみ)\n\n"
      "`/user_list`\n"
      "　登録ユーザーとレートの一覧を表示します"
    ),
    inline=False
  )
  embed.add_field(
    name="📊 精進記録",
    value=(
      "`/syozin [atcoder_name]`\n"
      "　指定ユーザーの今日のAC数・獲得点数・通算AC数を表示します\n\n"
      "`/ac_fight [period]`\n"
      "　AC数ランキングを表示します\n"
      "　期間: 1日 / 1週間(散布図) / 1ヶ月 / 3ヶ月 / 半年 / 1年(レートグラフ)\n\n"
      "`/diligence_growth [period]`\n"
      "　レート変化を主軸にしたランキング＋グラフを表示します\n"
      "　期間: 1日 / 1週間(散布図) / 1ヶ月 / 3ヶ月 / 半年 / 1年(レートグラフ)"
    ),
    inline=False
  )
  embed.add_field(
    name="🏆 コンテスト",
    value=(
      "`/abc_ranking [contest_number]`\n"
      "　指定したABCコンテストの登録ユーザーランキングを表示します\n"
      "　例: `/abc_ranking 450` → ABC450のランキング"
    ),
    inline=False
  )
  embed.set_footer(text="データは毎日0時に自動更新されます")
  await interaction.response.send_message(embed=embed)


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
        value=f"Rank: **{d['rank']}** 位　Perf: **{d['performance']}**　Rate: **{rc_str}** ({d['old_rating']} → {d['new_rating']})",
        inline=False
      )
      prev_rank = d["rank"]

    if unrated:
      unrated_lines = [
        f"{d['atcoder_name']}({d['discord_name']})  {d['rank']}位"
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

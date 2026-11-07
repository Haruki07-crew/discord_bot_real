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
import time
from server import server_thread
import discord_logger

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

admin_id = config.ADMIN_ID
ranking_channel_id = int(config.RANKING_CHANNEL_ID) if config.RANKING_CHANNEL_ID else None
log_channel_id = int(config.LOG_CHANNEL_ID) if config.LOG_CHANNEL_ID else None
DB_FILE = "database.db"


JST = datetime.timezone(datetime.timedelta(hours=9))


# ---- Embed 作成ヘルパー ----
# Discord の Embed はフィールド25個・合計6000文字・フィールド値1024文字が上限で、
# 超えると送信自体が失敗する。登録ユーザーが増えても壊れないように分割して送る。
EMBED_MAX_FIELDS = 25
EMBED_MAX_CHARS = 5500  # 上限6000文字に余裕を持たせる
FIELD_VALUE_MAX = 1024
FIELD_NAME_MAX = 256  # タイトルも同じく256文字


def _truncate(text, limit):
  return text if len(text) <= limit else text[:limit - 1] + "…"


## @brief フィールドのリストを上限に収まるよう複数のEmbedに分割して作成する
## @param fields [(name, value), ...]
## @return [discord.Embed, ...] (fieldsが空でも1つは返す)
def build_embeds(title, color, timestamp, fields, description=None):
  embeds = []
  cur = None
  cur_len = 0
  title = _truncate(title, FIELD_NAME_MAX - 6)  # "(続き)" を付けても256文字以内
  for name, value in fields:
    # discord_name は /user_register で自由入力されるため、長すぎる名前で送信が失敗しないよう切り詰める
    name = _truncate(name, FIELD_NAME_MAX)
    value = _truncate(value, FIELD_VALUE_MAX)
    field_len = len(name) + len(value)
    if cur is None or len(cur.fields) >= EMBED_MAX_FIELDS or cur_len + field_len > EMBED_MAX_CHARS:
      is_first = not embeds
      cur = discord.Embed(
        title=title if is_first else f"{title} (続き)",
        description=description if is_first else None,
        color=color,
        timestamp=timestamp
      )
      embeds.append(cur)
      cur_len = len(cur.title) + len(cur.description or "")
    cur.add_field(name=name, value=value, inline=False)
    cur_len += field_len
  if not embeds:
    embeds.append(discord.Embed(title=title, description=description, color=color, timestamp=timestamp))
  return embeds


## @brief 複数行のテキストを、1フィールドの値が1024文字以内になるよう複数フィールドに分ける
def lines_to_fields(name, lines):
  fields = []
  chunk = []
  chunk_len = 0
  for line in lines:
    if chunk and chunk_len + len(line) + 1 > FIELD_VALUE_MAX:
      fields.append((name if not fields else f"{name} (続き)", "\n".join(chunk)))
      chunk, chunk_len = [], 0
    chunk.append(line[:FIELD_VALUE_MAX])
    chunk_len += len(line) + 1
  if chunk:
    fields.append((name if not fields else f"{name} (続き)", "\n".join(chunk)))
  return fields


## @brief Embedのリストをチャンネルに送る。1通目に添付ファイル(グラフ)を付け、残りは別メッセージで送る
async def send_embeds_to_channel(channel, embeds, file=None, image_name=None):
  if file is not None:
    embeds[0].set_image(url=f"attachment://{image_name}")
    await channel.send(embed=embeds[0], file=file)
  else:
    await channel.send(embed=embeds[0])
  for e in embeds[1:]:
    await channel.send(embed=e)


## @brief Embedのリストでdefer済みインタラクションに応答する。2通目以降はfollowupで送る
async def send_embeds_to_interaction(interaction, embeds, file=None, image_name=None):
  if file is not None:
    embeds[0].set_image(url=f"attachment://{image_name}")
    await interaction.edit_original_response(content=None, embed=embeds[0], attachments=[file])
  else:
    await interaction.edit_original_response(content=None, embed=embeds[0])
  for e in embeds[1:]:
    await interaction.followup.send(embed=e)


## @brief 送信処理を最大 attempts 回まで再試行する (一時的なDiscord障害で自動投稿が失われないように)
## @param make_coro 呼ぶたびに新しい送信コルーチンを返す関数 (discord.File は1度しか送れないので毎回作り直す)
async def send_with_retry(make_coro, attempts=3, delay=60):
  for i in range(attempts):
    try:
      return await make_coro()
    except Exception as e:
      print(f"[send_with_retry] attempt {i + 1}/{attempts} failed: {e}")
      if i == attempts - 1:
        raise
      await asyncio.sleep(delay)


def format_rate_change(rc):
  return f"+{rc}" if rc >= 0 else str(rc)


## @brief Diligence & Growth ランキングのフィールドを作る
## @param point_first True なら点数を先に表示する (diligence_growth_point 用)
def growth_fields(ranking_data, point_first=False):
  fields = []
  for data in ranking_data:
    rc_str = format_rate_change(data["rate_change"])
    if point_first:
      value = f"Rate: **{rc_str}**　点数 : **{data['point']}** 点  AC数 : **{data['ac']}** AC"
    else:
      value = f"Rate: **{rc_str}**　AC数 : **{data['ac']}** AC  点数 : **{data['point']}** 点"
    fields.append((f"{data['figure']}{data['place']}位 : {data['atcoder_name']}({data['discord_name']})", value))
  return fields


## @brief ABCランキング (rated + unrated) のフィールドを作る
def abc_ranking_fields(rated, unrated):
  fields = []
  prev_rank = -1
  place = 0
  for i, d in enumerate(rated):
    if d["rank"] != prev_rank:
      place = i + 1
    figure = "🥇" if place == 1 else "🥈" if place == 2 else "🥉" if place == 3 else "👤"
    rc_str = format_rate_change(d.get("rate_change", 0))
    fields.append((
      f"{figure} {place}位 : {d['atcoder_name']}({d['discord_name']})",
      f"Rank: **{d['rank']}** 位　AC: **{d.get('ac_count', 0)}** 問　Perf: **{d['performance']}**　Rate: **{rc_str}** ({d['old_rating']} → {d['new_rating']})"
    ))
    prev_rank = d["rank"]
  if unrated:
    unrated_lines = [
      f"{d['atcoder_name']}({d['discord_name']})  {d['rank']}位  AC: {d.get('ac_count', 0)}問"
      for d in unrated
    ]
    fields.extend(lines_to_fields("📋 Unrated参加者", unrated_lines))
  return fields


## @brief 毎日1時(JST)に全登録ユーザーのデータをAPIから更新するバックグラウンドタスク

@tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=JST))
async def daily_update():
  print("[daily_update] Starting daily data update...")
  users = list(get_user_dict(DB_FILE).keys())
  await refresh_users_data(users, DB_FILE, interval=1.5)
  print("[daily_update] Daily update complete")


## @brief 毎週月曜0:15(JST)に週次ランキングと累積グラフを投稿するタスク
## @details 直近1週間のAC数・点数・レート変化をテキストで表示し、
##          12週サイクルの累積折れ線グラフ(AC数版・点数版)を投稿する。
WEEKLY_POST_TIME = datetime.time(hour=0, minute=15, tzinfo=JST)
_weekly_lock = asyncio.Lock()
_catch_up_task = None

@tasks.loop(time=WEEKLY_POST_TIME)
async def weekly_ranking_post():
  # 定時実行と起動時の取りこぼし投稿が同時に走っても二重投稿しないようにする
  async with _weekly_lock:
    await _post_weekly_ranking()


## @brief 月曜0:15に再起動などでBotが止まっていても、その日のうちに起動すれば週次投稿を行う
## @details tasks.loop(time=...) は止まっていた間の実行を後から行わないため、そのままだと1週分が丸ごと抜ける。
##          投稿済みかどうかは weekly_last_posted で判定するので、投稿済みなら何もしない。
async def catch_up_weekly_ranking_post():
  now = datetime.datetime.now(JST)
  if now.weekday() != 0 or now.time() < WEEKLY_POST_TIME.replace(tzinfo=None):
    return
  if get_weekly_last_posted(DB_FILE) == now.strftime("%Y-%m-%d"):
    return
  print("[weekly_ranking_post] Missed scheduled post, posting now")
  async with _weekly_lock:
    await _post_weekly_ranking()


async def _post_weekly_ranking():
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

  today_str = now.strftime("%Y-%m-%d")
  if get_weekly_last_posted(DB_FILE) == today_str:
    print("[weekly_ranking_post] Already posted today, skipping")
    return

  try:
    user = get_user_dict(DB_FILE)
    if not user:
      print("[weekly_ranking_post] No registered users, skipping")
      return

    # daily_update(1:00)より前に走るので、先にキャッシュを更新する
    # (しないと日曜日のACがどの週にも集計されない)
    await refresh_users_data(list(user), DB_FILE)

    # 先週分のデータを取得 (先週月曜0:00 〜 今週月曜0:00)。
    # 終わりを今日の0:00で区切り、0:00〜0:15のACが2週に二重計上されないようにする
    week_end_unix = int(datetime.datetime(now.year, now.month, now.day, tzinfo=JST).timestamp())
    ranking_data = await make_growth_ranking(user, 7, DB_FILE, end_unix=week_end_unix)
    if not ranking_data:
      print("[weekly_ranking_post] No ranking data, skipping")
      return

    # 週次サイクルを進める (同じ日に二重に進めないよう、進めた直後に記録する)
    cycle_id, week_number = advance_weekly_cycle(DB_FILE)
    set_weekly_last_posted(today_str, DB_FILE)
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
    embeds = build_embeds(
      f"🏆 Diligence & Growth [{week_number}週目]", 0xFFD700, now, growth_fields(ranking_data)
    )

    # 累積グラフ用データを取得
    # 登録解除されたユーザーの線がグラフに残らないよう、現在の登録者だけに絞る
    snapshots = {name: weeks for name, weeks in get_weekly_snapshots(cycle_id, DB_FILE).items() if name in user}

    # AC数版グラフ
    graph_ac = create_weekly_graph(snapshots, week_number, x_axis="ac")
    # 点数版グラフ
    graph_point = create_weekly_graph(snapshots, week_number, x_axis="point")

    def make_ac_post():
      file_ac = None
      if graph_ac:
        graph_ac.seek(0)
        file_ac = discord.File(graph_ac, filename="weekly_ac.png")
      return send_embeds_to_channel(channel, embeds, file_ac, "weekly_ac.png")
    await send_with_retry(make_ac_post)

    # 点数版は別embedで投稿
    if graph_point:
      embed_point = discord.Embed(
        title=f"📊 累積点数 vs レート変化 [{week_number}週目]",
        color=0x3498db,
        timestamp=now
      )
      embed_point.set_image(url="attachment://weekly_point.png")
      def make_point_post():
        graph_point.seek(0)
        return channel.send(embed=embed_point, file=discord.File(graph_point, filename="weekly_point.png"))
      await send_with_retry(make_point_post)

    print(f"[weekly_ranking_post] Posted week {week_number} of cycle {cycle_id}")

  except Exception as e:
    print(f"[weekly_ranking_post] Error: {e}")

@weekly_ranking_post.before_loop
async def before_weekly_ranking_post():
  await client.wait_until_ready()


## @brief prev_contest が未設定なら、直近に終了したABC番号をAPIから取得して初期化する
## @details 固定値で初期化すると、古いABCのランキングが1時間に1つずつ連投されてしまうため、
##          API取得に失敗した場合は初期化せず None を返し、次回の auto_abc_ranking で再試行する。
## @return 現在の prev_contest (取得できなければ None)
async def ensure_prev_contest():
  prev = get_prev_contest(DB_FILE)
  if prev is not None:
    return prev
  try:
    latest = await get_latest_ended_abc_number(with_end_time=True)
  except Exception as e:
    print(f"[ensure_prev_contest] Error: {e}")
    return None
  if latest is None:
    return None
  number, end_unix = latest
  # 終了から24時間以内ならまだレート未確定の可能性があるので、そのABCも自動投稿の対象に含める
  if time.time() - end_unix < 24 * 60 * 60:
    number -= 1
  set_prev_contest(number, DB_FILE)
  print(f"[ensure_prev_contest] prev_contest initialized to {number} (from API)")
  return number


## @brief 1時間ごとに prev_contest+1 のABC結果を確認し、確定したら自動でランキングを投稿するタスク
## @details DBに保存した prev_contest の次の番号のコンテスト結果を AtCoder API で確認し、
##          レーティング更新済みデータが現れたら投稿して prev_contest を更新する。
##          RANKING_CHANNEL_ID が未設定の場合はスキップする。
ABC_POST_MAX_FAILURES = 3
_abc_post_failures = {}  # contest_number -> 送信失敗回数

@tasks.loop(hours=1)
async def auto_abc_ranking():
  now_str = datetime.datetime.now(JST).strftime('%H:%M:%S.%f')[:-3]
  print(f"[{now_str}][auto_abc_ranking] tick")

  if ranking_channel_id is None:
    print(f"[{now_str}][auto_abc_ranking] RANKING_CHANNEL_ID not set, skipping")
    return

  try:
    prev = await ensure_prev_contest()
    if prev is None:
      print(f"[{now_str}][auto_abc_ranking] prev_contest not set (API unavailable), retry next tick")
      return

    next_number = prev + 1
    contest_id = f"abc{next_number:03d}"

    result = await fetch_abc_standings_if_ready(next_number, DB_FILE)
    if result is None:
      print(f"[{now_str}][auto_abc_ranking] {contest_id} results not ready yet, skipping")
      return

    rated, unrated = result
    print(f"[auto_abc_ranking] Results ready for {contest_id}, posting...")

    if not rated and not unrated:
      # 参加者なし → 投稿するものが無いので次のコンテストへ進める
      set_prev_contest(next_number, DB_FILE)
      print(f"[auto_abc_ranking] No registered users participated in {contest_id}")
      return

    channel = client.get_channel(ranking_channel_id)
    if channel is None:
      # prev_contest は進めず、次回のtickで再試行する
      print(f"[auto_abc_ranking] Channel {ranking_channel_id} not found")
      return

    embeds = build_embeds(
      f"🏆 ABC{next_number:03d} 登録ユーザーランキング",
      0xFFD700,
      datetime.datetime.now(JST),
      abc_ranking_fields(rated, unrated),
      description="コンテスト結果が確定しました！"
    )
    try:
      await send_embeds_to_channel(channel, embeds)
    except Exception as e:
      # 送信に失敗したら次のtickで再試行する。ただし失敗し続けると以降のABCが全て止まるので、
      # ABC_POST_MAX_FAILURES 回失敗したら諦めて次のコンテストへ進める
      _abc_post_failures[next_number] = _abc_post_failures.get(next_number, 0) + 1
      print(f"[auto_abc_ranking] Failed to post {contest_id} ({_abc_post_failures[next_number]}/{ABC_POST_MAX_FAILURES}): {e}")
      if _abc_post_failures[next_number] >= ABC_POST_MAX_FAILURES:
        set_prev_contest(next_number, DB_FILE)
        print(f"[auto_abc_ranking] Gave up posting {contest_id}")
      return
    # 投稿に成功してから prev_contest を進める (送信失敗時に投稿が失われないように)
    set_prev_contest(next_number, DB_FILE)
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
  if log_channel_id is not None:
    discord_logger.set_log_channel(client.get_channel(log_channel_id))
  await ensure_prev_contest()
  # 全員分のデータ更新を伴うので、on_ready を止めないよう別タスクで実行する
  global _catch_up_task
  if _catch_up_task is None or _catch_up_task.done():
    _catch_up_task = asyncio.create_task(catch_up_weekly_ranking_post())
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
    # 登録済みユーザーならキャッシュを差分更新してから集計する (しないと今日のACが反映されない)
    registered = {name.lower(): name for name in get_user_dict(DB_FILE)}
    if atcoder_name.lower() in registered:
      atcoder_name = registered[atcoder_name.lower()]  # キャッシュは登録時の表記で保存されている
      await refresh_users_data([atcoder_name], DB_FILE)
    elif await atcoder_user_exists(atcoder_name) is False:
      # 未登録ユーザーは kenkoooo から直接取るが、存在しない名前だと 0 AC と表示されてしまうので先に確認する
      await interaction.edit_original_response(content=f"⚠️エラー : {atcoder_name}は存在しません")
      return
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
    exists = await atcoder_user_exists(atcoder_name)
    if exists is False:
      await interaction.followup.send(f"⚠️エラー : {atcoder_name}は存在しません")
      return
    if exists is None:
      await interaction.followup.send(f"⚠️エラー : AtCoderに接続できませんでした。時間をおいて再度お試しください")
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
  if user_id == register_id or str(user_id) == str(admin_id):
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
    fields = []
    for atcoder_name, discord_name in user.items():
      latest_rating = get_latest_rating_from_db(atcoder_name, DB_FILE)
      atcoder_url = f"https://atcoder.jp/users/{atcoder_name}"
      fields.append((
        f"{get_rate_heart(latest_rating)} {discord_name}",
        f"Atcoder_ID: [{atcoder_name}]({atcoder_url})\n Rating: **{latest_rating}**"
      ))
    embeds = build_embeds("登録ユーザー", 0x3498db, interaction.created_at, fields)
    await send_embeds_to_interaction(interaction, embeds)
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
    await refresh_users_data(list(user), DB_FILE)
    ranking_data = await make_growth_ranking(user, day, DB_FILE)

    if not ranking_data:
      await interaction.edit_original_response(content="登録されているユーザーがいません")
      return

    embeds = build_embeds(
      f"🏆 Diligence & Growth [{label}]🏆", 0xFFD700, interaction.created_at, growth_fields(ranking_data)
    )

    if day <= 7:
      ac_rate_data = {d["atcoder_name"]: d for d in ranking_data}
      graph_buf = create_ac_rate_graph(ac_rate_data, label)
    else:
      all_user_data = {}
      for atcoder_name in user:
        all_user_data[atcoder_name] = await get_progress_data(atcoder_name, day, DB_FILE)
      graph_buf = create_progress_graph(all_user_data)

    file = discord.File(graph_buf, filename="ac_rate.png") if graph_buf is not None else None
    await send_embeds_to_interaction(interaction, embeds, file, "ac_rate.png")
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
    await refresh_users_data(list(user), DB_FILE)
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

    embeds = build_embeds(
      f"🏆 Diligence & Growth [点数] [{label}]🏆", 0x2ecc71, interaction.created_at,
      growth_fields(sorted_data, point_first=True)
    )

    if day <= 7:
      # 散布図 (横軸: 点数, 縦軸: レート変化)
      point_rate_data = {d["atcoder_name"]: {"ac": d["point"], "rate_change": d["rate_change"]} for d in sorted_data}
      graph_buf = create_ac_rate_graph(point_rate_data, label, x_label="点数")
    else:
      all_user_data = {}
      for atcoder_name in user:
        all_user_data[atcoder_name] = await get_progress_data(atcoder_name, day, DB_FILE, x_axis="point")
      graph_buf = create_progress_graph(all_user_data, x_label="点数")

    file = discord.File(graph_buf, filename="point_rate.png") if graph_buf is not None else None
    await send_embeds_to_interaction(interaction, embeds, file, "point_rate.png")
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

    user_stats = []
    for atcoder_name, discord_name in user.items():
      ac_count = await get_ac_count(atcoder_name, DB_FILE)
      streak = get_ac_streak(atcoder_name, DB_FILE)
      user_stats.append((atcoder_name, discord_name, ac_count, streak))

    user_stats.sort(key=lambda x: (x[3], x[2]), reverse=True)

    fields = []
    for atcoder_name, discord_name, ac_count, streak in user_stats:
      streak_text = f"{streak}日連続" if streak > 0 else "0日"
      fields.append((
        f"{discord_name} ({atcoder_name})",
        f"総AC数: **{ac_count}** AC　連続AC: **{streak_text}**"
      ))

    embeds = build_embeds("全員の精進状況", 0x3498db, interaction.created_at, fields)
    await send_embeds_to_interaction(interaction, embeds)
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

    embeds = build_embeds(
      f"🏆 ABC{contest_number:03d} 登録ユーザーランキング", 0xFFD700, interaction.created_at,
      abc_ranking_fields(rated, unrated)
    )
    await send_embeds_to_interaction(interaction, embeds)
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
  command_name = interaction.command.name if interaction.command else "不明"
  print(f"コマンド'{command_name}'でエラー発生: {error}")
  try:
    if interaction.response.is_done():
      await interaction.followup.send(content=error_message, ephemeral=True)
    else:
      await interaction.response.send_message(error_message, ephemeral=True)
    if admin_id:
      admin = await client.fetch_user(int(admin_id))
      await admin.send(f"エラー\n: '/{command_name}'\n実行者: {interaction.user}\nエラー内容{error}")
  except Exception as e:
    print(f"エラー発生: {e}")

server_thread()
client.run(config.DISCORD_TOKEN)

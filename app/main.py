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
import io
import os
import re
import time
from server import server_thread
import server
import discord_logger
import alerts
import atcoder.background_sync as sync_module

# 特別な許可が必要な Intents (メッセージ本文・メンバー・プレゼンス) は使わない。
# スラッシュコマンドだけで動くので不要で、Bot が100サーバーを超えたときの審査も不要になる。
intents = discord.Intents.default()
# discord_name は /user_register で自由入力されるため、"@everyone" などを入れると返信で全員に通知が飛ぶ。
# @everyone/@here とロールへのメンションは無効にする (admin への <@id> メンションは残す)
client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True))
tree = app_commands.CommandTree(client)

admin_id = config.ADMIN_ID
ranking_channel_id = int(config.RANKING_CHANNEL_ID) if config.RANKING_CHANNEL_ID else None
log_channel_id = int(config.LOG_CHANNEL_ID) if config.LOG_CHANNEL_ID else None
# DBの保存先。Docker などでデータを残すには、永続化したい場所を DB_PATH で指定する (未指定なら起動ディレクトリの database.db)
DB_FILE = config.DB_PATH
if os.path.dirname(DB_FILE):
  os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)


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
def build_embeds(title, color, timestamp, fields, description=None, footer=None):
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
  if footer:
    embeds[-1].set_footer(text=_truncate(footer, 2048))
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


# ---- ページ送り・上位N人表示 ----
# 登録者が数百〜1000人になると、全員分を Embed で送ると数十通の連投になって読めない。
# コマンドの返信は1ページ10人でボタンでページを送り、自動投稿は上位10人 + 全順位のテキストファイルにする。
PAGE_SIZE = 10
PAGE_VIEW_TIMEOUT_SEC = 15 * 60


## @brief fields を1ページ PAGE_SIZE 個ずつの Embed に分ける (ページ番号はフッターに入れる)
def build_pages(title, color, timestamp, fields, description=None, footer=None, per_page=PAGE_SIZE):
  chunks = [fields[i:i + per_page] for i in range(0, len(fields), per_page)] or [[]]
  pages = []
  for chunk in chunks:
    # 1ページが文字数上限を超える場合は build_embeds がさらに分ける
    pages.extend(build_embeds(title, color, timestamp, chunk, description=description))
  for i, page in enumerate(pages):
    page.title = title  # 「(続き)」ではなくページ番号で示す
    text = f"{i + 1}/{len(pages)} ページ" if len(pages) > 1 else ""
    if footer:
      text = f"{text}　{footer}" if text else footer
    if text:
      page.set_footer(text=_truncate(text, 2048))
  return pages


## @brief ◀ ▶ ボタンでページを切り替える View
class PageView(discord.ui.View):
  def __init__(self, pages):
    super().__init__(timeout=PAGE_VIEW_TIMEOUT_SEC)
    self.pages = pages
    self.index = 0
    self.message = None
    self._refresh_buttons()

  def _refresh_buttons(self):
    self.prev_button.disabled = self.index == 0
    self.next_button.disabled = self.index >= len(self.pages) - 1

  async def _show(self, interaction):
    self._refresh_buttons()
    # ボタンが押されたメッセージを覚えておく (on_timeout で Bot 自身の権限で編集するため)
    if getattr(interaction, "message", None) is not None:
      self.message = interaction.message
    await interaction.response.edit_message(embed=self.pages[self.index], view=self)

  @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
  async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    self.index = max(0, self.index - 1)
    await self._show(interaction)

  @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
  async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    self.index = min(len(self.pages) - 1, self.index + 1)
    await self._show(interaction)

  async def on_timeout(self):
    # 期限が切れたらボタンを押せないようにする (押しても反応しないボタンを残さない)。
    # スラッシュコマンドの応答トークンは15分で切れるので、interaction 経由ではなく
    # チャンネルのメッセージとして Bot 自身の権限で編集する。
    for item in self.children:
      item.disabled = True
    msg = self.message
    if msg is None:
      return
    try:
      await msg.channel.get_partial_message(msg.id).edit(view=self)
    except Exception as e:
      print(f"[PageView] failed to disable buttons: {e}")


## @brief ページ付きで defer 済みインタラクションに応答する (2ページ以上ならボタンを付ける)
async def send_pages_to_interaction(interaction, pages, file=None, image_name=None):
  kwargs = {"content": None, "embed": pages[0]}
  if file is not None:
    # 全ページに同じ画像を設定する (1ページ目だけだと、ページを切り替えたとき画像が Embed の外に出る)
    for page in pages:
      page.set_image(url=f"attachment://{image_name}")
    kwargs["attachments"] = [file]
  view = None
  if len(pages) > 1:
    view = PageView(pages)
    kwargs["view"] = view
  message = await interaction.edit_original_response(**kwargs)
  if view is not None:
    view.message = message


def _plain(text):
  return text.replace("**", "")


## @brief 全順位をテキストファイルにする (自動投稿で上位以外の人も自分の順位を確認できるように)
def ranking_text_file(title, fields, filename):
  lines = [title, ""] + [f"{_plain(name)}\n    {_plain(value)}" for name, value in fields]
  return discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=filename)


## @brief 自動投稿用: 上位 PAGE_SIZE 人だけを載せ、残りの人数を書き添える
def top_fields(fields, note="全員の順位は添付ファイルを見てください"):
  if len(fields) <= PAGE_SIZE:
    return fields
  return fields[:PAGE_SIZE] + [(f"…ほか {len(fields) - PAGE_SIZE} 人", note)]


## @brief 実行した人の順位を「あなたの順位」として返す (登録していなければ None)
def my_rank_text(interaction, ranking, total):
  mine = get_registered_by_discord_id(interaction.user.id, DB_FILE)
  if not mine:
    return None
  for d in ranking:
    if d["atcoder_name"].lower() == mine.lower():
      return f"あなた ({mine}) の順位: **{d['place']}位** / {total}人"
  return None


## @brief グラフに描くユーザー: 上位 PAGE_SIZE 人 + 実行した本人 (全員描くと線や名前が重なって読めない)
def graph_targets(interaction, ranking):
  names = [d["atcoder_name"] for d in ranking[:PAGE_SIZE]]
  mine = get_registered_by_discord_id(interaction.user.id, DB_FILE) if interaction is not None else None
  if mine:
    for d in ranking[PAGE_SIZE:]:
      if d["atcoder_name"].lower() == mine.lower():
        names.append(d["atcoder_name"])
  return names


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


## @brief AtCoderのユーザー名として正しい形式か (英数字と_で3〜16文字)
## @details "x/../.." や "name?a" のような文字列がURLに入ると、別のページが200を返して
##          存在確認をすり抜け、不正な名前や既存ユーザーの二重登録が起きるため、APIを叩く前に弾く
ATCODER_NAME_RE = re.compile(r"[A-Za-z0-9_]{3,16}")

def is_valid_atcoder_name(name):
  return ATCODER_NAME_RE.fullmatch(name) is not None


USER_ERROR_MESSAGE = "⚠️ エラーが発生しました。管理者に自動で通知したので、少し時間をおいてから試してください。"


## @brief コマンドで起きた例外を記録し、管理者に DM で知らせ、実行した人にはエラーを返す
## @param use_followup True なら edit_original_response ではなく followup で返す (途中経過を送っているコマンド用)
async def report_command_error(interaction, command_name, error, user_message=USER_ERROR_MESSAGE, use_followup=False):
  summary = alerts.record_error(f"/{command_name}", error)
  await alerts.notify_admin(
    f"cmd-{command_name}", f"/{command_name} でエラー\n実行者: {interaction.user}\n{summary}", cooldown=10 * 60
  )
  try:
    if use_followup:
      await interaction.followup.send(content=user_message)
    else:
      await interaction.edit_original_response(content=user_message, embed=None)
  except Exception as e:
    print(f"[report_command_error] failed to reply: {e}")


## @brief 管理者 (ADMIN_ID) かどうか
def is_admin(user_id):
  return admin_id is not None and str(user_id) == str(admin_id)


def format_rate_change(rc):
  return f"+{rc}" if rc >= 0 else str(rc)


## @brief Diligence & Growth ランキングのフィールドを作る
## @param point_first True なら点数を先に表示する (diligence_growth_point 用)
def growth_fields(ranking_data, point_first=False):
  fields = []
  for data in ranking_data:
    rc_str = format_rate_change(data["rate_change"])
    new_ac = data.get("new_ac")
    ac_str = f"総合AC : **{data['ac']}**" + (f" (新規 **{new_ac}**)" if new_ac is not None else "")
    if point_first:
      value = f"Rate: **{rc_str}**　点数 : **{data['point']}** 点  {ac_str}"
    else:
      value = f"Rate: **{rc_str}**　{ac_str}  点数 : **{data['point']}** 点"
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


## @brief 登録ユーザーのデータを1人ずつ同期し続けるバックグラウンドタスク
## @details 1秒ごとに、提出・コンテスト履歴それぞれで一番古いユーザーを1人ずつ更新する
##          (提出は5分ごと、コンテスト履歴は24時間ごとが目安)。API のアクセス間隔は http_client が守る。
##          コマンドはこの同期結果 (DB) を読むだけなので、登録人数が増えてもすぐに応答できる。
SYNC_ALERT_STREAK = 10  # 連続でこの回数失敗したら管理者に知らせる (失敗のたびに60秒止まるので約10分)
SYNC_KIND_LABELS = {"submission": "提出 (kenkoooo)", "contest": "コンテスト履歴 (atcoder.jp)"}
_sync_alerted = set()

@tasks.loop(seconds=1)
async def background_sync():
  try:
    await sync_step(DB_FILE)
  except Exception as e:
    # 例外で tasks.loop が止まると同期が永久に止まるので、必ず捕まえる
    summary = alerts.record_error("background_sync", e)
    await alerts.notify_admin("background_sync-exception", f"バックグラウンド同期で例外\n{summary}")
  await check_sync_alerts()


## @brief 同期が続けて失敗していれば管理者に知らせ、直ったら復旧を知らせる
async def check_sync_alerts():
  for kind, label in SYNC_KIND_LABELS.items():
    streak = sync_module.fail_streak[kind]
    if streak >= SYNC_ALERT_STREAK and kind not in _sync_alerted:
      _sync_alerted.add(kind)
      await alerts.notify_admin(f"sync-{kind}", f"{label} の同期が {streak} 回続けて失敗しています。API が落ちている可能性があります", cooldown=6 * 60 * 60)
    elif streak == 0 and kind in _sync_alerted:
      _sync_alerted.discard(kind)
      await alerts.notify_admin(f"sync-{kind}-recovered", f"✅ {label} の同期が復旧しました", cooldown=0)


## @brief /health 用: Discord に接続していて、同期が続けて失敗していなければ正常
def bot_health():
  connected = client.is_ready() and not client.is_closed()
  streaks = dict(sync_module.fail_streak)
  oldest = get_oldest_submission_sync(DB_FILE)
  detail = {
    "discord_connected": connected,
    "sync_fail_streak": streaks,
    "oldest_submission_sync_age_sec": int(time.time() - oldest) if oldest else None,
    "uptime_sec": int(time.time() - alerts.started_at),
  }
  ok = connected and all(v < SYNC_ALERT_STREAK for v in streaks.values())
  return ok, detail

@background_sync.before_loop
async def before_background_sync():
  await client.wait_until_ready()


## @brief 「提出データは何分前のものか」をフッター用の文字列で返す
def sync_footer():
  oldest = get_oldest_submission_sync(DB_FILE)
  if oldest is None:
    return None
  if oldest == 0:
    return "一部のユーザーはデータを同期中です (登録直後は反映まで少しかかります)"
  minutes = max(0, int((time.time() - oldest) // 60))
  return f"提出データは最大{minutes}分前のものです"


## @brief 毎日1時(JST)にDBをバックアップするタスク (データの更新は background_sync が常時行う)
@tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=JST))
async def daily_update():
  # 1日1回 DB をバックアップする (14日分を残す)。壊れたり消えたりしても前日の状態に戻せるように
  try:
    path = backup_database(DB_FILE)
    print(f"[daily_update] Backup saved: {path}")
  except Exception as e:
    print(f"[daily_update] Backup failed: {e}")


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

    # 日曜深夜の提出が同期されていない可能性があるので、集計前に全員分を更新する
    # (投稿は自動タスクなので、人数に比例して時間がかかっても応答期限の問題はない)
    # レートは終了から遅れて確定するため、コンテスト履歴はキャッシュを使わず取り直す
    # (取り直さないと、日曜深夜に確定したレート変化がどの週にも入らない)
    await refresh_users_data(list(user), DB_FILE, force_contest=True)
    user = get_user_dict(DB_FILE)  # 更新中に登録解除されたユーザーを除く
    if not user:
      return

    # 先週分のデータを取得 (先週月曜0:00 〜 今週月曜0:00)。
    # 終わりを今日の0:00で区切り、0:00〜0:15のACが2週に二重計上されないようにする
    week_end_unix = int(datetime.datetime(now.year, now.month, now.day, tzinfo=JST).timestamp())
    # 期間は「今日を含めて N 日分」なので、今日の0:00で切って先週の7日分にするには 8 を渡す
    ranking_data = await make_growth_ranking(user, 8, DB_FILE, end_unix=week_end_unix)
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

    # テキスト embed (今週の結果)。上位10人だけ載せ、全員の順位はテキストファイルで添付する
    weekly_title = f"🏆 Diligence & Growth [{week_number}週目]"
    weekly_fields = growth_fields(ranking_data)
    embeds = build_embeds(weekly_title, 0xFFD700, now, top_fields(weekly_fields))

    # 累積グラフ用データを取得
    # 登録解除されたユーザーの線がグラフに残らないよう、現在の登録者だけに絞る
    snapshots = {name: weeks for name, weeks in get_weekly_snapshots(cycle_id, DB_FILE).items() if name in user}
    # 線が多すぎると読めないので、累積レート変化 (同点なら累積AC) の上位10人に絞る
    top_names = sorted(
      snapshots, key=lambda n: (sum(w[3] for w in snapshots[n]), sum(w[1] for w in snapshots[n])), reverse=True
    )[:PAGE_SIZE]
    snapshots = {n: snapshots[n] for n in top_names}

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

    if len(weekly_fields) > PAGE_SIZE:
      await send_with_retry(lambda: channel.send(
        content="📄 全員の順位", file=ranking_text_file(weekly_title, weekly_fields, f"weekly_{week_number}.txt")
      ))

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
    summary = alerts.record_error("weekly_ranking_post", e)
    await alerts.notify_admin("weekly_ranking_post", f"週次ランキングの投稿に失敗しました\n{summary}")

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

    abc_title = f"🏆 ABC{next_number:03d} 登録ユーザーランキング"
    abc_fields = abc_ranking_fields(rated, unrated)
    embeds = build_embeds(
      abc_title, 0xFFD700, datetime.datetime.now(JST), top_fields(abc_fields),
      description="コンテスト結果が確定しました！"
    )
    try:
      await send_embeds_to_channel(channel, embeds)
      if len(abc_fields) > PAGE_SIZE:
        try:
          await channel.send(content="📄 全員の順位", file=ranking_text_file(abc_title, abc_fields, f"{contest_id}.txt"))
        except Exception as e:
          # ランキング本体は送れているので、添付だけの失敗では再投稿しない
          print(f"[auto_abc_ranking] Failed to send full ranking file: {e}")
    except Exception as e:
      # 送信に失敗したら次のtickで再試行する。ただし失敗し続けると以降のABCが全て止まるので、
      # ABC_POST_MAX_FAILURES 回失敗したら諦めて次のコンテストへ進める
      _abc_post_failures[next_number] = _abc_post_failures.get(next_number, 0) + 1
      summary = alerts.record_error("auto_abc_ranking", e)
      await alerts.notify_admin(
        f"abc-post-{next_number}",
        f"{contest_id} のランキング投稿に失敗しました ({_abc_post_failures[next_number]}/{ABC_POST_MAX_FAILURES})\n{summary}",
      )
      if _abc_post_failures[next_number] >= ABC_POST_MAX_FAILURES:
        set_prev_contest(next_number, DB_FILE)
        print(f"[auto_abc_ranking] Gave up posting {contest_id}")
      return
    # 投稿に成功してから prev_contest を進める (送信失敗時に投稿が失われないように)
    set_prev_contest(next_number, DB_FILE)
    print(f"[auto_abc_ranking] Posted {contest_id} ranking")
    # レートが確定したので、参加者のコンテスト履歴を次の同期で優先して取り直す (/diligence_growth に反映するため)
    request_contest_resync([d["atcoder_name"] for d in rated + unrated], DB_FILE)

  except Exception as e:
    summary = alerts.record_error("auto_abc_ranking", e)
    await alerts.notify_admin("auto_abc_ranking", f"ABC自動投稿の処理で例外\n{summary}", cooldown=6 * 60 * 60)

@auto_abc_ranking.before_loop
async def before_auto_abc_ranking():
  await client.wait_until_ready()


_commands_synced = False

## @brief Bot起動時のイベントハンドラ
## @details DBの初期化とSlashコマンドの同期を行う
@client.event
async def on_ready():
  global _commands_synced
  init_db(DB_FILE)
  alerts.setup(client, admin_id)
  server.health_provider = bot_health
  # 自動投稿タスクを先に起動する (sync が失敗しても自動投稿は止めない)
  if not daily_update.is_running():
    daily_update.start()
  if not background_sync.is_running():
    background_sync.start()
  if not weekly_ranking_post.is_running():
    weekly_ranking_post.start()
  if not auto_abc_ranking.is_running():
    auto_abc_ranking.start()
  # on_ready は再接続のたびに呼ばれる。sync はレート制限が厳しいので起動後1回だけ行う
  if not _commands_synced:
    try:
      await tree.sync()
      _commands_synced = True
    except Exception as e:
      print(f"[on_ready] tree.sync failed (retry on next reconnect): {e}")
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

BULK_GROUPS = {"test": TEST_USERS, "other_kosen": OTHER_KOSEN_USERS}


## @brief 事前に定義したメンバーをまとめて登録する管理者用コマンド
## @details 以前はメッセージ本文 (「テスト用にユーザー登録」など) で動かしていたが、
##          本文を読むには特別な権限 (Message Content Intent) が必要になるため、スラッシュコマンドにした。
@tree.command(name="bulk_register", description="(管理者用) main.py に定義したメンバーをまとめて登録します")
@app_commands.choices(group=[
  app_commands.Choice(name="テスト用 (TEST_USERS)", value="test"),
  app_commands.Choice(name="他高専テスト用 (OTHER_KOSEN_USERS)", value="other_kosen"),
])
async def bulk_register(interaction: discord.Interaction, group: app_commands.Choice[str]):
  if not is_admin(interaction.user.id):
    await interaction.response.send_message("このコマンドは管理者だけが使えます", ephemeral=True)
    return
  if _registration_lock.locked():
    await interaction.response.send_message("⚠️ 現在登録処理中です。完了するまでお待ちください。", ephemeral=True)
    return
  await interaction.response.defer()
  user_dict = BULK_GROUPS[group.value]
  async with _registration_lock:
    total = len(user_dict)
    await interaction.followup.send(f"ユーザー登録を開始します（{total}人）...")
    done = 0
    for atcoder_name, discord_name in user_dict.items():
      try:
        if get_registered_user(atcoder_name, DB_FILE):
          await interaction.followup.send(f"⏭️ {atcoder_name}({discord_name}) は既に登録済みです")
          continue
        register_user(atcoder_name, discord_name, interaction.user.id, interaction.user.id, DB_FILE)
        await initial_fetch_user_data(atcoder_name, DB_FILE)
        done += 1
        await interaction.followup.send(f"✅ {atcoder_name}({discord_name}) を登録しました ({done}/{total})")
      except Exception as e:
        alerts.record_error("/bulk_register", e)
        await interaction.followup.send(f"⚠️ {atcoder_name} の登録に失敗: {type(e).__name__}")
    await interaction.followup.send("✅ ユーザー登録がすべて完了しました！")


## @brief ユーザーの精進記録をEmbedで返すコマンド
## @details 今日および通算のAC数・獲得点数を表示する
## @param interaction Discordのインタラクション
## @param atcoder_name 対象のAtCoderユーザー名
@tree.command(name = "syozin", description="Atcoderの精進記録を返します")
async def rating_command(interaction: discord.Interaction, atcoder_name: str):
  await interaction.response.defer()
  try:
    # 登録済みユーザーならキャッシュを差分更新してから集計する (しないと今日のACが反映されない)
    if not is_valid_atcoder_name(atcoder_name):
      await interaction.edit_original_response(content=f"⚠️エラー : {atcoder_name}は存在しません")
      return
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
    new_ac = f"**{ac_daily[2]}** AC" if ac_daily[2] is not None else "— (登録ユーザーのみ)"
    embed.add_field(name="今日の総合AC", value=f"**{ac_daily[0]}** AC", inline=True)
    embed.add_field(name="今日の新規AC", value=new_ac, inline=True)
    embed.add_field(name="今日の獲得点数", value=f"**{round(ac_daily[1])}** 点", inline=True)
    embed.add_field(name="これまでに解いた問題数", value=f"**{ac_sum}** 問", inline=False)
    embed.description = "総合AC: 同じ問題でも別の日に解き直せば数える (同じ日は1回)\n新規AC: 初めて解いた問題の数"
    if ac_daily[0] == 0:
      embed.set_footer(text = "精進せんかい雑魚bro\n")
    else:
      embed.set_footer(text = "偉すぎるぜbro\n")
    await interaction.edit_original_response(embed = embed)
  except Exception as e:
    await report_command_error(interaction, "syozin", e)


## @brief 登録できるか確認する。できなければ理由のメッセージ、できれば None を返す (await を含まない)
def registration_problem(interaction, atcoder_name):
  if not is_admin(interaction.user.id):
    mine = get_registered_by_discord_id(interaction.user.id, DB_FILE)
    if mine:
      return (f"⚠️エラー : すでに {mine} を登録しています。登録できるのは1人1アカウントです。"
              f"変更するときは `/user_unregister` で解除してから登録し直してください")
  exist_user = get_registered_user(atcoder_name, DB_FILE)
  if exist_user:
    return f"⚠️エラー: {atcoder_name} さんはすでに<@{exist_user[1]}>さんによって登録されています"
  return None


## @brief 登録を確定して提出履歴を取り込む (/user_register と /user_verify の共通処理)
async def complete_registration(interaction, atcoder_name, discord_name):
  # 直前に確認し直す。ここから INSERT までは await を挟まないので、同時に実行されても二重登録にならない
  problem = registration_problem(interaction, atcoder_name)
  if problem:
    await interaction.followup.send(problem, allowed_mentions=discord.AllowedMentions.none())
    return
  register_user(atcoder_name, discord_name, interaction.user.id, interaction.user.id, DB_FILE)
  await interaction.followup.send(
    f"{discord_name} さんを {atcoder_name} で登録しました\n"
    f"提出履歴を取得中です...（提出数が多い場合は数分かかります）"
  )
  await initial_fetch_user_data(atcoder_name, DB_FILE)
  await interaction.followup.send(f"✅ {atcoder_name} のデータ取得が完了しました")


## @brief ユーザーをDBに登録するコマンド
## @details AtCoderの存在確認後にDBへ登録する。管理者以外は1人1アカウントまで。
##          REQUIRE_ATCODER_VERIFICATION が有効なら、管理者以外は確認コードを発行して /user_verify を待つ。
## @param atcoder_name 登録するAtCoderユーザー名
## @param discord_name ランキングに表示する名前 (省略時は Discord の表示名)
@tree.command(name = "user_register", description="自分のAtCoderアカウントを登録します")
@app_commands.describe(atcoder_name="AtCoderのユーザー名", discord_name="ランキングに表示する名前 (省略するとDiscordの表示名)")
async def user_register(interaction: discord.Interaction, atcoder_name: str, discord_name: str = None):
  await interaction.response.defer()
  try:
    if not discord_name:
      discord_name = getattr(interaction.user, "display_name", None) or str(interaction.user)
    if not is_valid_atcoder_name(atcoder_name):
      await interaction.followup.send(f"⚠️エラー : {atcoder_name}は存在しません")
      return
    problem = registration_problem(interaction, atcoder_name)
    if problem:
      await interaction.followup.send(problem, allowed_mentions=discord.AllowedMentions.none())
      return
    exists = await atcoder_user_exists(atcoder_name)
    if exists is False:
      await interaction.followup.send(f"⚠️エラー : {atcoder_name}は存在しません")
      return
    if exists is None:
      await interaction.followup.send(f"⚠️エラー : AtCoderに接続できませんでした。時間をおいて再度お試しください")
      return

    if config.REQUIRE_ATCODER_VERIFICATION and not is_admin(interaction.user.id):
      code = create_pending_verification(interaction.user.id, atcoder_name, discord_name, DB_FILE)
      await interaction.followup.send(
        f"🔐 **{atcoder_name}** があなたのアカウントか確認します。\n"
        f"1. AtCoder の [ユーザー情報の変更](https://atcoder.jp/settings) を開き、**所属** に `{code}` を書いて保存する\n"
        f"2. 1時間以内に `/user_verify` を実行する\n"
        f"確認が終わったら、所属は元に戻して大丈夫です。"
      )
      return

    await complete_registration(interaction, atcoder_name, discord_name)
  except Exception as e:
    await report_command_error(interaction, "user_register", e, use_followup=True)


## @brief /user_register で発行した確認コードが AtCoder の所属欄にあるか確かめ、登録を完了するコマンド
@tree.command(name="user_verify", description="AtCoderの所属欄に書いた確認コードを確かめて、登録を完了します")
async def user_verify(interaction: discord.Interaction):
  await interaction.response.defer()
  try:
    pending = get_pending_verification(interaction.user.id, DB_FILE)
    if pending is None:
      await interaction.followup.send("確認待ちの登録がありません (有効期限は1時間です)。`/user_register` からやり直してください")
      return
    atcoder_name, discord_name, code = pending
    found = await affiliation_contains(atcoder_name, code)
    if found is None:
      await interaction.followup.send("⚠️ AtCoderに接続できませんでした。時間をおいて再度お試しください")
      return
    if not found:
      await interaction.followup.send(
        f"⚠️ {atcoder_name} の所属欄に `{code}` が見つかりませんでした。保存したか確認して、もう一度 `/user_verify` を実行してください"
      )
      return
    delete_pending_verification(interaction.user.id, DB_FILE)
    await complete_registration(interaction, atcoder_name, discord_name)
  except Exception as e:
    await report_command_error(interaction, "user_verify", e, use_followup=True)


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
  if user_id == register_id or is_admin(user_id):
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
    rows = sorted(
      ((name, discord_name, get_latest_rating_from_db(name, DB_FILE)) for name, discord_name in user.items()),
      key=lambda r: r[2], reverse=True,
    )
    fields = [
      (f"{get_rate_heart(rating)} {discord_name}",
       f"Atcoder_ID: [{name}](https://atcoder.jp/users/{name})\n Rating: **{rating}**")
      for name, discord_name, rating in rows
    ]
    pages = build_pages(f"登録ユーザー ({len(fields)}人)", 0x3498db, interaction.created_at, fields)
    await send_pages_to_interaction(interaction, pages)
  except Exception as e:
    await report_command_error(interaction, "user_list", e)


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

    pages = build_pages(
      f"🏆 Diligence & Growth [{label}]🏆", 0xFFD700, interaction.created_at, growth_fields(ranking_data),
      description=my_rank_text(interaction, ranking_data, len(ranking_data)), footer=sync_footer()
    )

    targets = graph_targets(interaction, ranking_data)
    if day <= 7:
      ac_rate_data = {d["atcoder_name"]: d for d in ranking_data if d["atcoder_name"] in targets}
      graph_buf = create_ac_rate_graph(ac_rate_data, label)
    else:
      all_user_data = {}
      for atcoder_name in targets:
        all_user_data[atcoder_name] = await get_progress_data(atcoder_name, day, DB_FILE)
      graph_buf = create_progress_graph(all_user_data)

    file = discord.File(graph_buf, filename="ac_rate.png") if graph_buf is not None else None
    await send_pages_to_interaction(interaction, pages, file, "ac_rate.png")
  except Exception as e:
    await report_command_error(interaction, "diligence_growth", e)


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

    pages = build_pages(
      f"🏆 Diligence & Growth [点数] [{label}]🏆", 0x2ecc71, interaction.created_at,
      growth_fields(sorted_data, point_first=True),
      description=my_rank_text(interaction, sorted_data, len(sorted_data)), footer=sync_footer()
    )

    targets = graph_targets(interaction, sorted_data)
    if day <= 7:
      # 散布図 (横軸: 点数, 縦軸: レート変化)
      point_rate_data = {d["atcoder_name"]: {"ac": d["point"], "rate_change": d["rate_change"]} for d in sorted_data if d["atcoder_name"] in targets}
      graph_buf = create_ac_rate_graph(point_rate_data, label, x_label="点数")
    else:
      all_user_data = {}
      for atcoder_name in targets:
        all_user_data[atcoder_name] = await get_progress_data(atcoder_name, day, DB_FILE, x_axis="point")
      graph_buf = create_progress_graph(all_user_data, x_label="点数")

    file = discord.File(graph_buf, filename="point_rate.png") if graph_buf is not None else None
    await send_pages_to_interaction(interaction, pages, file, "point_rate.png")
  except Exception as e:
    await report_command_error(interaction, "diligence_growth_point", e)


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
        f"解いた問題数: **{ac_count}** 問　連続AC: **{streak_text}**"
      ))

    pages = build_pages(f"全員の精進状況 ({len(fields)}人)", 0x3498db, interaction.created_at, fields, footer=sync_footer())
    await send_pages_to_interaction(interaction, pages)
  except Exception as e:
    await report_command_error(interaction, "everyone_state", e)


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

    pages = build_pages(
      f"🏆 ABC{contest_number:03d} 登録ユーザーランキング", 0xFFD700, interaction.created_at,
      abc_ranking_fields(rated, unrated)
    )
    await send_pages_to_interaction(interaction, pages)
  except Exception as e:
    await report_command_error(
      interaction, "abc_ranking", e,
      user_message=f"⚠️ エラーが発生しました。ABC{contest_number:03d} は存在しないか、まだ終了していない可能性があります。"
    )


## @brief Slashコマンドのエラーをキャッチしてadminに通知するハンドラ
## @param interaction Discordのインタラクション
## @param error 発生したAppCommandError
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
  # 各コマンドの try/except で捕まえきれなかったエラー (引数の変換失敗など)
  command_name = interaction.command.name if interaction.command else "不明"
  summary = alerts.record_error(f"/{command_name}", error)
  await alerts.notify_admin(f"cmd-{command_name}", f"/{command_name} でエラー\n実行者: {interaction.user}\n{summary}", cooldown=10 * 60)
  try:
    if interaction.response.is_done():
      await interaction.followup.send(content=USER_ERROR_MESSAGE, ephemeral=True)
    else:
      await interaction.response.send_message(USER_ERROR_MESSAGE, ephemeral=True)
  except Exception as e:
    print(f"[on_app_command_error] failed to reply: {e}")


## @brief Bot の状態を表示する管理者用コマンド (本人にだけ見える)
@tree.command(name="bot_status", description="(管理者用) Botの同期状況と直近のエラーを表示します")
async def bot_status(interaction: discord.Interaction):
  if not is_admin(interaction.user.id):
    await interaction.response.send_message("このコマンドは管理者だけが使えます", ephemeral=True)
    return
  ok, detail = bot_health()
  users = get_user_dict(DB_FILE)
  age = detail["oldest_submission_sync_age_sec"]
  uptime_h = detail["uptime_sec"] / 3600
  lines = [
    f"状態: {'✅ 正常' if ok else '⚠️ 異常あり'}",
    f"Discord: {'接続中' if detail['discord_connected'] else '切断'}　応答速度: {client.latency * 1000:.0f}ms",
    f"登録ユーザー: {len(users)}人",
    f"提出データの古さ (最大): {age // 60 if age is not None else '-'}分",
    "同期の連続失敗: " + "、".join(f"{SYNC_KIND_LABELS[k]} {v}回" for k, v in detail["sync_fail_streak"].items()),
    f"起動してから: {uptime_h:.1f}時間",
  ]
  if alerts.recent_errors:
    lines.append("\n直近のエラー:")
    for t, where, summary in list(alerts.recent_errors)[-5:]:
      when = datetime.datetime.fromtimestamp(t, JST).strftime("%m/%d %H:%M")
      lines.append(f"・{when} {where}: {summary[:150]}")
  else:
    lines.append("\n直近のエラー: なし")
  embed = discord.Embed(title="🩺 Bot の状態", description=_truncate("\n".join(lines), 4000), color=0x2ecc71 if ok else 0xe74c3c)
  await interaction.response.send_message(embed=embed, ephemeral=True)

server_thread()
client.run(config.DISCORD_TOKEN)

---
name: add-command
description: Discord のスラッシュコマンドを新しく追加する、または既存のコマンドを変更するときの型と注意点。app/main.py にコマンドを書くときに使う。
---

# スラッシュコマンドの追加

## 型

```python
## @brief 何をするコマンドか (1行)
## @param interaction Discordのインタラクション
@ranking_group.command(name="command_name", description="コマンドの説明 (日本語、100文字以内)")
async def command_name(interaction: discord.Interaction, atcoder_name: str):
  await interaction.response.defer()          # 3秒以内に応答しないと失敗するので最初に defer
  try:
    if not is_valid_atcoder_name(atcoder_name):  # ユーザー入力を URL に入れる前に必ず検査
      await interaction.edit_original_response(content=f"⚠️エラー : {atcoder_name}は存在しません")
      return
    user = get_user_dict(DB_FILE)
    if not user:
      await interaction.edit_original_response(content="登録されているユーザーがいません")
      return

    fields = [(f"{discord_name} ({name})", f"値: **{...}**") for name, discord_name in user.items()]
    pages = build_pages("タイトル", 0x3498db, interaction.created_at, fields)   # 1ページ10人
    await send_pages_to_interaction(interaction, pages)          # 2ページ以上なら ◀ ▶ ボタンが付く
  except Exception as e:
    await report_command_error(interaction, "command_name", e)   # 記録 + 管理者に DM + 実行者にエラー表示
```

## チェックリスト

- **グループ**
  - コマンドは `user_group` / `ranking_group` / `syozin_group` / `notify_group` / `admin_group` のどれかに入れる (`@tree.command` で一番上に増やさない)
  - 1グループ25個までが Discord の上限。`/help` の一覧はグループから自動で作られる
  - エラー報告の名前は `report_command_error(interaction, "ranking command_name", e)` のようにグループ名から書く

- **Embed**
  - `discord.Embed` に直接 `add_field` しない。人数分の一覧は `build_pages()` でページに分ける(1000人いても1通で済む)
  - 自動投稿(ボタンが使えない)は `top_fields()` で上位10人に絞り、全員分は `ranking_text_file()` で添付する
  - 複数行のテキストは `lines_to_fields()` でフィールドに分ける
  - グラフは `graph_targets()` で上位10人と本人に絞る
- **画像**
  - `discord.File` は1度しか送れない。再送するときは BytesIO を `seek(0)` してから作り直す
- **期間**
  - 期間を扱うときは `get_period_start_unix(day)` を使う。「今日を含めて day 日分」で統一している
- **ユーザー名**
  - AtCoder のユーザー名は大文字と小文字を区別しない。DB は `COLLATE NOCASE` で検索する
- **外部API**
  - 外部APIを叩くときは、同じホストに1秒に1回まで
  - 登録人数に比例して時間がかかる処理は、15分の応答期限に注意する。人数が増えても終わる設計にする
- **権限**
  - 管理者だけに許す操作は `is_admin(interaction.user.id)` で確認する
- **ドキュメントとテスト**
  - README.md の「使い方」にコマンドを追記する
  - `tests/test_offline.py` にテストを足す。`support.FakeInteraction` で `command_name.callback(it, ...)` を呼ぶ
- **反映**
  - コマンド一覧は Bot の起動時に1回だけ同期される(`tree.sync`)。反映には再起動が必要

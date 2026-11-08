---
name: add-command
description: Discord のスラッシュコマンドを新しく追加する、または既存のコマンドを変更するときの型と注意点。app/main.py にコマンドを書くときに使う。
---

# スラッシュコマンドの追加

## 型

```python
## @brief 何をするコマンドか (1行)
## @param interaction Discordのインタラクション
@tree.command(name="command_name", description="コマンドの説明 (日本語、100文字以内)")
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
    embeds = build_embeds("タイトル", 0x3498db, interaction.created_at, fields)
    await send_embeds_to_interaction(interaction, embeds)        # 2通目以降は followup で送られる
  except Exception as e:
    print(e)
    await interaction.edit_original_response(content=f"⚠️ エラーが発生しました。お手数ですが(<@{admin_id}>)までご連絡ください。")
```

## チェックリスト

- **Embed**
  - `discord.Embed` に直接 `add_field` しない。`build_embeds()` を使う。登録者が26人を超えると Discord の上限で送信できなくなるため
  - 複数行のテキストは `lines_to_fields()` でフィールドに分ける
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
  - 管理者だけに許す操作は `str(interaction.user.id) == str(admin_id)` で確認する
- **ドキュメントとテスト**
  - README.md の「使い方」にコマンドを追記する
  - `tests/test_offline.py` にテストを足す。`support.FakeInteraction` で `command_name.callback(it, ...)` を呼ぶ
- **反映**
  - コマンド一覧は Bot の起動時に1回だけ同期される(`tree.sync`)。反映には再起動が必要

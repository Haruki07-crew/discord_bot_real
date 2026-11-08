---
name: ship
description: 変更をブランチ→テスト→PR→マージの手順で本番に出す。main への push は本番デプロイになるので、コードを変更して反映するときは必ずこの手順を使う。
---

# 変更を本番に出す

main ブランチは本番環境に自動でデプロイされる。直接 push せず、次の順で進める。

1. **ブランチを切る**
   `git checkout main && git pull --ff-only && git checkout -b <種類>/<短い説明>`
   - 種類は `fix/`、`feat/`、`docs/`、`chore/` のどれか
2. **テストを通す**
   - `python -m unittest discover -s tests -v` がすべて成功すること
   - 振る舞いを変えたら、`tests/test_offline.py` にテストを足す。足すのはネットワークに出ないテスト
   - 外部APIの仕様に依存する変更は、実際に1回だけAPIを叩いて確認する(1秒に1回まで)。確認した仕様は docs/atcoder-api.md に書く
3. **ドキュメントを合わせる**
   - コマンドや挙動が変わったら README.md を直す
   - 内部の処理の流れが変わったら docs/development.md を直す
4. **コミットする**
   - メッセージは日本語。1行目に「何をどう直したか」、本文に「なぜ」を書く
   - `.env` と `database.db` が含まれていないことを `git status` で確認する
5. **push して PR を作る**
   - `git push -u origin <branch>`
   - `gh pr create --base main` で PR を作る。本文には「修正内容」と「確認したこと」を書き、確認していないことは確認していないと明記する
6. **マージする**
   - ユーザーからマージを任されている場合は、`gh pr merge <branch> --merge` でマージする
   - そうでない場合は、PR の URL を伝えて判断を仰ぐ
   - マージ後は `git checkout main && git pull --ff-only` で手元を最新にする

## 注意

- マージすると Bot が再起動する。月曜 0:15 前後(週次投稿)は避ける。
- DB のテーブルを変える変更は、既存の DB で起動しても壊れないようにする(`CREATE TABLE IF NOT EXISTS` や、列の追加を試して既にあれば無視する形)。

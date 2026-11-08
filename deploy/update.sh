#!/usr/bin/env bash
# main ブランチに新しいコミットがあれば取り込んで Bot を作り直す。
# systemd タイマー (deploy/atcoder-bot-update.timer) から5分ごとに実行される。
set -euo pipefail
cd "$(dirname "$0")/.."

git fetch --quiet origin main
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ]; then
  exit 0  # 変更なし
fi

echo "[update] $(git rev-parse --short HEAD) -> $(git rev-parse --short origin/main)"
git merge --ff-only --quiet origin/main
docker compose up -d --build
docker image prune -f >/dev/null   # 古いイメージで容量を圧迫しないように
echo "[update] done"

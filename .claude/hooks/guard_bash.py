#!/usr/bin/env python3
"""PreToolUse hook: 本番に影響する危険な Bash コマンドを止める。

- Bot の直接起動 (本番トークンだと本番と二重に動き、自動投稿が二重になる)
- main ブランチへの直接 push (main = 本番デプロイ。PR を経由する)
- .env / database.db を git に追加すること
"""
import json
import re
import sys

data = json.load(sys.stdin)
cmd = (data.get("tool_input") or {}).get("command", "")

rules = [
  (r"\bpython[0-9.]*\s+(\S*/)?main\.py\b",
   "Bot を直接起動しようとしています。本番トークンだと本番と二重に動きます。"
   "動作確認は `python -m unittest discover -s tests` で行ってください。"),
  (r"\bgit\b[^;&|]*\bpush\b[^;&|]*(\s|:)main(\s|$)",
   "main への直接 push は本番デプロイになります。ブランチを切って PR からマージしてください (/ship)。"),
  (r"\bgit\b[^;&|]*\badd\b[^;&|]*(\.env\b|database\.db)",
   ".env や database.db は git に追加しないでください (トークン・本番データが含まれます)。"),
]
for pattern, message in rules:
  if re.search(pattern, cmd):
    print(message, file=sys.stderr)
    sys.exit(2)

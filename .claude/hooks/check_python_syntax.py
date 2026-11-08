#!/usr/bin/env python3
"""PostToolUse hook: 編集した .py ファイルの構文エラーをその場で Claude に返す。"""
import json
import py_compile
import sys

data = json.load(sys.stdin)
path = (data.get("tool_input") or {}).get("file_path", "")
if not path.endswith(".py"):
  sys.exit(0)
try:
  py_compile.compile(path, doraise=True)
except py_compile.PyCompileError as e:
  print(f"構文エラー: {e.msg}", file=sys.stderr)
  sys.exit(2)
except FileNotFoundError:
  pass

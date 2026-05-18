#!/usr/bin/env bash
# PostToolUse hook: Edit/Write 后,对 .json 文件做合法性校验
# 校验失败不阻断(退出 0),仅 stderr 报告让 AI 看到
# 主要目标:settings.json / package.json / tsconfig.json 这类配置文件被改坏立刻发现
set -u

input=$(cat)
file_path=$(printf '%s' "$input" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"file_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')

# 只处理 .json 与 .jsonl(jsonl 按行校验)
case "$file_path" in
  *.json) mode="json" ;;
  *.jsonl) mode="jsonl" ;;
  *) exit 0 ;;
esac

# 文件不存在放行(可能是被删除)
[ -f "$file_path" ] || exit 0

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

if [ "$mode" = "json" ]; then
  err=$(python3 -c "
import json, sys
try:
    with open('$file_path', 'r', encoding='utf-8') as f:
        json.load(f)
except json.JSONDecodeError as e:
    print(f'JSON 解析错误: line {e.lineno} col {e.colno}: {e.msg}', file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f'读文件失败: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1)
  rc=$?
else
  # jsonl:每行单独 parse
  err=$(python3 -c "
import json, sys
bad = []
with open('$file_path', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            bad.append(f'line {i}: {e.msg}')
        if len(bad) >= 5:
            bad.append('... (仅显示前 5 行错误)')
            break
if bad:
    print('JSONL 解析错误:', file=sys.stderr)
    for b in bad:
        print('  ' + b, file=sys.stderr)
    sys.exit(1)
" 2>&1)
  rc=$?
fi

if [ $rc -ne 0 ]; then
  echo "[json_lint] $file_path 不是合法的 ${mode^^}:" >&2
  echo "$err" >&2
  echo "[json_lint] 修复 JSON 语法或回退本次改动" >&2
fi

exit 0

#!/usr/bin/env bash
# PostToolUse hook: RAG collection drift 提醒
# 覆盖 embedding model、chunk 参数、向量 schema 等 RAG 数据契约改动。
# 触发:被改文件含相关关键字,且 git diff(未提交+最近一次 commit) 显示改动行有这些关键字
# 输出:stderr 提醒,不阻断(改动可能合法,如重命名/重构)

set -u

input=$(cat)

file_path=$(printf '%s' "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''), end='')
except Exception:
    pass
" 2>/dev/null)

[ -z "$file_path" ] && exit 0
[ ! -f "$file_path" ] && exit 0

case "$file_path" in
  *.py|*.toml|*.env|*.env.example|*settings*) ;;
  *) exit 0 ;;
esac

# git 仓库内
project_root=$(cd "$(dirname "$file_path")" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
[ -z "$project_root" ] && exit 0

case "$project_root" in
  "$HOME/.claude"*) exit 0 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CHECK_SCRIPT="$SCRIPT_DIR/../scripts/check_rag_drift.py"
[ -f "$CHECK_SCRIPT" ] || exit 0

python3 "$CHECK_SCRIPT" --file "$file_path" >/dev/null || true
exit 0

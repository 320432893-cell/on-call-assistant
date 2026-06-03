#!/usr/bin/env bash
# PostToolUse hook: read dirty code after edits and print non-blocking static feedback.
# It never mutates files. Ruff is invoked with --no-fix on the touched file only.
set -u

input=$(cat)

file_path=$(printf '%s' "$input" | python3 -c "
import json
import sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''), end='')
except Exception:
    pass
" 2>/dev/null)

[ -z "$file_path" ] && exit 0
[ ! -f "$file_path" ] && exit 0

case "$file_path" in
  "$HOME/.claude"*) exit 0 ;;
esac

project_root=$(cd "$(dirname "$file_path")" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$project_root" ]; then
  project_root=$(cd "$(dirname "$file_path")" 2>/dev/null && pwd -P) || exit 0
fi

echo "[dirty_static] 写后提示:请和用户确认本次改动采用的范式/思想(例如局部修补、分层重构、数据契约优先、测试先行、兼容性优先),再继续扩大改动。" >&2

dirty_diff="$project_root/.ai-config/tools/dirty_diff_review.py"
if [ -f "$dirty_diff" ]; then
  python3 "$dirty_diff" --file "$file_path" >/dev/null || true
fi

case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac

tmp_err=$(mktemp)
trap 'rm -f "$tmp_err"' EXIT

if ! python3 -m py_compile "$file_path" 2>"$tmp_err"; then
  echo "[dirty_static] py_compile failed for $file_path:" >&2
  sed -n '1,40p' "$tmp_err" >&2
fi

ruff_bin=""
if [ -x "$project_root/.venv/bin/ruff" ]; then
  ruff_bin="$project_root/.venv/bin/ruff"
elif command -v ruff >/dev/null 2>&1; then
  ruff_bin=$(command -v ruff)
fi

if [ -n "$ruff_bin" ]; then
  ruff_out=$("$ruff_bin" check --no-fix --force-exclude "$file_path" 2>&1)
  ruff_rc=$?
  if [ "$ruff_rc" -ne 0 ] && [ -n "$ruff_out" ]; then
    echo "[dirty_static] ruff dirty-file findings for $file_path (--no-fix):" >&2
    printf '%s\n' "$ruff_out" | sed -n '1,80p' >&2
  fi
fi

exit 0

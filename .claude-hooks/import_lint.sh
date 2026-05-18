#!/usr/bin/env bash
# PostToolUse hook (Edit/Write/MultiEdit): 改 .py 后跑 import-linter
# 检查分层架构契约(DIP / 子系统封装)是否被破坏
# 退出码 0 总放行,违规写 stderr 让 AI 看到
#
# 设计:
# - 只在项目根有 .importlinter 配置时跑
# - 用项目 venv 的 lint-imports(它需要 import 项目代码解析依赖图)
# - TTL 5 分钟去重避免每次 Edit 都重跑(lint 全图很慢)

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

# 只对 .py 文件触发
case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac

# 找项目根 (向上找 .importlinter)
find_lint_config() {
  local dir
  dir=$(dirname "$file_path")
  dir=$(cd "$dir" 2>/dev/null && pwd) || return 1
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -f "$dir/.importlinter" ]; then
      echo "$dir"
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

project_root=$(find_lint_config)
[ -z "$project_root" ] && exit 0

# 找 lint-imports 可执行文件:优先项目 venv,回退全局
linter=""
for cand in "$project_root/.venv/bin/lint-imports" "$HOME/.local/bin/lint-imports"; do
  if [ -x "$cand" ]; then
    linter="$cand"
    break
  fi
done
[ -z "$linter" ] && exit 0

# TTL 去重: 同项目 5 分钟内不重复跑
proj_hash=$(echo -n "$project_root" | md5sum | cut -c1-8)
done_marker="/tmp/import_lint_${proj_hash}.done"
if [ -f "$done_marker" ]; then
  if [ "$(find "$done_marker" -mmin +5 2>/dev/null | wc -l)" -eq 0 ]; then
    exit 0
  fi
  rm -f "$done_marker"
fi

# 跑
cd "$project_root" || exit 0
output=$("$linter" --config .importlinter 2>&1)
rc=$?

# 标记已跑(不论结果,避免连续 Edit 刷屏)
touch "$done_marker" 2>/dev/null

if [ $rc -ne 0 ]; then
  echo "" >&2
  echo "[import_lint] 项目: $project_root" >&2
  echo "[import_lint] 分层架构契约被破坏(对应 code.md § 1 DIP 规则):" >&2
  echo "" >&2
  # 跳过 logo,只输出违规信息
  echo "$output" | sed -n '/Contracts$/,$p' | head -40 >&2
  echo "" >&2
  echo "[import_lint] 修复方式: 调整 import 路径,或在 .importlinter 添加 ignore_imports(需在 PR 说明豁免理由)" >&2
fi

exit 0

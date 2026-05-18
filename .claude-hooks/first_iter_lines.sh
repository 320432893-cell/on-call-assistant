#!/usr/bin/env bash
# PostToolUse hook (Write): 首迭代行数提醒
# 对应 flow_new_project.md § 5 — 探索型新项目第一个迭代 ≤ 50 行
#
# 触发条件:
#   - 新项目状态(git 仓库内 commit 数 ≤ 3,或无 .git)
#   - 单次 Write 写入文件超 50 行
#   - 只在新建文件(此前 git ls-files 没追踪过)时触发
#
# 不阻断,stderr 提示 + 建议拆分

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

# 只看代码文件
case "$file_path" in
  *.py|*.vue|*.ts|*.js|*.tsx|*.jsx|*.go|*.rs) ;;
  *) exit 0 ;;
esac

# 文件行数
lines=$(wc -l < "$file_path" 2>/dev/null || echo 0)
[ "$lines" -le 50 ] && exit 0

# 找项目根
find_project_root() {
  local dir
  dir=$(dirname "$file_path")
  dir=$(cd "$dir" 2>/dev/null && pwd) || return 1
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -d "$dir/.git" ] || [ -f "$dir/pyproject.toml" ]; then
      echo "$dir"
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

project_root=$(find_project_root)
[ -z "$project_root" ] && exit 0

case "$project_root" in
  "$HOME/.claude"*) exit 0 ;;
esac

# 判定"新项目":commit 数 ≤ 3,或文件不在 git 追踪范围里
if [ -d "$project_root/.git" ]; then
  commit_count=$(cd "$project_root" && git rev-list --count HEAD 2>/dev/null || echo 0)
  if [ "$commit_count" -gt 3 ]; then
    # 老项目,只在"新建文件"时提醒
    rel_path="${file_path#$project_root/}"
    if cd "$project_root" && git ls-files --error-unmatch "$rel_path" >/dev/null 2>&1; then
      # 已 tracked,不是新文件,跳过
      exit 0
    fi
  fi
fi

# skip 标记(用户嫌烦可关掉)
[ -f "$project_root/.first_iter_skip" ] && exit 0

echo "" >&2
echo "[first_iter_lines] 新文件 ${file_path##*/} 写入 $lines 行" >&2
echo "[first_iter_lines] flow_new_project.md § 5:探索型新项目第一个迭代建议 ≤ 50 行" >&2
echo "[first_iter_lines] 处置:① 先验证最小切片再扩展 ② 或在汇报段说明为何首迭代超规模" >&2
echo "[first_iter_lines] (老项目可忽略;长期关闭:touch $project_root/.first_iter_skip)" >&2

exit 0

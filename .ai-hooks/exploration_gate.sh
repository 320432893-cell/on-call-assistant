#!/usr/bin/env bash
# PreToolUse hook on Edit/Write: 探索型任务未确认前禁止写业务代码
# 对应 rule_governance/governance.index.md 的探索到写入门禁
# 退出码 2 = 阻断
#
# 为什么不能用 ruff/basedpyright: 这是 AI 行为规则(流程纪律),不是代码质量
#
# 状态流转:
#   rule_activator 检测到探索型 → /tmp/ai_task_exploratory_<project_hash>
#   用户回复含确认词 → rule_activator 写 /tmp/ai_task_confirmed_<project_hash>
#   本 hook: exploratory 存在 + confirmed 不存在 → exit 2
set -u

input=$(cat)

# 只拦 Edit / Write（代码输出动作）
tool_name=$(printf '%s' "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_name', ''), end='')
except Exception:
    pass
" 2>/dev/null)

case "${tool_name:-}" in
  Edit|Write|MultiEdit) ;;
  *) exit 0 ;;
esac

file_path=$(printf '%s' "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''), end='')
except Exception:
    pass
" 2>/dev/null)

[ -z "$file_path" ] && exit 0

# 排除规则文件/配置文件本身的编辑（讨论阶段改规则不应被拦）
case "$file_path" in
  *.md|*.json|*.yaml|*.yml|*.toml|*.ini|*.sh|*.txt) exit 0 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
TASK_HASH=$(printf '%s' "$PROJECT_ROOT" | md5sum | cut -c1-12)
EXPLORATORY_MARKER="/tmp/ai_task_exploratory_${TASK_HASH}"
CONFIRMED_MARKER="/tmp/ai_task_confirmed_${TASK_HASH}"

# 用项目级标记（rule_activator 写的）
# 如果没有 exploratory 标记 → 不是探索型,放行
[ -f "$EXPLORATORY_MARKER" ] || exit 0

# 有 exploratory 标记,检查是否已确认
if [ -f "$CONFIRMED_MARKER" ]; then
  exit 0
fi

# 探索型 + 未确认 → 阻断
echo "[exploration_gate] 阻断: 探索型任务,用户尚未确认方案" >&2
echo "[exploration_gate] 按 rule_governance/governance.index.md:" >&2
echo "  1. 先输出 ≥2 个方案对比" >&2
echo "  2. 等用户确认后再写代码" >&2
echo "  3. 用户确认词: 确认/做/开始/选A/选B/就这样" >&2
exit 2

#!/usr/bin/env bash
# PreToolUse hook on Edit/Write: 探索型任务未确认前禁止输出代码
# 对应 governance.md § 9.2 T1 机械强制
# 退出码 2 = 阻断
#
# 为什么不能用 ruff/mypy: 这是 AI 行为规则(流程纪律),不是代码质量
#
# 状态流转:
#   rule_activator 检测到探索型 → /tmp/claude_task_exploratory_<hash>
#   用户回复含确认词 → rule_activator 写 /tmp/claude_task_confirmed_<hash>
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

# 找项目根 hash（与 rule_activator 一致）
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

# 用 session 级标记（rule_activator 写的）
# 如果没有 exploratory 标记 → 不是探索型,放行
ls /tmp/claude_task_exploratory_* >/dev/null 2>&1 || exit 0

# 有 exploratory 标记,检查是否已确认
if ls /tmp/claude_task_confirmed_* >/dev/null 2>&1; then
  exit 0
fi

# 探索型 + 未确认 → 阻断
echo "[exploration_gate] 阻断: 探索型任务,用户尚未确认方案" >&2
echo "[exploration_gate] 按 governance.md § 9.2:" >&2
echo "  1. 先输出 ≥2 个方案对比" >&2
echo "  2. 等用户确认后再写代码" >&2
echo "  3. 用户确认词: 确认/做/开始/选A/选B/就这样" >&2
exit 2

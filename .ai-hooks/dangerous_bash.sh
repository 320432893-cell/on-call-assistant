#!/usr/bin/env bash
# PreToolUse hook on Bash: 拦截高风险不可逆命令
# 退出码 2 = 阻断,把理由写到 stderr 让 AI 看到
# 对应 workflow.md § 5 回滚方案 + § 6.4 不确定即问
set -u

input=$(cat)
cmd=$(printf '%s' "$input" | grep -oE '"command"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"(.*)"$/\1/' | sed 's/\\"/"/g; s/\\\\/\\/g')

block() {
  echo "[dangerous_bash] 阻断: $1" >&2
  echo "[dangerous_bash] 命令: $cmd" >&2
  echo "[dangerous_bash] 按 workflow.md § 5,执行不可逆操作前必须输出回滚方案并取得用户确认" >&2
  exit 2
}

# 用 grep -E 做模式匹配（注意要避免误伤 ls / cat 等）
# 1. rm -rf / rm -fr （含递归强删）
echo "$cmd" | grep -Eq '(^|[[:space:];|&])rm[[:space:]]+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)([[:space:]]|$)' && block "rm -rf 递归强删"

# 2. git reset --hard
echo "$cmd" | grep -Eq 'git[[:space:]]+reset[[:space:]]+(--hard|--keep)' && block "git reset --hard 会丢弃未提交改动"

# 3. git push --force / -f （仅限跟在 push 后)
echo "$cmd" | grep -Eq 'git[[:space:]]+push[[:space:]]+(.*[[:space:]])?(--force|--force-with-lease|-f([[:space:]]|$))' && block "git push --force 会覆盖远程历史"

# 4. git clean -fd / -fdx
echo "$cmd" | grep -Eq 'git[[:space:]]+clean[[:space:]]+(-[a-zA-Z]*[fd][a-zA-Z]*)' && block "git clean -fd 会删除未跟踪文件"

# 5. rm 删除 .git 目录
echo "$cmd" | grep -Eq '(^|[[:space:];|&])rm[[:space:]].*\.git(/|[[:space:]]|$)' && block "删除 .git 目录会丢失整个版本历史"

exit 0

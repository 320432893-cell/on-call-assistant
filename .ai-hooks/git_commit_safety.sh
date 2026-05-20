#!/usr/bin/env bash
# PreToolUse hook on Bash: git commit 前体检暂存区
# 对应 workflow.md § 6.1 开局体检 + 4.3.1 git 仓库治理
# 退出码 2 = 阻断
set -u

input=$(cat)
cmd=$(printf '%s' "$input" | grep -oE '"command"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"(.*)"$/\1/' | sed 's/\\"/"/g; s/\\\\/\\/g')

# 只拦 git commit (排除 git commit --help 等查询命令)
echo "$cmd" | grep -Eq 'git[[:space:]]+commit($|[[:space:]])' || exit 0
echo "$cmd" | grep -Eq 'git[[:space:]]+commit[[:space:]]+(--help|-h)($|[[:space:]])' && exit 0

# 检查暂存区是否含敏感文件
staged=$(git diff --cached --name-only 2>/dev/null) || exit 0  # 不是 git 仓库放行

if [ -z "$staged" ]; then
  exit 0  # 暂存区空,让 git 自己报错
fi

risky=""
while IFS= read -r f; do
  # 先放行公开占位符文件 (.env.example / .env.template / .env.sample)
  # 以及 detect-secrets 基线文件(.secrets.baseline 不含实际密钥)
  case "$f" in
    *.env.example|*.env.template|*.env.sample|.env.example|.env.template|.env.sample)
      continue
      ;;
    .secrets.baseline|*/.secrets.baseline)
      continue
      ;;
  esac
  case "$f" in
    *.env|.env|.env.*|*/.env|*.key|*.pem|*credentials*|*secret*|*token*)
      risky="$risky\n  - $f (密钥/敏感)"
      ;;
    *.venv/*|venv/*|*/__pycache__/*|*.pyc)
      risky="$risky\n  - $f (虚拟环境/缓存)"
      ;;
    *node_modules/*|*/.idea/*|*/.vscode/*)
      risky="$risky\n  - $f (依赖/IDE 元数据)"
      ;;
  esac
  # 大文件检测 (>5MB)
  if [ -f "$f" ]; then
    size=$(wc -c < "$f" 2>/dev/null || echo 0)
    if [ "$size" -gt 5242880 ]; then
      risky="$risky\n  - $f ($(($size / 1048576))MB 大文件)"
    fi
  fi
done <<< "$staged"

if [ -n "$risky" ]; then
  echo "[git_commit_safety] 阻断: 暂存区含风险文件:" >&2
  printf "$risky\n" >&2
  echo "[git_commit_safety] 按 workflow.md § 6.1, 必须先 git rm --cached 撤出 + 补 .gitignore 后再 commit" >&2
  exit 2
fi

exit 0

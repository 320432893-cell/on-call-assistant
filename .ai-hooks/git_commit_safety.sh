#!/usr/bin/env bash
# PreToolUse hook on Bash: git commit 前体检暂存区
# 对应 AGENTS.md 的工作区体检和 git 协作边界
# 退出码 2 = 阻断
set -u

input=$(cat)
commit_action=$(printf '%s' "$input" | python3 -c "
import json
import shlex
import sys

GIT_OPTS_WITH_VALUE = {'-C', '-c', '--git-dir', '--work-tree', '--namespace'}

def command_words(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|()')
    lexer.whitespace_split = True
    lexer.commenters = ''
    words = []
    current = []
    for token in lexer:
        if token in {';', '&&', '||', '|', '(', ')'}:
            if current:
                words.append(current)
                current = []
            continue
        current.append(token)
    if current:
        words.append(current)
    return words

def is_git_commit(words):
    if not words or words[0] != 'git':
        return False
    i = 1
    while i < len(words):
        word = words[i]
        if word == 'commit':
            return True
        if word in GIT_OPTS_WITH_VALUE:
            i += 2
            continue
        if word.startswith('--git-dir=') or word.startswith('--work-tree=') or word.startswith('--namespace='):
            i += 1
            continue
        if word.startswith('-'):
            i += 1
            continue
        return False
    return False

try:
    data = json.load(sys.stdin)
    command = data.get('tool_input', {}).get('command', '')
except Exception:
    command = ''

if not command:
    raise SystemExit(0)

for words in command_words(command):
    if is_git_commit(words):
        if any(word in {'--help', '-h'} for word in words):
            print('help', end='')
        else:
            print('commit', end='')
        break
" 2>/dev/null)

[ "$commit_action" = "commit" ] || exit 0

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
    *.env|.env|.env.*|*/.env|*.key|*.pem|*credentials*|*secret*|*token*|*password*)
      risky="$risky\n  - $f (密钥/敏感)"
      ;;
    *.venv/*|venv/*|*/__pycache__/*|*.pyc)
      risky="$risky\n  - $f (虚拟环境/缓存)"
      ;;
    *node_modules/*|*/node_modules/*|.idea/*|*/.idea/*|.vscode/*|*/.vscode/*)
      risky="$risky\n  - $f (依赖/IDE 元数据)"
      ;;
    .claude/*|*/.claude/*|.codex/*|*/.codex/*)
      risky="$risky\n  - $f (AI 工具本地配置)"
      ;;
    screenshot/*|*/screenshot/*|*screenshot_*.png|*.log|logs/*|*/logs/*)
      risky="$risky\n  - $f (运行产物/截图/日志)"
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
  echo "[git_commit_safety] 按 AGENTS.md, 必须先 git rm --cached 撤出 + 补 .gitignore 后再 commit" >&2
  exit 2
fi

exit 0

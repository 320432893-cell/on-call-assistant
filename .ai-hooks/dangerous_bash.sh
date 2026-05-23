#!/usr/bin/env bash
# PreToolUse hook on Bash: 拦截高风险不可逆命令
# 退出码 2 = 阻断,把理由写到 stderr 让 AI 看到
# 对应 process/workflow.index.md 的回滚方案 + 不确定即问
set -u

input=$(cat)
match=$(printf '%s' "$input" | python3 -c "
import json, sys
import shlex

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

def is_rm_rf(words):
    return bool(words and words[0] == 'rm' and any(word.startswith('-') and 'r' in word and 'f' in word for word in words[1:]))

def is_git_reset_hard(words):
    return len(words) >= 3 and words[0] == 'git' and words[1] == 'reset' and words[2] in {'--hard', '--keep'}

def is_git_push_force(words):
    return len(words) >= 3 and words[0] == 'git' and words[1] == 'push' and any(
        word in {'--force', '--force-with-lease', '-f'} for word in words[2:]
    )

def is_git_clean_force_delete(words):
    return len(words) >= 3 and words[0] == 'git' and words[1] == 'clean' and any(
        word.startswith('-') and 'f' in word and 'd' in word for word in words[2:]
    )

def removes_git_dir(words):
    return bool(words and words[0] == 'rm' and any(word == '.git' or word.startswith('.git/') or '/.git/' in word for word in words[1:]))

try:
    data = json.load(sys.stdin)
    command = data.get('tool_input', {}).get('command', '')
except Exception:
    command = ''

if not command:
    raise SystemExit(0)

for words in command_words(command):
    if is_rm_rf(words):
        print('rm -rf 递归强删', end='')
        break
    if is_git_reset_hard(words):
        print('git reset --hard 会丢弃未提交改动', end='')
        break
    if is_git_push_force(words):
        print('git push --force 会覆盖远程历史', end='')
        break
    if is_git_clean_force_delete(words):
        print('git clean -fd 会删除未跟踪文件', end='')
        break
    if removes_git_dir(words):
        print('删除 .git 目录会丢失整个版本历史', end='')
        break
" 2>/dev/null)

[ -z "$match" ] && exit 0

block() {
  echo "[dangerous_bash] 阻断: $match" >&2
  echo "[dangerous_bash] 按 process/workflow.index.md,执行不可逆操作前必须输出回滚方案并取得用户确认" >&2
  exit 2
}

block

exit 0

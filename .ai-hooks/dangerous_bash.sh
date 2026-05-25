#!/usr/bin/env bash
# PreToolUse hook on Bash: 拦截高风险命令
# 退出码 2 = 阻断,把理由写到 stderr 让 AI 看到
# 对应 AGENTS.md 的高风险操作协作边界
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

def base_command(word):
    return word.rsplit('/', 1)[-1]

def strip_wrappers(words):
    while words and base_command(words[0]) in {'sudo', 'env', 'command'}:
        words = words[1:]
        if words and '=' in words[0] and base_command(words[0]) == words[0]:
            while words and '=' in words[0] and not words[0].startswith('-'):
                words = words[1:]
    return words

def git_args(words):
    if not words or base_command(words[0]) != 'git':
        return []
    args = words[1:]
    index = 0
    global_options_with_value = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--exec-path'}
    while index < len(args):
        word = args[index]
        if word == '--':
            index += 1
            break
        if word in global_options_with_value:
            index += 2
            continue
        if any(word.startswith(prefix + '=') for prefix in global_options_with_value):
            index += 1
            continue
        if word.startswith('-'):
            index += 1
            continue
        break
    return args[index:]

def is_rm_rf(words):
    return bool(words and base_command(words[0]) == 'rm' and any(word.startswith('-') and 'r' in word and 'f' in word for word in words[1:]))

def is_git_reset_hard(words):
    args = git_args(words)
    return len(args) >= 2 and args[0] == 'reset' and args[1] in {'--hard', '--keep'}

def is_git_push_force(words):
    args = git_args(words)
    return len(args) >= 2 and args[0] == 'push' and any(
        word in {'--force', '--force-with-lease', '-f'} for word in args[1:]
    )

def is_git_push(words):
    args = git_args(words)
    return len(args) >= 1 and args[0] == 'push'

def is_git_add_all(words):
    args = git_args(words)
    return len(args) >= 2 and args[0] == 'add' and any(
        word in {'.', '-A', '--all'} for word in args[1:]
    )

def is_git_checkout_or_switch(words):
    args = git_args(words)
    return len(args) >= 1 and args[0] in {'checkout', 'switch'}

def is_git_clean_force_delete(words):
    args = git_args(words)
    return len(args) >= 2 and args[0] == 'clean' and any(
        word.startswith('-') and 'f' in word and 'd' in word for word in args[1:]
    )

def removes_git_dir(words):
    return bool(words and base_command(words[0]) == 'rm' and any(word == '.git' or word.startswith('.git/') or '/.git/' in word for word in words[1:]))

def is_dependency_or_download(words):
    if not words:
        return False
    cmd = base_command(words[0])
    if cmd == 'pip' and len(words) >= 2 and words[1] in {'install', 'download'}:
        return True
    if len(words) >= 3 and cmd in {'python', 'python3', 'py'} and words[1] == '-m' and words[2] == 'pip':
        return len(words) >= 4 and words[3] in {'install', 'download'}
    if cmd == 'uv' and len(words) >= 2 and words[1] in {'add', 'remove', 'sync', 'lock', 'pip'}:
        return True
    if cmd in {'npm', 'pnpm', 'yarn'} and len(words) >= 2 and words[1] in {'install', 'i', 'add', 'remove'}:
        return True
    if cmd == 'npx':
        return True
    if cmd == 'playwright' and len(words) >= 2 and words[1] in {'install', 'install-deps'}:
        return True
    if len(words) >= 3 and cmd == 'node' and 'playwright' in words[1] and words[2] in {'install', 'install-deps'}:
        return True
    if cmd == 'docker' and len(words) >= 2 and words[1] in {'pull', 'run', 'build'}:
        return True
    return False

try:
    data = json.load(sys.stdin)
    command = data.get('tool_input', {}).get('command', '')
except Exception:
    command = ''

if not command:
    raise SystemExit(0)

for raw_words in command_words(command):
    words = strip_wrappers(raw_words)
    if is_rm_rf(words):
        print('rm -rf 递归强删', end='')
        break
    if is_git_reset_hard(words):
        print('git reset --hard 会丢弃未提交改动', end='')
        break
    if is_git_push_force(words):
        print('git push --force 会覆盖远程历史', end='')
        break
    if is_git_push(words):
        print('git push 会发布本地提交到远端', end='')
        break
    if is_git_add_all(words):
        print('git add . / -A 会批量暂存文件', end='')
        break
    if is_git_checkout_or_switch(words):
        print('git checkout/switch 会切换工作区状态', end='')
        break
    if is_git_clean_force_delete(words):
        print('git clean -fd 会删除未跟踪文件', end='')
        break
    if removes_git_dir(words):
        print('删除 .git 目录会丢失整个版本历史', end='')
        break
    if is_dependency_or_download(words):
        print('依赖安装/下载/工具链变更需要用户确认；Python 包默认使用清华源', end='')
        break
" 2>/dev/null)

[ -z "$match" ] && exit 0

block() {
  echo "[dangerous_bash] 阻断: $match" >&2
  echo "[dangerous_bash] 按 AGENTS.md,执行高影响操作前必须说明影响、回滚或替代方案并取得用户确认" >&2
  exit 2
}

block

exit 0

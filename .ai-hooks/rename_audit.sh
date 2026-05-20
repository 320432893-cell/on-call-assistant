#!/usr/bin/env bash
# PostToolUse hook (Edit/MultiEdit): 幽灵引用扫描
# 对应 flow_legacy_project.md § 8 老项目红线 — 改名/删除后 grep 旧名
#
# 工作原理:
#   - 从 tool_input 解析出本次 Edit 的 old_string / new_string
#   - 用 ast/regex 提取 old 里被删除/改名的 def/class 名
#   - grep 项目其他文件,看旧名是否残留(幽灵引用)
#   - 残留则 stderr 提醒,不阻断
set -u

input=$(cat)

# 用 python 解析 JSON 全程,避开 shell 变量注入
parsed=$(printf '%s' "$input" | OLD_INPUT="$input" python3 <<'PYEOF' 2>/dev/null
import sys, json, os
try:
    data = json.loads(os.environ.get('OLD_INPUT', sys.stdin.read()))
    tool = data.get('tool_name', '')
    fp = data.get('tool_input', {}).get('file_path', '')
    old = data.get('tool_input', {}).get('old_string', '')
    new = data.get('tool_input', {}).get('new_string', '')
    print(f"TOOL={tool}")
    print(f"FILE={fp}")
    # 用 base64 逃逸,避免 shell 处理换行/引号
    import base64
    print(f"OLD_B64={base64.b64encode(old.encode('utf-8')).decode('ascii')}")
    print(f"NEW_B64={base64.b64encode(new.encode('utf-8')).decode('ascii')}")
except Exception:
    pass
PYEOF
)

[ -z "$parsed" ] && exit 0
eval "$parsed"

# 只处理 Edit / MultiEdit (Write 是新文件或全量改写,不适用)
case "${TOOL:-}" in
  Edit|MultiEdit) ;;
  *) exit 0 ;;
esac

# 文件类型过滤
case "${FILE:-}" in
  *.py|*.vue|*.ts|*.js|*.tsx|*.jsx) ;;
  *) exit 0 ;;
esac

[ -z "${FILE:-}" ] && exit 0
[ ! -f "$FILE" ] && exit 0
[ -z "${OLD_B64:-}" ] && exit 0

# 找项目根
find_project_root() {
  local dir
  dir=$(dirname "$FILE")
  dir=$(cd "$dir" 2>/dev/null && pwd) || return 1
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -d "$dir/.git" ]; then
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

# 通过 env 把 base64 内容传给 Python(零字符串注入风险)
removed_names=$(OLD_B64="$OLD_B64" NEW_B64="$NEW_B64" python3 <<'PYEOF' 2>/dev/null
import os, re, base64

old = base64.b64decode(os.environ['OLD_B64']).decode('utf-8', errors='ignore')
new = base64.b64decode(os.environ['NEW_B64']).decode('utf-8', errors='ignore')

patterns = [
    r'^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    r'^\s*async\s+def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]',
    r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    r'^\s*export\s+function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
    r'^\s*const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=',
]

old_names = set()
new_names = set()
for pat in patterns:
    for m in re.finditer(pat, old, re.MULTILINE):
        old_names.add(m.group(1))
    for m in re.finditer(pat, new, re.MULTILINE):
        new_names.add(m.group(1))

removed = old_names - new_names
# 过滤过短/常见词,降低误报
SKIP = {'self', 'cls', 'main', 'init', 'data', 'temp', 'test', 'args', 'kwargs', 'value', 'name', 'item'}
removed = {n for n in removed if len(n) >= 4 and n not in SKIP and not n.startswith('_')}

for n in sorted(removed):
    print(n)
PYEOF
)

[ -z "$removed_names" ] && exit 0

# 相对路径,避免 grep 自己又匹配到本文件
file_rel="${FILE#$project_root/}"

ghost_refs=""
while IFS= read -r name; do
  [ -z "$name" ] && continue
  refs=$(cd "$project_root" && grep -rn --include="*.py" --include="*.vue" --include="*.ts" --include="*.js" \
    --exclude-dir=.venv --exclude-dir=venv --exclude-dir=.git --exclude-dir=node_modules \
    --exclude-dir=__pycache__ --exclude-dir=dist --exclude-dir=.ai-hooks \
    -wE "\b${name}\b" 2>/dev/null | grep -v "^${file_rel}:" | head -3)
  if [ -n "$refs" ]; then
    ghost_refs="${ghost_refs}\n  [删除/改名: ${name}]"
    while IFS= read -r line; do
      ghost_refs="${ghost_refs}\n      $line"
    done <<< "$refs"
  fi
done <<< "$removed_names"

if [ -n "$ghost_refs" ]; then
  echo "" >&2
  echo "[rename_audit] 检测到幽灵引用 — flow_legacy_project.md § 8" >&2
  echo "[rename_audit] 本次 Edit 删除/改名了符号,但项目其他文件仍在引用:" >&2
  printf '%b\n' "$ghost_refs" >&2
  echo "" >&2
  echo "[rename_audit] 处置:① 同步改引用方 ② 或显式说明保留旧名的兼容理由" >&2
fi

exit 0

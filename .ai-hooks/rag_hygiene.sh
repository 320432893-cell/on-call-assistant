#!/usr/bin/env bash
# PostToolUse hook: BGE 双塔 embedding 语义检查
# 仅保留成熟静态工具暂时表达不干净的 RAG 反模式:
#   R2 — bge-m3 类双塔 embedder 调用 encode 时漏 is_query 参数(query/passage 必须区分)
# R6/R7 已下放到 .semgrep/rag-hygiene.yml，避免 hook 与 semgrep 重复报告。

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

case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac

case "$file_path" in
  */tests/*|*/test/*) exit 0 ;;
esac
case "$(basename "$file_path")" in
  test_*.py|*_test.py) exit 0 ;;
esac

# 必须 import 相关库才扫
relevant=$(grep -E "^(from sentence_transformers|import sentence_transformers|from qdrant_client|import qdrant_client)" "$file_path" 2>/dev/null)
[ -z "$relevant" ] && exit 0

violations=$(FILE="$file_path" python3 <<'PYEOF' 2>/dev/null
import ast, os, sys

try:
    src = open(os.environ['FILE'], encoding='utf-8').read()
    tree = ast.parse(src)
except Exception:
    sys.exit(0)

issues = []

for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue

    func = node.func
    func_name = None
    if isinstance(func, ast.Name):
        func_name = func.id
    elif isinstance(func, ast.Attribute):
        func_name = func.attr

    # R2: encode(...) 漏 is_query
    if func_name == 'encode' and isinstance(func, ast.Attribute):
        parent = func.value
        parent_name = ''
        if isinstance(parent, ast.Name):
            parent_name = parent.id.lower()
        elif isinstance(parent, ast.Attribute):
            parent_name = parent.attr.lower()
        if any(h in parent_name for h in ['embed', 'encoder', 'model', 'bge']):
            kw_names = {kw.arg for kw in node.keywords if kw.arg}
            first_arg_is_literal = (
                node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            )
            if not first_arg_is_literal and 'is_query' not in kw_names:
                if any(k in src for k in ['bge', 'BGE', 'is_query', 'query_prefix']):
                    issues.append(f"  line {node.lineno}: {parent_name}.encode(...) 缺 is_query= 参数(bge 双塔必须区分 query/passage)")

for line in issues[:10]:
    print(line)
PYEOF
)

if [ -n "$violations" ]; then
  echo "" >&2
  echo "[rag_hygiene] 文件 $file_path 检测到 BGE embedding 语义风险:" >&2
  echo "$violations" >&2
  echo "" >&2
  echo "[rag_hygiene] 处置:" >&2
  echo "    R2 — 双塔 embedder encode(text, is_query=True/False) 必须显式区分" >&2
fi

exit 0

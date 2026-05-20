#!/usr/bin/env bash
# PostToolUse hook: FastAPI 不安全配置检测
# 对应 backend.md / architecture.md § 5 配置 vs 代码边界
#
# 检测项:
#   1. FastAPI(debug=True) / Flask(debug=True) 硬编码
#   2. CORSMiddleware allow_origins=["*"] / allow_origins=("*",)
#   3. uvicorn.run(..., reload=True, ...) 硬编码(reload 是开发模式)
#
# 误报控制:
#   - tests/ 目录跳过
#   - debug=settings.X / debug=os.getenv(...) 等走配置的放行(只拦字面 True)

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

# 必须先 import 了 FastAPI / Flask / CORSMiddleware / uvicorn 才扫
imports_relevant=$(grep -E "^(from fastapi|import fastapi|from flask|import flask|from starlette|CORSMiddleware|import uvicorn|from uvicorn)" "$file_path" 2>/dev/null)
[ -z "$imports_relevant" ] && exit 0

violations=$(FILE="$file_path" python3 <<'PYEOF' 2>/dev/null
import ast, os, sys

try:
    src = open(os.environ['FILE'], encoding='utf-8').read()
    tree = ast.parse(src)
except Exception:
    sys.exit(0)

UNSAFE_FRAMEWORK_NAMES = {'FastAPI', 'Flask', 'Starlette'}

issues = []

def is_literal_true(node):
    """node 是 Constant(True) 字面量"""
    return isinstance(node, ast.Constant) and node.value is True

def is_wildcard_origin(node):
    """node 是 ['*'] / ('*',) 等通配 origin"""
    if isinstance(node, (ast.List, ast.Tuple)):
        for el in node.elts:
            if isinstance(el, ast.Constant) and el.value == '*':
                return True
    return False

for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue

    func = node.func
    func_name = None
    if isinstance(func, ast.Name):
        func_name = func.id
    elif isinstance(func, ast.Attribute):
        func_name = func.attr

    # 1. FastAPI(debug=True) / Flask(debug=True)
    if func_name in UNSAFE_FRAMEWORK_NAMES:
        for kw in node.keywords:
            if kw.arg == 'debug' and is_literal_true(kw.value):
                issues.append(f"  line {node.lineno}: {func_name}(debug=True) 硬编码 — 应走配置 settings.DEBUG / os.getenv")

    # 2. CORSMiddleware allow_origins=["*"]
    if func_name == 'add_middleware':
        # app.add_middleware(CORSMiddleware, allow_origins=["*"])
        is_cors = False
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id == 'CORSMiddleware':
                is_cors = True
                break
            if isinstance(arg, ast.Attribute) and arg.attr == 'CORSMiddleware':
                is_cors = True
                break
        if is_cors:
            for kw in node.keywords:
                if kw.arg == 'allow_origins' and is_wildcard_origin(kw.value):
                    issues.append(f"  line {node.lineno}: CORSMiddleware allow_origins=['*'] 全开 — 生产环境应限定具体域名")

    # 也覆盖直接 CORSMiddleware(allow_origins=["*"]) 这种(不常见但严谨)
    if func_name == 'CORSMiddleware':
        for kw in node.keywords:
            if kw.arg == 'allow_origins' and is_wildcard_origin(kw.value):
                issues.append(f"  line {node.lineno}: CORSMiddleware allow_origins=['*'] 全开")

    # 3. uvicorn.run(..., reload=True)
    is_uvicorn_run = False
    if isinstance(func, ast.Attribute) and func.attr == 'run':
        if isinstance(func.value, ast.Name) and func.value.id == 'uvicorn':
            is_uvicorn_run = True
    if is_uvicorn_run:
        for kw in node.keywords:
            if kw.arg == 'reload' and is_literal_true(kw.value):
                issues.append(f"  line {node.lineno}: uvicorn.run(reload=True) 硬编码 — reload 仅用于开发,应走配置")

for line in issues[:10]:
    print(line)
PYEOF
)

if [ -n "$violations" ]; then
  echo "" >&2
  echo "[fastapi_debug] 文件 $file_path 检测到不安全配置硬编码:" >&2
  echo "$violations" >&2
  echo "" >&2
  echo "[fastapi_debug] 处置:走配置(settings.DEBUG / os.getenv('DEBUG'))而非代码字面量" >&2
  echo "[fastapi_debug] 对应规则: architecture.md § 5 配置 vs 代码边界" >&2
fi

exit 0

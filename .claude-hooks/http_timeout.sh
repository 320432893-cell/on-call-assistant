#!/usr/bin/env bash
# PostToolUse hook: HTTP 客户端调用无 timeout 检测
# 对应 architecture.md § 7 外部服务调用边界 — 必须设置超时
#
# 工作原理:
#   - grep requests/httpx/urllib 的客户端调用
#   - 检查同行或同语句块内是否含 timeout=
#   - 没有 → stderr 报警,不阻断
#
# 误报控制:
#   - mock/test 文件跳过(*_test.py / test_*.py / tests/)
#   - 类方法定义里的 self.requests.get 不算(只看顶层 requests 模块调用)
#   - 字符串里的 "requests.get" 不算(grep -E 边界)

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

# 测试文件跳过(只看仓库内 tests/ 目录或文件名以 test_ / _test 收尾)
case "$file_path" in
  */tests/*|*/test/*) exit 0 ;;
esac
case "$(basename "$file_path")" in
  test_*.py|*_test.py) exit 0 ;;
esac

# 用 Python ast 精准查:requests/httpx/urllib 调用是否含 timeout 关键字参数
violations=$(FILE="$file_path" python3 <<'PYEOF' 2>/dev/null
import ast, os, sys

CLIENT_FUNCS = {
    # requests
    'requests.get', 'requests.post', 'requests.put', 'requests.delete',
    'requests.patch', 'requests.head', 'requests.options', 'requests.request',
    # httpx 同步 + 异步
    'httpx.get', 'httpx.post', 'httpx.put', 'httpx.delete',
    'httpx.patch', 'httpx.head', 'httpx.options', 'httpx.request',
    # urllib
    'urllib.request.urlopen',
}

# 客户端实例方法(client.get / await client.get)— 名字部分必须是常见 client 命名
INSTANCE_METHODS = {'get', 'post', 'put', 'delete', 'patch', 'head', 'request'}
INSTANCE_NAME_HINTS = {'client', 'session', 'http', 'requests', '_client', '_session'}

try:
    src = open(os.environ['FILE'], encoding='utf-8').read()
    tree = ast.parse(src, filename=os.environ['FILE'])
except Exception:
    sys.exit(0)

def get_call_name(node):
    """提取 a.b.c(...) 形式的 'a.b.c'"""
    if isinstance(node, ast.Attribute):
        parts = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return '.'.join(reversed(parts))
    elif isinstance(node, ast.Name):
        return node.id
    return None

def is_likely_client(call_node):
    """判断 self.client.get / session.post 这类实例方法"""
    if not isinstance(call_node.func, ast.Attribute):
        return False
    if call_node.func.attr not in INSTANCE_METHODS:
        return False
    parent = call_node.func.value
    while isinstance(parent, ast.Attribute):
        parent = parent.value
    if isinstance(parent, ast.Name):
        n = parent.id.lower()
        return any(hint in n for hint in INSTANCE_NAME_HINTS)
    return False

found = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue

    name = get_call_name(node.func)
    is_module_call = name in CLIENT_FUNCS
    is_inst_call = is_likely_client(node)

    if not (is_module_call or is_inst_call):
        continue

    # 检查 timeout 关键字参数
    has_timeout = any(kw.arg == 'timeout' for kw in node.keywords)
    # 也算 **kwargs 形式(无法静态判,放过)
    has_double_star = any(kw.arg is None for kw in node.keywords)
    if has_timeout or has_double_star:
        continue

    line = node.lineno
    func_repr = name if is_module_call else f"<client>.{node.func.attr}"
    found.append(f"  line {line}: {func_repr}(...)")

for f in found[:5]:
    print(f)
PYEOF
)

if [ -n "$violations" ]; then
  echo "" >&2
  echo "[http_timeout] 文件 $file_path 含无 timeout 的 HTTP 调用 — architecture.md § 7" >&2
  echo "$violations" >&2
  echo "" >&2
  echo "[http_timeout] 处置:" >&2
  echo "    ① 加 timeout=N 参数(秒,如 timeout=30)" >&2
  echo "    ② 或用 client/session 实例并在构造时设默认 timeout" >&2
  echo "    ③ 显式无超时场景(SSE/长轮询):用 timeout=None 显式声明" >&2
fi

exit 0

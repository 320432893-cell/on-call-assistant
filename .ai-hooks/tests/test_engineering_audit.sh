#!/usr/bin/env bash
# engineering_audit.sh 单测
# 按 rule_governance/governance.index.md: 至少 3 正样本 + 3 反样本(含边界)
# 用法: bash tests/test_engineering_audit.sh
set -u

HOOK="$(cd "$(dirname "$0")/.." && pwd)/engineering_audit.sh"
PASS=0; FAIL=0; TOTAL=0
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

assert_stderr_contains() {
  local desc="$1" expected="$2" actual="$3"
  TOTAL=$((TOTAL + 1))
  if echo "$actual" | grep -qF "$expected"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: 期望 stderr 含 '$expected'" >&2
    echo "  实际: $(echo "$actual" | head -3)" >&2
  fi
}

assert_stderr_empty() {
  local desc="$1" actual="$2"
  TOTAL=$((TOTAL + 1))
  if [ -z "$actual" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL [$desc]: 期望 stderr 为空" >&2
    echo "  实际: $(echo "$actual" | head -3)" >&2
  fi
}

# 辅助: 创建最小项目(≥5 py 文件 + .git)
make_project() {
  local dir="$1"
  mkdir -p "$dir"
  git -C "$dir" init -q
  for i in 1 2 3 4 5; do
    echo "x = $i" > "$dir/mod_$i.py"
  done
}

run_hook() {
  local file_path="$1"
  rm -f /tmp/eng_audit_*.done
  echo "{\"tool_input\":{\"file_path\":\"$file_path\"}}" \
    | bash "$HOOK" 2>&1 1>/dev/null
}

# ========== 正样本(应触发报告) ==========

# P1: 项目无 .gitignore → 红线
echo "--- P1: 无 .gitignore ---"
proj="$TMP_ROOT/p1"
make_project "$proj"
rm -f "$proj/.gitignore"
out=$(run_hook "$proj/mod_1.py")
assert_stderr_contains "P1: 无 .gitignore 触发红线" "★★★" "$out"

# P2: 项目无 README → 警告
echo "--- P2: 无 README ---"
proj="$TMP_ROOT/p2"
make_project "$proj"
touch "$proj/.gitignore"
out=$(run_hook "$proj/mod_1.py")
assert_stderr_contains "P2: 无 README 触发警告" "★★ 无 README" "$out"

# P3: 项目无 tests/ → 警告
echo "--- P3: 无 tests ---"
proj="$TMP_ROOT/p3"
make_project "$proj"
touch "$proj/.gitignore" "$proj/README.md"
echo "uv.lock" > "$proj/uv.lock"
out=$(run_hook "$proj/mod_1.py")
assert_stderr_contains "P3: 无 tests 触发警告" "★★ 无 tests" "$out"

# ========== 反样本(不应触发报告) ==========

# N1: 完备项目(有 .git + .gitignore + README + lock + tests)
echo "--- N1: 完备项目 ---"
proj="$TMP_ROOT/n1"
make_project "$proj"
printf '.venv\n__pycache__\n.env\n.idea\n.vscode\n*.pyc\n' > "$proj/.gitignore"
touch "$proj/README.md"
echo "lock" > "$proj/uv.lock"
mkdir -p "$proj/tests" && echo "def test_x(): pass" > "$proj/tests/test_a.py"
out=$(run_hook "$proj/mod_1.py")
assert_stderr_empty "N1: 完备项目无报告" "$out"

# N2: 项目 <5 py 文件(规模门槛不触发)
echo "--- N2: <5 py 文件 ---"
proj="$TMP_ROOT/n2"
mkdir -p "$proj" && git -C "$proj" init -q
echo "x=1" > "$proj/a.py"
echo "x=2" > "$proj/b.py"
out=$(run_hook "$proj/a.py")
assert_stderr_empty "N2: <5 py 不触发" "$out"

# N3: 非项目路径(无 .git 也无 pyproject.toml → 找不到项目根)
echo "--- N3: 非项目路径 ---"
proj="$TMP_ROOT/n3"
mkdir -p "$proj"
for i in 1 2 3 4 5; do echo "x=$i" > "$proj/m$i.py"; done
out=$(run_hook "$proj/m1.py")
assert_stderr_empty "N3: 无项目根不触发" "$out"

# ========== 汇总 ==========
echo ""
echo "========================================="
echo "  结果: $PASS/$TOTAL 通过, $FAIL 失败"
echo "========================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1

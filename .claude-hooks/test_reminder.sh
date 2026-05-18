#!/usr/bin/env bash
# PostToolUse hook: Edit/Write 后,如果存在对应 test_*.py 提醒 AI 跑测试
# 对应 workflow.md § 6.6 测试存在性
set -u

input=$(cat)
file_path=$(printf '%s' "$input" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"file_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')

# 不是 .py 或本身就是 test 文件直接放行
case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac
base=$(basename "$file_path")
case "$base" in
  test_*|*_test.py|conftest.py) exit 0 ;;
esac

# 在文件所在目录及其父级查找对应 test
dir=$(dirname "$file_path")
stem="${base%.py}"

found=""
# 同目录
for cand in "$dir/test_$stem.py" "$dir/${stem}_test.py" "$dir/tests/test_$stem.py"; do
  [ -f "$cand" ] && found="$cand" && break
done
# 父级 tests/
if [ -z "$found" ]; then
  parent=$(dirname "$dir")
  for cand in "$parent/tests/test_$stem.py" "$parent/test/test_$stem.py"; do
    [ -f "$cand" ] && found="$cand" && break
  done
fi

if [ -n "$found" ]; then
  echo "[test reminder] 检测到对应测试文件: $found" >&2
  echo "[test reminder] 按 workflow.md § 6.6, 修改后必须运行测试; bug 修复需补复现用例; 行为变更需调整用例" >&2
fi
exit 0

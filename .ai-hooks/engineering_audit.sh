#!/usr/bin/env bash
# PostToolUse hook (Edit/Write/MultiEdit): 工程规范审计器
# 改完代码后扫描项目根缺口,stderr 报告,不阻断
# 同会话+同项目只报一次,避免噪音
#
# 检测项分级:
#   ★★★ 红线  (.gitignore 缺 / 大文件入库 / 无 .git)
#   ★★ 警告   (无 README / 无 lock 文件 / 无 tests/)
#   ★  提醒   (大文件 >500 行)
#
# 为什么不能用 ruff/mypy: 本 hook 检查的是项目结构/配置完备性,不是代码质量
# 代码级检查(大函数/循环import/死代码)已移交 ruff PLR0915 / import-linter / ruff F401

set -u

input=$(cat)
file_path=$(printf '%s' "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    fp = data.get('tool_input', {}).get('file_path', '')
    print(fp, end='')
except Exception:
    pass
" 2>/dev/null)

[ -z "$file_path" ] && exit 0
[ ! -e "$file_path" ] && exit 0

# === 1. 找项目根:向上找 .git 或 pyproject.toml/setup.py ===
find_project_root() {
  local dir
  dir=$(dirname "$file_path")
  dir=$(cd "$dir" 2>/dev/null && pwd) || return 1
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -d "$dir/.git" ] || [ -f "$dir/pyproject.toml" ] || [ -f "$dir/setup.py" ]; then
      echo "$dir"
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

project_root=$(find_project_root)
[ -z "$project_root" ] && exit 0

# 排除 ~/.claude 自身的改动(规则文件不是"项目")
case "$project_root" in
  "$HOME/.claude"*) exit 0 ;;
esac

# === 2. skip 标记 ===
[ -f "$project_root/.eng_audit_skip" ] && exit 0

# === 3. 项目规模门槛: .py >= 5 ===
py_count=$(find "$project_root" -name "*.py" \
  -not -path "*/.venv/*" -not -path "*/venv/*" \
  -not -path "*/__pycache__/*" -not -path "*/.git/*" \
  -not -path "*/node_modules/*" 2>/dev/null | wc -l)

[ "$py_count" -lt 5 ] && exit 0

# === 4. 去重: 用项目路径 hash 标记,6 小时过期 ===
# 之所以不靠 session_id: 多数 hook 调用 bash 时 $$ 变化,session_id 不稳定
# 6 小时窗口够覆盖单次工作周期,过期后下次审计能再提醒
proj_hash=$(echo -n "$project_root" | md5sum | cut -c1-8)
done_marker="/tmp/eng_audit_${proj_hash}.done"
if [ -f "$done_marker" ]; then
  # 文件存在但超过 6 小时则重审
  if [ "$(find "$done_marker" -mmin +360 2>/dev/null | wc -l)" -eq 0 ]; then
    exit 0
  fi
  # 否则清掉旧标记,继续审
  rm -f "$done_marker"
fi

# === 5. 扫描 ===
red_lines=""    # ★★★
warnings=""     # ★★
hints=""        # ★

# --- 核心 5 项 ---

# 5.1 .git 存在
if [ ! -d "$project_root/.git" ]; then
  red_lines="${red_lines}\n  ★★★ 无 .git 目录,代码无版本控制 → git init"
fi

# 5.2 .gitignore 完备性
if [ ! -f "$project_root/.gitignore" ]; then
  red_lines="${red_lines}\n  ★★★ 无 .gitignore → 风险:虚拟环境/缓存/密钥可能入库"
else
  missing=""
  for pat in ".venv" "__pycache__" ".env" ".idea" ".vscode" "*.pyc"; do
    if ! grep -qE "(^|/)${pat}(/|\$)?" "$project_root/.gitignore" 2>/dev/null; then
      missing="$missing $pat"
    fi
  done
  if [ -n "$missing" ]; then
    red_lines="${red_lines}\n  ★★★ .gitignore 缺关键项:$missing"
  fi
fi

# 5.3 大文件入库检查(>5MB 已跟踪)
if [ -d "$project_root/.git" ]; then
  large_tracked=$(cd "$project_root" && git ls-files 2>/dev/null | while read f; do
    [ -f "$f" ] || continue
    size=$(wc -c < "$f" 2>/dev/null || echo 0)
    [ "$size" -gt 5242880 ] && echo "$f ($((size / 1048576))MB)"
  done | head -3)
  if [ -n "$large_tracked" ]; then
    red_lines="${red_lines}\n  ★★★ 大文件已 tracked (>5MB):"
    while IFS= read -r line; do
      red_lines="${red_lines}\n      - $line"
    done <<< "$large_tracked"
  fi
fi

# 5.4 README 存在
has_readme="no"
for f in README.md README.rst README.txt README; do
  [ -f "$project_root/$f" ] && has_readme="yes" && break
done
[ "$has_readme" = "no" ] && warnings="${warnings}\n  ★★ 无 README → 新人接手成本高"

# 5.5 lock 文件
has_lock="no"
for f in poetry.lock uv.lock Pipfile.lock requirements.lock; do
  [ -f "$project_root/$f" ] && has_lock="yes" && break
done
if [ "$has_lock" = "no" ]; then
  has_req=""
  [ -f "$project_root/requirements.txt" ] && has_req="requirements.txt"
  [ -f "$project_root/pyproject.toml" ] && has_req="$has_req pyproject.toml"
  if [ -n "$has_req" ]; then
    warnings="${warnings}\n  ★★ 有依赖声明($has_req)但无 lock 文件 → 复现性差"
  else
    warnings="${warnings}\n  ★★ 无依赖声明也无 lock 文件 → 完全无法复现环境"
  fi
fi

# --- 扩展 3 项 ---

# 5.6 tests/ 存在 + 测试文件数
test_count=0
for d in tests test; do
  if [ -d "$project_root/$d" ]; then
    test_count=$(find "$project_root/$d" -name "test_*.py" -o -name "*_test.py" 2>/dev/null | wc -l)
    break
  fi
done
if [ "$test_count" -eq 0 ]; then
  warnings="${warnings}\n  ★★ 无 tests/ 目录或无 test_*.py → 改动无回归保障"
elif [ "$test_count" -lt 3 ] && [ "$py_count" -ge 20 ]; then
  hints="${hints}\n  ★ 项目 $py_count 个 .py 但只有 $test_count 个测试 → 覆盖偏低"
fi

# 5.7 大文件 >500 行 (.py) / >300 行 (.vue)
big_files=$(find "$project_root" -name "*.py" \
  -not -path "*/.venv/*" -not -path "*/venv/*" \
  -not -path "*/__pycache__/*" -not -path "*/.git/*" \
  -not -path "*/node_modules/*" 2>/dev/null | while read f; do
    lines=$(wc -l < "$f" 2>/dev/null || echo 0)
    [ "$lines" -gt 500 ] && echo "$f ($lines 行)"
  done | head -5)
big_vue=$(find "$project_root" -name "*.vue" \
  -not -path "*/node_modules/*" -not -path "*/.git/*" \
  -not -path "*/dist/*" 2>/dev/null | while read f; do
    lines=$(wc -l < "$f" 2>/dev/null || echo 0)
    [ "$lines" -gt 300 ] && echo "$f ($lines 行)"
  done | head -5)
if [ -n "$big_files" ] || [ -n "$big_vue" ]; then
  hints="${hints}\n  ★ 大文件(SRP 信号):"
  if [ -n "$big_files" ]; then
    hints="${hints}\n      [.py >500 行]"
    while IFS= read -r line; do
      hints="${hints}\n      - $line"
    done <<< "$big_files"
  fi
  if [ -n "$big_vue" ]; then
    hints="${hints}\n      [.vue >300 行]"
    while IFS= read -r line; do
      hints="${hints}\n      - $line"
    done <<< "$big_vue"
  fi
fi

# === 6. 输出 ===
if [ -n "$red_lines" ] || [ -n "$warnings" ] || [ -n "$hints" ]; then
  echo "" >&2
  echo "[engineering_audit] 项目根: $project_root ($py_count py 文件)" >&2
  echo "[engineering_audit] 工程规范缺口扫描:" >&2
  if [ -n "$red_lines" ]; then
    echo "" >&2
    echo "  === 红线(必须处理)===" >&2
    printf '%b\n' "$red_lines" >&2
  fi
  if [ -n "$warnings" ]; then
    echo "" >&2
    echo "  === 警告(建议处理)===" >&2
    printf '%b\n' "$warnings" >&2
  fi
  if [ -n "$hints" ]; then
    echo "" >&2
    echo "  === 提醒(可选)===" >&2
    printf '%b\n' "$hints" >&2
  fi
  echo "" >&2
  echo "[engineering_audit] 同会话同项目本次后不再重复报告。如需跳过该项目,touch \$PROJECT/.eng_audit_skip" >&2
fi

# 标记已扫
touch "$done_marker" 2>/dev/null

exit 0

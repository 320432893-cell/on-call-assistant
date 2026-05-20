#!/usr/bin/env bash
# 老项目健康检查脚本
# 用法:
#   bash legacy_health_check.sh gate1 <项目路径>   皮毛检查
#   bash legacy_health_check.sh gate2 <项目路径>   健康检查
# 输出走 stderr,AI 读取后判断

set -u

mode="${1:-}"
project_dir="${2:-.}"

if [ -z "$mode" ] || [ ! -d "$project_dir" ]; then
  echo "用法: $0 {gate1|gate2} <项目路径>" >&2
  exit 1
fi

cd "$project_dir" || exit 1

# ============ 门 1:皮毛检查 ============
gate1() {
  echo "===== 门 1 皮毛检查: $project_dir =====" >&2

  # 项目大小
  py_files=$(find . -name "*.py" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/__pycache__/*" -not -path "*/.git/*" 2>/dev/null | wc -l)
  total_lines=$(find . -name "*.py" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/__pycache__/*" -not -path "*/.git/*" -exec cat {} + 2>/dev/null | wc -l)
  echo "[规模] py 文件数: $py_files,总代码行数: $total_lines" >&2

  # 依赖管理
  has_req="无"
  has_lock="无"
  [ -f "requirements.txt" ] && has_req="requirements.txt"
  [ -f "pyproject.toml" ] && has_req="pyproject.toml"
  [ -f "poetry.lock" ] && has_lock="poetry.lock"
  [ -f "uv.lock" ] && has_lock="uv.lock"
  [ -f "Pipfile.lock" ] && has_lock="Pipfile.lock"
  echo "[依赖] 依赖文件: $has_req,锁文件: $has_lock" >&2

  # 测试
  test_count=0
  if [ -d "tests" ] || [ -d "test" ]; then
    test_count=$(find . -name "test_*.py" -o -name "*_test.py" 2>/dev/null | grep -v -E "\.venv|venv|__pycache__|\.git" | wc -l)
  fi
  echo "[测试] test 文件数: $test_count" >&2

  # README
  has_readme="无"
  for f in README.md README.rst README.txt README; do
    [ -f "$f" ] && has_readme="$f" && break
  done
  echo "[文档] README: $has_readme" >&2

  # Git
  has_git="无"
  [ -d ".git" ] && has_git="有"
  echo "[版本] .git: $has_git" >&2

  # 文件结构(顶层目录数)
  top_dirs=$(find . -maxdepth 1 -type d -not -name "." -not -name ".git" -not -name "__pycache__" -not -name ".venv" -not -name "venv" 2>/dev/null | wc -l)
  echo "[结构] 顶层子目录: $top_dirs" >&2

  # 异常判定
  echo "" >&2
  echo "===== 门 1 评估 =====" >&2
  warnings=0
  [ "$has_req" = "无" ] && echo "[!] 无依赖文件" >&2 && warnings=$((warnings+1))
  [ "$has_lock" = "无" ] && [ "$has_req" != "无" ] && echo "[!] 依赖未锁版本" >&2 && warnings=$((warnings+1))
  [ "$test_count" -eq 0 ] && echo "[!] 无测试" >&2 && warnings=$((warnings+1))
  [ "$has_readme" = "无" ] && echo "[!] 无 README" >&2 && warnings=$((warnings+1))
  [ "$has_git" = "无" ] && echo "[!] 无 .git" >&2 && warnings=$((warnings+1))

  # 高熵判定:警告 ≥4 + 文件多
  if [ $warnings -ge 4 ] && [ "$py_files" -ge 30 ]; then
    echo "[结论] 高熵项目(警告 $warnings + py 文件 $py_files)" >&2
    return 2
  fi
  if [ $warnings -ge 1 ]; then
    echo "[结论] 基础设施缺口(警告数 $warnings)" >&2
    return 1
  fi
  echo "[结论] 基础设施健康" >&2
  return 0
}

# ============ 门 2:健康检查 ============
gate2() {
  echo "===== 门 2 健康检查: $project_dir =====" >&2

  # 1. ruff 违规密度
  if command -v ruff >/dev/null 2>&1; then
    ruff_out=$(ruff check . --quiet --output-format=concise 2>&1 || true)
    ruff_count=$(echo "$ruff_out" | grep -cE "^[^[:space:]].+:[0-9]+:[0-9]+" || echo 0)
    total_lines=$(find . -name "*.py" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/__pycache__/*" -not -path "*/.git/*" -exec cat {} + 2>/dev/null | wc -l)
    if [ "$total_lines" -gt 0 ]; then
      density=$(awk "BEGIN { printf \"%.1f\", $ruff_count * 1000 / $total_lines }")
    else
      density="N/A"
    fi
    echo "[ruff] 违规数: $ruff_count,千行密度: $density" >&2
  else
    echo "[ruff] 未安装,跳过" >&2
    ruff_count=0
    density=0
  fi

  # 2. 大文件检测(>500 行)
  big_files=$(find . -name "*.py" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/__pycache__/*" -not -path "*/.git/*" -exec wc -l {} + 2>/dev/null | awk '$1 > 500 && $2 != "total" {print $2 ": " $1 " 行"}')
  big_count=$(echo "$big_files" | grep -c ":" || echo 0)
  echo "[大文件] >500 行的文件: $big_count 个" >&2
  if [ "$big_count" -gt 0 ] && [ "$big_count" -le 5 ]; then
    echo "$big_files" | sed 's/^/  /' >&2
  fi

  # 3. 大函数粗略估算(连续非空非注释的最大块)— 用 awk 简化
  # 跳过,实战中靠 ruff PLR0915 检测

  # 4. 循环依赖(可选,需 import-linter 或 pydeps)
  # 跳过,留给用户手动配置

  # 5. 最近修改时间分布
  recent_files=$(find . -name "*.py" -mtime -30 -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/__pycache__/*" -not -path "*/.git/*" 2>/dev/null | wc -l)
  echo "[活跃度] 30 天内修改的 py 文件: $recent_files" >&2

  # 评估
  echo "" >&2
  echo "===== 门 2 评估 =====" >&2

  # 密度判定
  density_int=$(echo "$density" | awk '{print int($1)}')
  health="健康"
  if [ "$density_int" -gt 200 ] || [ "$big_count" -gt 5 ]; then
    health="烂"
  elif [ "$density_int" -gt 50 ] || [ "$big_count" -gt 0 ]; then
    health="一般"
  fi
  echo "[结论] 代码健康度: $health(密度 $density,大文件 $big_count)" >&2

  case "$health" in
    健康) return 0 ;;
    一般) return 1 ;;
    烂)   return 2 ;;
  esac
}

case "$mode" in
  gate1) gate1; exit $? ;;
  gate2) gate2; exit $? ;;
  *) echo "未知模式: $mode" >&2; exit 1 ;;
esac

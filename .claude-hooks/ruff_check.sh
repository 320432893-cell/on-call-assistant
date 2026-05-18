#!/usr/bin/env bash
# PostToolUse hook: Edit/Write 后对 .py 文件跑全套工具链检查
# - ruff 严格集(项目根 .ruff.toml 优先,回退 ~/.ruff.toml)
# - mypy 严格(项目根 .mypy.ini 优先,回退 ~/.mypy.ini)
# - 自定义检查:不稳定排序(set/dict.keys 用于 enumerate)
# 退出码 0 总是放行,违规列表写到 stderr 给 AI 看
set -u

input=$(cat)
file_path=$(printf '%s' "$input" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*"file_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')

# 不是 .py 直接放行
case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac

# 文件不存在放行
[ -f "$file_path" ] || exit 0

# 从文件所在目录向上找最近的配置文件,找不到回退到 ~/
# 用法: find_config <配置文件名> <家目录兜底路径>
find_config() {
  local name="$1"
  local fallback="$2"
  local dir
  dir=$(dirname "$file_path")
  dir=$(cd "$dir" 2>/dev/null && pwd) || { echo "$fallback"; return; }
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -f "$dir/$name" ]; then
      echo "$dir/$name"
      return
    fi
    dir=$(dirname "$dir")
  done
  echo "$fallback"
}

ruff_config=$(find_config ".ruff.toml" "$HOME/.ruff.toml")
mypy_config=$(find_config ".mypy.ini" "$HOME/.mypy.ini")

violations=""

# 1. ruff 检查
if command -v ruff >/dev/null 2>&1 && [ -f "$ruff_config" ]; then
  ruff_out=$(ruff check --config "$ruff_config" "$file_path" 2>&1)
  ruff_rc=$?
  if [ $ruff_rc -ne 0 ]; then
    violations="${violations}\n[ruff 严格集] (config: $ruff_config)\n$ruff_out\n"
  fi
fi

# 2. mypy 检查
if command -v mypy >/dev/null 2>&1 && [ -f "$mypy_config" ]; then
  mypy_out=$(mypy --config-file "$mypy_config" "$file_path" 2>&1)
  mypy_rc=$?
  if [ $mypy_rc -ne 0 ]; then
    # mypy 报错可能很多,只取前 20 行
    mypy_short=$(echo "$mypy_out" | head -20)
    violations="${violations}\n[mypy 类型检查] (config: $mypy_config)\n$mypy_short\n"
  fi
fi

# 3. 自定义检查:不稳定排序模式
# 抓 enumerate(set(...)) / enumerate(dict(...)) / list(set(...)) 用于产物
unstable=$(grep -nE 'enumerate\([[:space:]]*set\(|enumerate\([[:space:]]*dict\(.*\)\.keys\(|list\(set\(' "$file_path" 2>&1)
if [ -n "$unstable" ]; then
  violations="${violations}\n[确定性自检]\n检测到不稳定排序模式(set/dict.keys 直接用于 enumerate),按 code.md § 5 不变式规则,需:\n  □ 加 sorted() 保证稳定\n  □ 或在 # 范式: 注释说明业务接受不稳定\n位置:\n$unstable\n"
fi

# 4. 自定义检查:标准库 random 无 seed
# 抓 random.{random,choice,shuffle,sample,randint,uniform,gauss,...} 但文件内无 random.seed(
# ruff NPY002 只管 numpy.random,标准库 random 这里补
random_calls=$(grep -nE '(^|[^a-zA-Z_.])random\.(random|choice|choices|shuffle|sample|randint|uniform|gauss|randrange|getrandbits|betavariate)' "$file_path" 2>/dev/null)
if [ -n "$random_calls" ]; then
  # 文件内是否有 seed 设置(random.seed / 同模块 SystemRandom)
  has_seed=$(grep -E 'random\.seed\(|SystemRandom\(' "$file_path" 2>/dev/null)
  if [ -z "$has_seed" ]; then
    violations="${violations}\n[确定性自检 — random 无 seed]\ncode.md § 5:标准库 random.* 用于业务输出需 random.seed() 或显式说明业务接受不可复现\n位置:\n$random_calls\n处置:\n  □ 文件顶部 random.seed(N) 固定种子\n  □ 改用 secrets 模块(密码学场景)\n  □ 或在调用处注释 # 范式: 确定性 — 业务接受不可复现\n"
  fi
fi

# 输出违规(如有)
if [ -n "$violations" ]; then
  echo "[hook] 文件 $file_path 工具链检查发现违规:" >&2
  printf '%b' "$violations" >&2
  echo "" >&2
  echo "[hook] 按 code.md 规则修复或在响应中显式说明豁免理由(# noqa / 注释)" >&2
fi

exit 0

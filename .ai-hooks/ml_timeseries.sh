#!/usr/bin/env bash
# PostToolUse hook: 时序 ML 三大反模式
# 覆盖:
#   E1 — train_test_split 用在时序数据(文件含 datetime / pd.to_datetime)
#   E2 — XGB / sklearn 类入口缺 random_state= (复现性)
#   E3 — .shift(-N) (未来泄漏) 与 fit/train/predict 在同一文件出现
#
# 误报控制:
#   - tests/ 跳过
#   - 必须 import sklearn / xgboost / lightgbm 才启用
#   - shift(-N) 单独不报,必须配合 fit/predict 调用才报

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
  *.py|*.ipynb) ;;
  *) exit 0 ;;
esac

case "$file_path" in
  */tests/*|*/test/*) exit 0 ;;
esac
case "$(basename "$file_path")" in
  test_*.py|*_test.py) exit 0 ;;
esac

# 必须 import sklearn / xgboost / lightgbm
relevant=$(grep -E "^(from sklearn|import sklearn|from xgboost|import xgboost|from lightgbm|import lightgbm)" "$file_path" 2>/dev/null)
[ -z "$relevant" ] && exit 0

violations=$(FILE="$file_path" python3 <<'PYEOF' 2>/dev/null
import ast, os, sys, re

try:
    src = open(os.environ['FILE'], encoding='utf-8').read()
    tree = ast.parse(src)
except Exception:
    sys.exit(0)

issues = []

# 文件是否含时序数据信号(用于 E1)
has_timeseries_hint = bool(re.search(
    r'pd\.to_datetime|DatetimeIndex|date_range|pd\.Timestamp|\.dt\.|index_col\s*=\s*[\'\"]?date',
    src
))

# 文件是否调用 fit/train/predict(用于 E3)
has_fit_call = bool(re.search(r'\.fit\s*\(|\.train\s*\(|\.predict\s*\(|cross_val_score|cross_validate', src))

# 需要 random_state 的入口名(TimeSeriesSplit 不需要,它是确定性切分)
NEEDS_SEED = {
    'train_test_split', 'KFold', 'StratifiedKFold', 'GroupKFold',
    'RepeatedKFold', 'ShuffleSplit',
    'XGBClassifier', 'XGBRegressor', 'XGBRanker',
    'LGBMClassifier', 'LGBMRegressor',
    'RandomForestClassifier', 'RandomForestRegressor',
    'GradientBoostingClassifier', 'GradientBoostingRegressor',
}

for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue

    func = node.func
    func_name = None
    if isinstance(func, ast.Name):
        func_name = func.id
    elif isinstance(func, ast.Attribute):
        func_name = func.attr

    # E1: train_test_split 用在时序
    if func_name == 'train_test_split' and has_timeseries_hint:
        kw = {k.arg for k in node.keywords if k.arg}
        # shuffle=False 是合法的(用户已意识到是时序)
        shuffle_false = any(
            k.arg == 'shuffle' and isinstance(k.value, ast.Constant) and k.value.value is False
            for k in node.keywords
        )
        if not shuffle_false:
            issues.append(f"  line {node.lineno}: train_test_split 在时序数据上(文件含 datetime/DatetimeIndex)未指定 shuffle=False — 改用 TimeSeriesSplit 或 walk-forward,否则数据泄漏")

    # E2: 缺 random_state
    if func_name in NEEDS_SEED:
        kw = {k.arg for k in node.keywords if k.arg}
        # **kwargs 形式放行
        has_double_star = any(k.arg is None for k in node.keywords)
        if not has_double_star and 'random_state' not in kw and 'seed' not in kw:
            issues.append(f"  line {node.lineno}: {func_name}(...) 缺 random_state= 参数 — SHAP/CV 跨次跑结果不可复现")

    # E3: shift(-N) 未来 shift(提示性,需 AI 自查赋值目标)
    # ast 里 -N 是 UnaryOp(USub, Constant(N)),需要单独处理
    if func_name == 'shift':
        first = node.args[0] if node.args else None
        is_negative = False
        n_val = None
        if isinstance(first, ast.UnaryOp) and isinstance(first.op, ast.USub) and isinstance(first.operand, ast.Constant) and isinstance(first.operand.value, int):
            is_negative = True
            n_val = -first.operand.value
        elif isinstance(first, ast.Constant) and isinstance(first.value, int) and first.value < 0:
            is_negative = True
            n_val = first.value
        if is_negative and has_fit_call:
            issues.append(f"  line {node.lineno}: .shift({n_val}) 未来 shift,文件含 fit/predict — 自查:该列赋给 target y(合法) 还是 feature X(泄漏)?")

for line in issues[:10]:
    print(line)
PYEOF
)

if [ -n "$violations" ]; then
  echo "" >&2
  echo "[ml_timeseries] 文件 $file_path 检测到时序 ML 反模式:" >&2
  echo "$violations" >&2
  echo "" >&2
  echo "[ml_timeseries] 处置:" >&2
  echo "    E1 — 时序数据用 TimeSeriesSplit / walk-forward,禁 train_test_split shuffle=True" >&2
  echo "    E2 — 加 random_state=42(或项目统一种子) 保证跨次复现" >&2
  echo "    E3 — shift(-N) 仅可用于构造 target y;若用于特征 X 则数据泄漏" >&2
fi

exit 0

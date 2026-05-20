#!/usr/bin/env bash
# UserPromptSubmit hook: 扫描用户 prompt 关键词,把对应规则文件路径注入上下文
# 输出走 stdout(exit 0),支持该 hook 协议的 AI 工具会把内容加到下一轮上下文里
# 不阻断,只提示。漏匹配比误匹配代价低,所以倾向"宁可不激活也不乱激活"

set -u

input=$(cat)

# 用 python 解析 JSON,避免 shell 处理多行 prompt 中的引号/换行
prompt=$(printf '%s' "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('prompt', ''), end='')
except Exception:
    pass
" 2>/dev/null)

if [ -z "$prompt" ]; then
  exit 0
fi

# === T1 状态管理(governance.md § 9.2) ===
# 探索型检测 → 写标记文件,供 exploration_gate.sh 读取
# 确认词检测 → 写确认标记,解除 gate 阻断
TASK_HASH=$(echo -n "$$_$(date +%Y%m%d)" | md5sum | cut -c1-8)

# 检测用户确认词(优先级最高,先处理)
if printf '%s' "$prompt" | grep -iqE '确认|^做$|开始|选[A-Z]|就这样|^可以$|^行$|^好$|同意|拍板|按你'; then
  touch "/tmp/ai_task_confirmed_${TASK_HASH}" 2>/dev/null
fi

# 检测探索型任务(新项目/架构决策)
if printf '%s' "$prompt" | grep -iqE '新项目|新模块|从零|架构决策|设计.*(一个|系统|方案)|搭建.*(项目|系统)'; then
  touch "/tmp/ai_task_exploratory_${TASK_HASH}" 2>/dev/null
fi

# 规则文件根路径(动态定位,hook 在 .ai-hooks/,规则在同仓库 .ai-config/rules/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_DIR="$SCRIPT_DIR/../.ai-config/rules"

# 匹配函数:模式命中即输出激活提示
# 用法: match "关键词正则" "规则文件名" "场景标签"
matched_files=""

match() {
  local pattern="$1"
  local rule_file="$2"
  local label="$3"
  if printf '%s' "$prompt" | grep -iqE "$pattern"; then
    # 去重:同一文件只激活一次
    case "$matched_files" in
      *"$rule_file"*) return ;;
    esac
    matched_files="$matched_files $rule_file"
    local full_path="$RULES_DIR/$rule_file"
    if [ -f "$full_path" ]; then
      echo "[规则激活] 检测到「$label」语境(关键词命中: $pattern),建议立即 Read 以下文件:"
      echo "  $full_path"
      echo ""
    fi
  fi
}

# === 流程层(优先级最高) ===
# 救火型:线上故障关键词
match '挂了|崩了|报警|线上.*(500|错|挂)|生产.*(事故|故障)|出事|不能用|数据.*对不上|跑不动|卡死|宕机|内存.*泄漏|OOM' \
      "flow_emergency.md" "救火型(线上故障)"

# 探索型:新项目/架构决策
match '新项目|新模块|从零|架构决策|设计.*(一个|系统|方案)|搭建.*(项目|系统)|帮我.*(设计|规划|搭)' \
      "flow_new_project.md" "探索型(新项目/架构)"

# 探索型联动:新项目通常需要风险识别,显式联动激活
match '新项目|新模块|从零|架构决策' \
      "risk_reasoning.md" "探索型联动:风险识别"

# 收敛型:老项目改动
match '重构|修.*bug|把.*改成|老代码|老项目|优化.*(代码|函数|性能)|加.*(功能|特性)|封装.*(脚本|函数)' \
      "flow_legacy_project.md" "收敛型(老项目改动)"

# 接手:理解项目
match '接手|熟悉.*(项目|代码)|这个项目.*(是|干|做)|帮我.*(看|理解)|项目.*(结构|分层)|入口.*(在哪|是什么)' \
      "onboarding.md" "接手(理解项目)"

# === 协议层 ===
# 风险识别
# - 命中条件放宽:"识别风险"/"风险点"/"风险.*识别" 都接受
# - "对抗"必须搭配角色/测试/视角等,避免"对抗评价"等 meta-query 误中
match '风险.*识别|识别.*风险|风险点|失败模式|会不会.*(挂|慢|错|丢)|对抗.*(角色|测试|视角|模拟)|反推|信任边界|攻击面' \
      "risk_reasoning.md" "风险识别协议"

# 信息引导
match '不确定.*(怎么|该|要)|帮我.*问|不知道.*怎么|有什么.*(需要|要).*确认|信息.*(缺|不全)' \
      "info_guidance.md" "信息引导漏斗"

# === 治理层 ===
match '规则|governance|治理|\.md.*(改|修|增|删)|AGENTS\.md|workflow\.md' \
      "governance.md" "规则治理"

if printf '%s' "$prompt" | grep -iqE '规则|governance|治理|\.md.*(改|修|增|删)|AGENTS\.md|workflow\.md|静态工具|下放|hook'; then
  echo "[规则激活] 规则/治理类讨论必须带反向论证:"
  echo "  - 先锚定用户原话"
  echo "  - 再说明正向收益"
  echo "  - 必须说明反向风险/什么场景下会害用户"
  echo "  - 最后给落地建议"
  echo ""
fi

# === 专题层 ===
match 'FastAPI|路由|API.*(endpoint|端点)|HTTP.*(请求|路由)|backend|后端' \
      "backend.md" "FastAPI 后端"

match 'Vue|前端|ECharts|element|\bv-(if|for|model|bind)\b|frontend' \
      "frontend.md" "Vue 前端"

match 'pyinstaller|打包.*(exe|应用)|\.exe|交付' \
      "package.md" "打包"

match 'playwright|爬虫|web.*automation|自动化.*(网页|浏览器)|browser.*automation' \
      "web-automation.md" "Web 自动化"

match 'QThread|QRunnable|PySide|PyQt|信号槽|signal.*slot|GUI|界面' \
      "gui.md" "GUI"

match 'Excel|CSV|对账|数据.*(清洗|合并|处理|迁移|归一化|对齐)' \
      "data.md" "数据处理"

match '分层|封装.*(架构|脚本)|脚本转应用|依赖.*(倒置|关系)|architecture' \
      "architecture.md" "架构"

match '思想范式|状态机.*(范式|设计)|注册表.*模式|DIP|SRP|幂等键|检查点.*(范式|模式)' \
      "code.md" "代码范式"

exit 0

# SYNC.md — 环境同步执行手册

> **使用方式**：在新机器/久未同步的机器上,把整份文件发给 Claude Code,
> 让它按"执行步骤"一步一步把环境拉到一致状态。
>
> 这份文件本身**入 git**,改一次,两边都能用。

---

## 1. 这个项目的环境契约（事实声明）

Claude 读到这里时,**不要质疑**以下事实,直接按它推进:

- **Python**: ≥3.11(`pyproject.toml` 已声明)
- **依赖管理**: 唯一真相源是 `pyproject.toml`,锁文件 `uv.lock` 入 git
  - 运行依赖: `[project.dependencies]`
  - 开发依赖: `[dependency-groups] dev`
  - **不存在 `requirements.txt`**(2026-05-18 已迁出删除)
- **包管理器**: `uv`(通过 `pipx` 安装)
- **venv 位置**: 项目根 `.venv/`(不入 git)
- **lint/类型检查工具链**: `ruff` + `mypy`,通过 `pipx` 全局安装
- **代码分析工具链**: `pydeps`(循环 import)+ `vulture`(死代码),通过 `pipx` 全局安装,被 `engineering_audit.sh` 调用
- **架构契约工具链**: `import-linter` 在**项目 venv**(`pyproject.toml [dependency-groups] dev`),被 `import_lint.sh` 调用
  - 它需要 import 项目代码解析依赖图,所以必须在能 import `app/` 的 venv 里,不走 pipx
  - 配置文件: 项目根 `.importlinter`,定义层级契约(`routers > services > models > config`)
- **lint 配置**: 项目根 `.ruff.toml` / `.mypy.ini`(入 git,**这是同步源**)
  - 家目录 `~/.ruff.toml` / `~/.mypy.ini` 是 hook 的兜底配置,不是同步源

### 1.1 Claude Code 配置同步策略(2026-05-18 二次改造)

**hook 同步**:
- hook 物理位置: 项目根 `.claude-hooks/`(入 git,**这是同步源**)
- `~/.claude/hooks/` 是**软链**指向项目 `.claude-hooks/`
- 改 hook 只需 git push/pull,无需 stage 包搬运

**规则 + CLAUDE.md 同步**(本轮新增):
- 物理位置: 项目根 `.claude-config/`(入 git,**这是同步源**)
  - `.claude-config/CLAUDE.md` ← 全局决策流程
  - `.claude-config/rules/*.md` ← 16 个规则文件(workflow / governance / flow_* / 专题)
  - `.claude-config/settings.json.template` ← 不含 token 的注册结构(入仓)
  - `.claude-config/settings.json` ← **含 token,不入仓**(.gitignore 已排除)
- 软链:
  - `~/.claude/CLAUDE.md` → `.claude-config/CLAUDE.md`
  - `~/.claude/projects/-mnt-e-python--/memory/rules` → `.claude-config/rules`
  - `~/.claude/settings.json` → `.claude-config/settings.json`(本地实文件)

**为什么规则要进仓**:
- 之前规则散在 `~/.claude/projects/-mnt-e-python--/memory/rules/`,跨电脑同步只能靠手抄/stage 包
- 进仓后改规则 = git commit,push/pull 自动同步
- 软链让 Claude Code 默认路径仍然找到文件,不改 `~/.claude/` 结构

### 1.2 hook 内部规则文件路径

`rule_activator.sh` 硬编码引用 `~/.claude/projects/-mnt-e-python--/memory/rules/<file>.md`。
本路径**不要改**——它对应着软链上文,既是 Claude 历史路径也是当前真实位置。
家电脑同步时只要软链建对,这条路径自然能跑。

### 1.3 工具链配置查找策略

`ruff_check.sh` 从被改文件目录向上找 `.ruff.toml`/`.mypy.ini`,
找到用项目级,找不到回退 `~/.ruff.toml`/`~/.mypy.ini`。

---

## 2. 执行前置:Claude 必须先确认的事

在动手之前,Claude 用只读命令探测环境(按 § 4.5 用户已授权):

```
uname -s                     # Linux=WSL/Linux 流程; MINGW*/CYGWIN*/MSYS*=Windows 流程
which uv ruff mypy pipx      # 缺哪个装哪个
python3 --version            # 或 py --version (Windows)
ls .venv 2>/dev/null         # 是否已有 venv
git status                   # 工作区是否干净(脏的话先问用户)
```

**判断分支**:
- `uname -s` 含 `Linux` → 走 § 3 (WSL/Linux)
- `uname -s` 含 `MINGW`/`MSYS`/`CYGWIN` 或在 PowerShell 里 → 走 § 4 (Windows)
- 含糊不清 → 问用户,**不要猜**

---

## 3. WSL / Linux 同步流程

### 3.1 工具链(只在缺失时装)

```bash
# pipx (PEP 668 限制,系统 Python 不能直接 pip install)
command -v pipx >/dev/null || sudo apt update && sudo apt install -y pipx
pipx ensurepath

# 核心工具
command -v uv       >/dev/null || pipx install uv
command -v ruff     >/dev/null || pipx install ruff
command -v mypy     >/dev/null || pipx install mypy

# 代码分析工具(engineering_audit hook 调用)
command -v pydeps   >/dev/null || pipx install pydeps
command -v vulture  >/dev/null || pipx install vulture
```

> 装完如果命令没找到,需要 `source ~/.bashrc` 或重开终端让 `~/.local/bin` 进 PATH。

### 3.2 项目依赖

```bash
cd /path/to/competitor_study   # WSL 标准位置: ~/project/competitor_study
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

`uv sync` 行为:
- 没有 `.venv` 会自动建(Python 版本按 pyproject `requires-python` 选)
- 完全按 `uv.lock` 装,保证复现
- **会卸掉不在 pyproject 里的包**(包括 pip 自身),这是预期行为

### 3.3 验证

```bash
.venv/bin/python -c "import fastapi, tantivy, sentence_transformers, anthropic; print('imports OK')"

# 测 hook 配置查找(应该输出项目根的 .ruff.toml 路径)
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' \
  | bash ~/.claude/hooks/ruff_check.sh 2>&1 | grep -E "config:|imports OK" | head -3
```

### 3.4 Claude Code 配置软链(首次同步必做)

> 项目仓库里 `.claude-hooks/` 和 `.claude-config/` 是真身,通过软链让 Claude Code
> 默认查找路径指向它,实现 git pull 即同步。

#### 3.4.1 hook 软链

```bash
cd /path/to/competitor_study

# 1. 备份原 hook(如果存在且不是软链)
if [ -d ~/.claude/hooks ] && [ ! -L ~/.claude/hooks ]; then
    mv ~/.claude/hooks ~/.claude/hooks.bak.$(date +%Y%m%d-%H%M%S)
fi

# 2. 如果已是软链但指向错误,先删除
[ -L ~/.claude/hooks ] && rm ~/.claude/hooks

# 3. 建软链(指向当前项目的 .claude-hooks)
ln -s "$PWD/.claude-hooks" ~/.claude/hooks

# 4. 验证
ls -la ~/.claude/hooks
# 应该看到: ~/.claude/hooks -> /path/to/competitor_study/.claude-hooks
```

#### 3.4.2 CLAUDE.md 和规则文件软链(2026-05-18 新增)

```bash
cd /path/to/competitor_study

# 1. CLAUDE.md
if [ -e ~/.claude/CLAUDE.md ] && [ ! -L ~/.claude/CLAUDE.md ]; then
    mv ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.pre-link.bak
fi
[ -L ~/.claude/CLAUDE.md ] && rm ~/.claude/CLAUDE.md
ln -s "$PWD/.claude-config/CLAUDE.md" ~/.claude/CLAUDE.md

# 2. 规则目录(rule_activator.sh 硬编码这条路径)
RULES_PARENT=~/.claude/projects/-mnt-e-python--/memory
mkdir -p "$RULES_PARENT"
if [ -e "$RULES_PARENT/rules" ] && [ ! -L "$RULES_PARENT/rules" ]; then
    mv "$RULES_PARENT/rules" "$RULES_PARENT/rules.pre-link.bak"
fi
[ -L "$RULES_PARENT/rules" ] && rm "$RULES_PARENT/rules"
ln -s "$PWD/.claude-config/rules" "$RULES_PARENT/rules"

# 3. 验证
ls -la ~/.claude/CLAUDE.md "$RULES_PARENT/rules"
ls "$RULES_PARENT/rules/" | head -5  # 应该看到 16 个 .md 文件
```

#### 3.4.3 settings.json(含 token,不进仓)

```bash
cd /path/to/competitor_study

# 1. 如果本机还没设过 settings,从 template 创建
if [ ! -f .claude-config/settings.json ]; then
    cp .claude-config/settings.json.template .claude-config/settings.json
    echo "[!] 请编辑 .claude-config/settings.json 填入你的 ANTHROPIC_AUTH_TOKEN"
    echo "    位置: env.ANTHROPIC_AUTH_TOKEN"
fi

# 2. 软链
if [ -e ~/.claude/settings.json ] && [ ! -L ~/.claude/settings.json ]; then
    mv ~/.claude/settings.json ~/.claude/settings.json.pre-link.bak
fi
[ -L ~/.claude/settings.json ] && rm ~/.claude/settings.json
ln -s "$PWD/.claude-config/settings.json" ~/.claude/settings.json

# 3. 验证 JSON 合法
python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))" && echo "settings.json 合法"
```

#### 3.4.4 测试 hook 触发

> **当前 hook 总数**:13 个 PostToolUse + 2 个 PreToolUse(Bash) + 1 个 UserPromptSubmit
>
> 详细清单见 `.claude-config/rules/workflow.md` 附录 B。

```bash
# 测 ruff_check
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' \
  | bash ~/.claude/hooks/ruff_check.sh 2>&1 | grep -E "config:" | head -1

# 测 rule_activator
echo '{"session_id":"x","prompt":"线上挂了"}' | bash ~/.claude/hooks/rule_activator.sh

# 测 engineering_audit
rm -f /tmp/eng_audit_*.done
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' \
  | bash ~/.claude/hooks/engineering_audit.sh 2>&1 | head -3

# 测 import_lint(架构契约,本项目应输出 KEPT)
rm -f /tmp/import_lint_*.done
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' \
  | bash ~/.claude/hooks/import_lint.sh 2>&1
echo "(无输出说明契约 KEPT;有输出说明发现违规)"

# 测 rename_audit(用一个真实跨文件引用的符号)
echo '{"tool_name":"Edit","tool_input":{"file_path":"'"$PWD"'/app/services/report_indexer.py","old_string":"def ingest_from_pdf(\n    pdf_path: str,\n) -> dict:\n    pass","new_string":"def index_report_pdf(\n    pdf_path: str,\n) -> dict:\n    pass"}}' \
  | bash ~/.claude/hooks/rename_audit.sh 2>&1 | head -5
# 应输出 [rename_audit] 检测到幽灵引用 + 引用位置

# 测 first_iter_lines(项目里临时建一个 60 行新 .py)
tmp_new=app/services/__test_first_iter__.py
seq 1 60 | sed 's/^/x_var/' > "$tmp_new"
echo '{"tool_input":{"file_path":"'"$PWD/$tmp_new"'"}}' | bash ~/.claude/hooks/first_iter_lines.sh 2>&1 | head -3
rm -f "$tmp_new"
# 应提示首迭代 ≤ 50 行

# 测 playwright_no_sleep
cat > /tmp/probe_pw.py << 'EOF'
from playwright.sync_api import sync_playwright
import time
def run():
    time.sleep(3)
EOF
echo '{"tool_input":{"file_path":"/tmp/probe_pw.py"}}' | bash ~/.claude/hooks/playwright_no_sleep.sh 2>&1 | head -3
rm -f /tmp/probe_pw.py

# 测 http_timeout
cat > /tmp/probe_http.py << 'EOF'
import requests
def f():
    return requests.get("https://example.com")
EOF
echo '{"tool_input":{"file_path":"/tmp/probe_http.py"}}' | bash ~/.claude/hooks/http_timeout.sh 2>&1 | head -3
rm -f /tmp/probe_http.py

# 测 fastapi_debug
cat > /tmp/probe_api.py << 'EOF'
from fastapi import FastAPI
app = FastAPI(debug=True)
EOF
echo '{"tool_input":{"file_path":"/tmp/probe_api.py"}}' | bash ~/.claude/hooks/fastapi_debug.sh 2>&1 | head -3
rm -f /tmp/probe_api.py

# 测 rag_hygiene
cat > /tmp/probe_rag.py << 'EOF'
from sentence_transformers import SentenceTransformer
embedder = SentenceTransformer("BAAI/bge-m3")
def search(text, vs):
    vec = embedder.encode(text)
    return vs.search(query_vector=vec, limit=1)
EOF
echo '{"tool_input":{"file_path":"/tmp/probe_rag.py"}}' | bash ~/.claude/hooks/rag_hygiene.sh 2>&1 | head -3
rm -f /tmp/probe_rag.py

# 测 ml_timeseries
cat > /tmp/probe_ml.py << 'EOF'
import pandas as pd
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
df = pd.read_csv("foo.csv"); df.index = pd.to_datetime(df["date"])
X_train, X_test, y_train, y_test = train_test_split(df[["close"]], df["target"], test_size=0.2)
m = XGBClassifier(); m.fit(X_train, y_train)
EOF
echo '{"tool_input":{"file_path":"/tmp/probe_ml.py"}}' | bash ~/.claude/hooks/ml_timeseries.sh 2>&1 | head -3
rm -f /tmp/probe_ml.py

# rag_drift 不容易构造测试场景(依赖 git diff),改了 EMBEDDING_MODEL/CHUNK_SIZE 时自动触发
```

### 3.5 VSCode

- 打开 `data_project.code-workspace`
- 右下角应自动选中 `.venv/bin/python`,没自动选就 `Ctrl+Shift+P` →
  `Python: Select Interpreter` → `.venv/bin/python`

---

## 4. Windows 同步流程

### 4.1 工具链(PowerShell)

```powershell
# pipx
where.exe pipx 2>$null
if ($LASTEXITCODE -ne 0) {
    py -m pip install --user pipx
    py -m pipx ensurepath
    # 重开 PowerShell
}

# 核心工具 + 代码分析工具
foreach ($t in 'uv','ruff','mypy','pydeps','vulture') {
    where.exe $t 2>$null
    if ($LASTEXITCODE -ne 0) { pipx install $t }
}
```

### 4.2 项目依赖

```powershell
cd C:\path\to\competitor_study
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4.3 Claude Code 配置目录联接(首次同步必做,2026-05-18 重写)

Windows 不能用 Linux 软链,用**目录联接 (junction)**——`mklink /J` 不需要管理员权限,
对文件用 `mklink` 硬链或 PowerShell `New-Item -ItemType SymbolicLink`(后者需开发者模式)。

#### 4.3.1 hook 联接

```powershell
cd C:\path\to\competitor_study

$hookPath = "$env:USERPROFILE\.claude\hooks"

# 1. 备份原 hook(如果存在且不是联接)
if ((Test-Path $hookPath) -and -not (Get-Item $hookPath).LinkType) {
    Move-Item $hookPath "$hookPath.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}

# 2. 如果已是联接但指向错误,先删
if ((Test-Path $hookPath) -and (Get-Item $hookPath).LinkType) {
    Remove-Item $hookPath
}

# 3. 建目录联接
cmd /c mklink /J $hookPath "$PWD\.claude-hooks"
```

#### 4.3.2 CLAUDE.md 和规则联接(本轮新增)

```powershell
cd C:\path\to\competitor_study

# CLAUDE.md(单文件用 mklink /H 硬链,不需要权限)
$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
if ((Test-Path $claudeMd) -and -not (Get-Item $claudeMd).LinkType) {
    Move-Item $claudeMd "$claudeMd.pre-link.bak"
}
if (Test-Path $claudeMd) { Remove-Item $claudeMd }
cmd /c mklink /H $claudeMd "$PWD\.claude-config\CLAUDE.md"

# 规则目录(rule_activator.sh 硬编码引用 ~/.claude/projects/-mnt-e-python--/memory/rules)
$rulesParent = "$env:USERPROFILE\.claude\projects\-mnt-e-python--\memory"
New-Item -ItemType Directory -Force -Path $rulesParent | Out-Null

$rulesPath = "$rulesParent\rules"
if ((Test-Path $rulesPath) -and -not (Get-Item $rulesPath).LinkType) {
    Move-Item $rulesPath "$rulesPath.pre-link.bak"
}
if ((Test-Path $rulesPath) -and (Get-Item $rulesPath).LinkType) {
    Remove-Item $rulesPath
}
cmd /c mklink /J $rulesPath "$PWD\.claude-config\rules"

# 验证
Get-Item $claudeMd, $rulesPath | Select-Object Name, LinkType, Target
```

#### 4.3.3 settings.json(含 token,不进仓)

```powershell
cd C:\path\to\competitor_study

# 1. 如果本机还没设过 settings,从 template 创建
if (-not (Test-Path .claude-config\settings.json)) {
    Copy-Item .claude-config\settings.json.template .claude-config\settings.json
    Write-Host "[!] 请编辑 .claude-config\settings.json 填入你的 ANTHROPIC_AUTH_TOKEN"
}

# 2. 联接
$settingsPath = "$env:USERPROFILE\.claude\settings.json"
if ((Test-Path $settingsPath) -and -not (Get-Item $settingsPath).LinkType) {
    Move-Item $settingsPath "$settingsPath.pre-link.bak"
}
if (Test-Path $settingsPath) { Remove-Item $settingsPath }
cmd /c mklink /H $settingsPath "$PWD\.claude-config\settings.json"

# 3. 验证 JSON 合法
python -c "import json; json.load(open(r'$env:USERPROFILE\.claude\settings.json'))"
```

> **WSL/Windows 共用一个项目仓库的注意事项**:
> - 同一台机器同时在 WSL 和 Windows 用同一个 git 仓库会出问题(行尾/权限混乱)
> - 建议: WSL 单独 clone 到 `~/project/`,Windows 单独 clone 到 `C:\project\`,两边 git push/pull 同步
> - 这样 WSL 的软链指向 Linux 路径,Windows 的 junction 指向 Windows 路径,各自独立

### 4.4 验证

```powershell
.venv\Scripts\python -c "import fastapi, tantivy, sentence_transformers, anthropic; print('imports OK')"

# 测 hook 触发
cmd /c "echo {`"tool_input`":{`"file_path`":`"$PWD\app\main.py`"}} | bash %USERPROFILE%\.claude\hooks\ruff_check.sh"
```

---

## 5. 常见同步任务速查

| 任务 | 命令 |
|------|------|
| 拉远端最新代码 + 同步依赖 | `git pull && uv sync` |
| 加一个运行依赖 | 改 `pyproject.toml` 的 `[project.dependencies]` → `uv sync` |
| 加一个开发依赖 | 改 `pyproject.toml` 的 `[dependency-groups] dev` → `uv sync` |
| 升级所有包到最新兼容版 | `uv lock --upgrade && uv sync` |
| 改 ruff 规则 | 改项目根 `.ruff.toml` → `git commit` → 另一台 `git pull`,**完事** |
| 改 hook 脚本 | 改项目根 `.claude-hooks/xxx.sh` → `git commit` → 另一台 `git pull`,**完事** |
| 改 CLAUDE.md / 规则文件 | 改 `.claude-config/CLAUDE.md` 或 `.claude-config/rules/*.md` → `git commit` → 另一台 `git pull`,**完事** |
| 加新 hook | 写到 `.claude-hooks/`,**用 Python 脚本一次性重写** `.claude-config/settings.json` + `settings.json.template` 的 PostToolUse 列表(见 § 6.10) |
| 加新规则文件 | 写到 `.claude-config/rules/`,在 `.claude-config/rules/workflow.md § 8` 加激活条件 |
| 改 token | 只改本机 `.claude-config/settings.json`(不入仓),不影响另一台 |

---

## 6. 故障排查

### 6.1 hook 没触发 ruff 检查

```bash
# 0. ~/.claude/hooks 是否正确指向项目仓库
ls -la ~/.claude/hooks
# 应该看到: hooks -> .../competitor_study/.claude-hooks
# 如果不是软链,按 § 3.4.1 重建
# 1. 命令存在吗
which ruff mypy
# 2. 配置文件能找到吗
ls ./.ruff.toml ~/.ruff.toml
# 3. 手动模拟 hook 输入
echo '{"tool_input":{"file_path":"./app/main.py"}}' | bash ~/.claude/hooks/ruff_check.sh
```

### 6.2 rule_activator hook 没注入规则路径

```bash
# 0. 规则目录软链是否生效
ls -la ~/.claude/projects/-mnt-e-python--/memory/rules
# 应该看到: rules -> .../competitor_study/.claude-config/rules
ls ~/.claude/projects/-mnt-e-python--/memory/rules/ | wc -l  # 应该是 16

# 1. 手动模拟
echo '{"session_id":"x","prompt":"线上挂了"}' | bash ~/.claude/hooks/rule_activator.sh
# 应该输出 [规则激活] 行,含 flow_emergency.md 路径
```

### 6.3 engineering_audit 没扫描

```bash
# 0. 工具是否装好
which pydeps vulture
# 1. /tmp 标记是否还在(6 小时 TTL,新机器一定不在)
ls /tmp/eng_audit_*.done 2>/dev/null
# 2. 项目根 .py 文件数 >= 5?
find . -name "*.py" -not -path "*/.venv/*" -not -path "*/.git/*" | wc -l
# 3. 手动模拟
rm -f /tmp/eng_audit_*.done
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' | bash ~/.claude/hooks/engineering_audit.sh
```

### 6.4 import_lint 没拦反向 import

```bash
# 0. 项目 venv 里有 lint-imports?
ls .venv/bin/lint-imports || echo "缺! 跑 uv sync 装上"
# 1. .importlinter 配置存在?
ls .importlinter
# 2. TTL 标记是否还在(5 分钟内不重跑)
ls /tmp/import_lint_*.done 2>/dev/null
# 3. 手动模拟
rm -f /tmp/import_lint_*.done
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' | bash ~/.claude/hooks/import_lint.sh
# 4. 直接跑 lint-imports 看完整输出
.venv/bin/lint-imports --config .importlinter --no-cache
```

### 6.5 `uv sync` 报"Python 版本不满足"

WSL: `uv python install 3.12`
Windows: 装 Python 3.11+ 后重跑

### 6.6 `import xxx` 失败但 `uv pip list` 显示已装

VSCode/PyCharm 没用上 venv 解释器。手动选 `.venv/bin/python`(WSL) 或
`.venv\Scripts\python.exe`(Windows)。

### 6.7 git pull 后 ruff 报新违规

预期行为——另一台机器更新了规则。两个选择:
1. 按新规则修代码
2. 觉得规则太严,改 `.ruff.toml` 加 ignore,push 回去

### 6.8 settings.json 软链断了 / token 不见了

`settings.json` **不入仓**。新机器需要:
1. `cp .claude-config/settings.json.template .claude-config/settings.json`
2. 编辑填入 `ANTHROPIC_AUTH_TOKEN`
3. `ln -s "$PWD/.claude-config/settings.json" ~/.claude/settings.json`

### 6.9 规则文件改动了但 AI 还在用旧规则

软链是 OS 层,Claude Code 不缓存规则。如果改了 `.claude-config/rules/xxx.md`:
1. 重启 Claude Code 会话(开新对话)
2. 或者用户在 prompt 里显式说"重新读 xxx.md"

### 6.10 settings.json 被 Claude Code linter 静默回滚 hook 注册

**现象**:在会话里用 Edit 工具增量改 `.claude-config/settings.json` 的 `hooks.PostToolUse.hooks[]` 列表,
有时会收到 system-reminder 提示 settings.json 被改动,然后**新加的 hook 注册条目消失了**(被回滚)。
linter 同时会把这次执行 chmod 的命令追加到 `permissions.allow`,**只剩 permissions 变长,hook 实际没注册**。

**怎么知道发生了**(三个信号,占一即怀疑):
1. 改完 Edit 后**立刻收到** `<system-reminder> Note: ...settings.json was modified, either by the user or by a linter` 这种提示
2. 同一文件你只改了 hook 列表,但 system-reminder 显示 `permissions.allow` 变长
3. 你显式跑下面这条 sanity check:
```bash
python3 -c "
import json
s = json.load(open('.claude-config/settings.json'))
hooks = s['hooks']['PostToolUse'][0]['hooks']
print('PostToolUse hook 数:', len(hooks))
for h in hooks: print('  -', h['command'].split('/')[-1])
"
# 如果数量与你预期的不一致(比如刚加的 hook 不在列表里) → 被回滚了
```

**解决**:**不要再用 Edit 增量改**,改用 Python 一次性重写完整列表。这样 linter 拿不到"增量 diff"可以挑剔,只能整体接受:
```bash
cd /path/to/competitor_study
python3 <<'PYEOF'
import json
from pathlib import Path

# 这里是你要的完整 hook 列表(改这个变量即可)
target_post = [
    "ruff_check.sh", "test_reminder.sh", "json_lint.sh",
    "engineering_audit.sh", "import_lint.sh", "rename_audit.sh",
    "first_iter_lines.sh", "playwright_no_sleep.sh",
    "http_timeout.sh", "fastapi_debug.sh",
    "rag_hygiene.sh", "rag_drift.sh", "ml_timeseries.sh",
    # 加新 hook 在这里追加文件名即可
]

for p in [".claude-config/settings.json", ".claude-config/settings.json.template"]:
    s = json.load(open(p))
    s["hooks"]["PostToolUse"] = [{
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": f"bash ~/.claude/hooks/{h}"} for h in target_post]
    }]
    Path(p).write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# 校验
s = json.load(open(".claude-config/settings.json"))
print("现 PostToolUse hooks:", len(s["hooks"]["PostToolUse"][0]["hooks"]))
PYEOF
```

**为什么 Edit 会被回滚但 Python 写入不会**:Edit 是 Claude Code 原生工具,改 settings.json 时引擎会把它当"用户配置"参与 linter;Python 通过 Bash 写入是普通文件操作,引擎不挑剔。这是经验现象,2026-05-18 多次踩坑确认。

**预防**:加新 hook 时**直接用 Python 脚本重写**,不走 Edit。文档 § 5 速查表"加新 hook"一行已更新指向本节。

---

## 7. 这份文件自己怎么维护

- 任何时候改了"环境契约"(§ 1 的事实声明),**必须**回来更新这份文件
- 加新工具/新流程,加到对应章节
- 改完 `git commit`,两台机器自动同步

> 让 Claude 维护时,可以说: **"按 SYNC.md 同步环境"** 或
> **"更新 SYNC.md 反映 XXX 变更"**。

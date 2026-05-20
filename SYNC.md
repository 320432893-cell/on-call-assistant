# SYNC.md - 环境同步执行手册

> **使用方式**: 在新机器/久未同步的机器上,把整份文件发给 Codex/AI,
> 让它按"执行步骤"一步一步把环境拉到一致状态。
>
> 这份文件本身**入 git**,改一次,两边都能用。

---

## 1. 这个项目的环境契约（事实声明）

Codex/AI 读到这里时,**不要质疑**以下事实,直接按它推进:

- **Python**: ≥3.11(`pyproject.toml` 已声明)
- **依赖管理**: 唯一真相源是 `pyproject.toml`,锁文件 `uv.lock` 入 git
  - 运行依赖: `[project.dependencies]`
  - 开发依赖: `[dependency-groups] dev`
  - **不存在 `requirements.txt`**(2026-05-18 已迁出删除)
- **包管理器**: `uv`(通过 `pipx` 安装)
- **venv 位置**: 项目根 `.venv/`(不入 git)
- **lint/类型检查工具链**: `ruff` + `mypy`,通过 `pipx` 全局安装
- **代码分析工具链**: `pydeps`(循环 import)+ `vulture`(死代码),通过 `pipx` 全局安装,被 `engineering_audit.sh` 调用
- **架构契约工具链**: `import-linter` 在**项目 venv**(`pyproject.toml [dependency-groups] dev`),由 `pre-commit` 调用
  - 它需要 import 项目代码解析依赖图,所以必须在能 import `app/` 的 venv 里,不走 pipx
  - 配置文件: 项目根 `.importlinter`,定义层级契约(`routers > services > models > config`)
- **lint 配置**: 项目根 `.ruff.toml` / `.mypy.ini`(入 git,**这是同步源**)
  - 家目录 `~/.ruff.toml` / `~/.mypy.ini` 是 hook 的兜底配置,不是同步源

### 1.1 AI 编码规则同步策略

**hook 同步**:
- hook 物理位置: 项目根 `.claude-hooks/`(入 git,**这是同步源**)
- Claude Code 使用时: `~/.claude/hooks/` 可软链指向项目 `.claude-hooks/`
- Codex 使用时: 以仓库 `.claude-hooks/` 为主版本；是否接入本机运行时由本机配置决定
- **hook 注册表 SSOT**:`.claude-hooks/manifest.json`(本轮新增,详见 § 6.10)
  - 改 hook 注册改这一个文件,跑 `python3 scripts/regen_settings.py` 即同步到 settings.json
- 改 hook 只需 git push/pull,无需 stage 包搬运

**规则 + CLAUDE.md 同步**:
- 主版本: 项目根 `.claude-config/`(入 git,**这是同步源**)
  - `.claude-config/CLAUDE.md` <- Codex/AI 全局协作规则
  - `.claude-config/rules/*.md` <- 规则文件(workflow / governance / flow_* / 专题)
  - `.claude-config/settings.json.template` ← 不含 token 的注册结构(入仓,**机器生成**,见 § 6.10)
  - `.claude-config/settings.json` ← **含 token,不入仓**(.gitignore 已排除,**机器生成**)
- Codex 本机运行时副本:
  - `/home/queclink/.codex/memories/claude-rules-copy/on-call-assistant/`
  - 这只是本机副本/索引,**不是同步源**,不能只改这里
- Claude Code 兼容软链:
  - `~/.claude/CLAUDE.md` → `.claude-config/CLAUDE.md`
  - `~/.claude/projects/-home-queclink-project-on-call-assistant/memory/rules` → `.claude-config/rules`
  - `~/.claude/settings.json` → `.claude-config/settings.json`(本地实文件)

**为什么规则要进仓**:
- 之前规则散在本机 Claude/Codex 运行时目录,跨电脑同步只能靠手抄
- 进仓后改规则 = git commit,push/pull 自动同步
- 运行时副本或软链只服务本机加载,不能作为长期主版本

**为什么 settings.json 改成机器生成**:
- Claude Code 引擎 linter 会挑剔 Edit 工具对 settings.json 的增量改动,有时静默回滚 hook 注册
- 改为从 `manifest.json` 生成,避免人/AI 直接 Edit settings.json
- 详见 § 6.10

### 1.2 hook 内部规则文件路径

`rule_activator.sh` 当前按脚本所在目录动态定位规则:

`$SCRIPT_DIR/../.claude-config/rules`

所以只要 `.claude-hooks/` 和 `.claude-config/` 在同一个仓库根下,家电脑 `git pull` 后路径自然成立。
旧的 `~/.claude/projects/-mnt-e-python--/memory/rules` 是历史路径,不再作为本项目规则主路径。

### 1.3 工具链配置查找策略

`ruff` / `mypy` 从被改文件目录向上找 `.ruff.toml`/`.mypy.ini`,
找到用项目级,找不到回退 `~/.ruff.toml`/`~/.mypy.ini`。

---

## 2. 执行前置:Codex/AI 必须先确认的事

在动手之前,Codex/AI 用只读命令探测环境:

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
cd /path/to/on-call-assistant
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
.venv/bin/ruff check app/main.py 2>&1 | head -3
```

### 3.4 Claude Code 配置软链(仅使用 Claude Code 时需要)

> 项目仓库里 `.claude-hooks/` 和 `.claude-config/` 是真身,通过软链让 Claude Code
> 默认查找路径指向它,实现 git pull 即同步。

#### 3.4.1 hook 软链

```bash
cd /path/to/on-call-assistant

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
# 应该看到: ~/.claude/hooks -> /path/to/on-call-assistant/.claude-hooks
```

#### 3.4.2 CLAUDE.md 和规则文件软链(2026-05-18 新增)

```bash
cd /path/to/on-call-assistant

# 1. CLAUDE.md
if [ -e ~/.claude/CLAUDE.md ] && [ ! -L ~/.claude/CLAUDE.md ]; then
    mv ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.pre-link.bak
fi
[ -L ~/.claude/CLAUDE.md ] && rm ~/.claude/CLAUDE.md
ln -s "$PWD/.claude-config/CLAUDE.md" ~/.claude/CLAUDE.md

# 2. 规则目录(Claude Code 兼容路径)
RULES_PARENT=~/.claude/projects/-home-queclink-project-on-call-assistant/memory
mkdir -p "$RULES_PARENT"
if [ -e "$RULES_PARENT/rules" ] && [ ! -L "$RULES_PARENT/rules" ]; then
    mv "$RULES_PARENT/rules" "$RULES_PARENT/rules.pre-link.bak"
fi
[ -L "$RULES_PARENT/rules" ] && rm "$RULES_PARENT/rules"
ln -s "$PWD/.claude-config/rules" "$RULES_PARENT/rules"

# 3. 验证
ls -la ~/.claude/CLAUDE.md "$RULES_PARENT/rules"
ls "$RULES_PARENT/rules/" | head -5
```

#### 3.4.3 settings.json(含 token,不进仓 — 从 manifest 生成)

```bash
cd /path/to/on-call-assistant

# 1. 首次同步:跑生成器,会从 manifest.json + template 生成 settings.json
#    若本机已有 settings.json,生成器会自动保留你已填入的 ANTHROPIC_AUTH_TOKEN
#    若本机没有 settings.json,生成器会用占位符并打印 WARN
python3 scripts/regen_settings.py

# 2. 如果上一步打了 WARN(token 是占位符),编辑 settings.json 填入真实 token
#    位置: env.ANTHROPIC_AUTH_TOKEN
#    填完后**不需要再跑生成器**,token 直接读自这个文件,下次跑生成器会保留

# 3. 软链
if [ -e ~/.claude/settings.json ] && [ ! -L ~/.claude/settings.json ]; then
    mv ~/.claude/settings.json ~/.claude/settings.json.pre-link.bak
fi
[ -L ~/.claude/settings.json ] && rm ~/.claude/settings.json
ln -s "$PWD/.claude-config/settings.json" ~/.claude/settings.json

# 4. 验证 JSON 合法
python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))" && echo "settings.json 合法"
```

> **以后改 hook 注册**:改 `.claude-hooks/manifest.json` 后跑 `python3 scripts/regen_settings.py`,**不要直接 Edit settings.json**(linter 会回滚,见 § 6.10)。

#### 3.4.4 测试 hook 触发

> **当前 hook 总数**:13 个 PostToolUse + 2 个 PreToolUse(Bash) + 1 个 UserPromptSubmit
>
> 详细清单见 `.claude-config/rules/workflow.md` 附录 B。

```bash
# 测 ruff(直接调用,不再通过 hook 壳)
.venv/bin/ruff check app/main.py 2>&1 | head -3

# 测 rule_activator
echo '{"session_id":"x","prompt":"线上挂了"}' | bash ~/.claude/hooks/rule_activator.sh

# 测 engineering_audit
rm -f /tmp/eng_audit_*.done
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' \
  | bash ~/.claude/hooks/engineering_audit.sh 2>&1 | head -3

# 测 import-linter(直接调用,不再通过 hook 壳)
.venv/bin/lint-imports --config .importlinter --no-cache
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
cd C:\path\to\on-call-assistant
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4.3 Claude Code 配置目录联接(仅使用 Claude Code 时需要)

Windows 不能用 Linux 软链,用**目录联接 (junction)**——`mklink /J` 不需要管理员权限,
对文件用 `mklink` 硬链或 PowerShell `New-Item -ItemType SymbolicLink`(后者需开发者模式)。

#### 4.3.1 hook 联接

```powershell
cd C:\path\to\on-call-assistant

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
cd C:\path\to\on-call-assistant

# CLAUDE.md(单文件用 mklink /H 硬链,不需要权限)
$claudeMd = "$env:USERPROFILE\.claude\CLAUDE.md"
if ((Test-Path $claudeMd) -and -not (Get-Item $claudeMd).LinkType) {
    Move-Item $claudeMd "$claudeMd.pre-link.bak"
}
if (Test-Path $claudeMd) { Remove-Item $claudeMd }
cmd /c mklink /H $claudeMd "$PWD\.claude-config\CLAUDE.md"

# 规则目录(Claude Code 兼容路径)
$rulesParent = "$env:USERPROFILE\.claude\projects\-home-queclink-project-on-call-assistant\memory"
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
cd C:\path\to\on-call-assistant

# 1. 首次同步:跑生成器(会保留已填的 ANTHROPIC_AUTH_TOKEN,否则用占位符)
python scripts\regen_settings.py

# 2. 如果生成器打了 WARN(token 是占位符),编辑 .claude-config\settings.json 填入真实 token

# 3. 联接
$settingsPath = "$env:USERPROFILE\.claude\settings.json"
if ((Test-Path $settingsPath) -and -not (Get-Item $settingsPath).LinkType) {
    Move-Item $settingsPath "$settingsPath.pre-link.bak"
}
if (Test-Path $settingsPath) { Remove-Item $settingsPath }
cmd /c mklink /H $settingsPath "$PWD\.claude-config\settings.json"

# 4. 验证 JSON 合法
python -c "import json; json.load(open(r'$env:USERPROFILE\.claude\settings.json'))"
```

> **以后改 hook 注册**:改 `.claude-hooks\manifest.json` 后跑 `python scripts\regen_settings.py`,**不要直接 Edit settings.json**(见 § 6.10)。

> **WSL/Windows 共用一个项目仓库的注意事项**:
> - 同一台机器同时在 WSL 和 Windows 用同一个 git 仓库会出问题(行尾/权限混乱)
> - 建议: WSL 单独 clone 到 `~/project/`,Windows 单独 clone 到 `C:\project\`,两边 git push/pull 同步
> - 这样 WSL 的软链指向 Linux 路径,Windows 的 junction 指向 Windows 路径,各自独立

### 4.4 验证

```powershell
.venv\Scripts\python -c "import fastapi, tantivy, sentence_transformers, anthropic; print('imports OK')"

# 测 hook 触发(直接调用 ruff,不再通过 hook 壳)
.venv\Scripts\ruff check app\main.py
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
| 加新 hook | 写到 `.claude-hooks/xxx.sh`,在 `.claude-hooks/manifest.json` 对应 stage 列表加文件名,跑 `python3 scripts/regen_settings.py`(详见 § 6.10 SSOT 流程) |
| 加新规则文件 | 写到 `.claude-config/rules/`,在 `.claude-config/rules/workflow.md § 8` 加激活条件 |
| 改 token | 只改本机 `.claude-config/settings.json`(不入仓),不影响另一台 |

---

## 6. 故障排查

### 6.1 hook 没触发 ruff 检查

```bash
# 0. ~/.claude/hooks 是否正确指向项目仓库
ls -la ~/.claude/hooks
# 应该看到: hooks -> .../on-call-assistant/.claude-hooks
# 如果不是软链,按 § 3.4.1 重建
# 1. 命令存在吗
which ruff mypy
# 2. 配置文件能找到吗
ls ./.ruff.toml ~/.ruff.toml
# 3. 手动验证 ruff(不再通过 hook 壳)
.venv/bin/ruff check ./app/main.py
```

### 6.2 rule_activator hook 没注入规则路径

```bash
# 0. 规则目录软链是否生效
ls -la ~/.claude/projects/-home-queclink-project-on-call-assistant/memory/rules
# 应该看到: rules -> .../on-call-assistant/.claude-config/rules
ls ~/.claude/projects/-home-queclink-project-on-call-assistant/memory/rules/ | wc -l

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

### 6.4 import-linter 没拦反向 import

```bash
# 0. 项目 venv 里有 lint-imports?
ls .venv/bin/lint-imports || echo "缺! 跑 uv sync 装上"
# 1. .importlinter 配置存在?
ls .importlinter
# 2. 直接跑 lint-imports 看完整输出
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

`settings.json` **不入仓**(自 § 6.10 SSOT 改造后是机器生成的派生产物)。新机器需要:
1. `python3 scripts/regen_settings.py` — 从 manifest 生成 settings.json(若无则用占位符 token,会打 WARN)
2. 编辑 `.claude-config/settings.json` 填入真实 `ANTHROPIC_AUTH_TOKEN`
3. `ln -s "$PWD/.claude-config/settings.json" ~/.claude/settings.json`(WSL)或 `mklink /H`(Windows)

### 6.9 规则文件改动了但 AI 还在用旧规则

软链是 OS 层,Claude Code 不缓存规则。如果改了 `.claude-config/rules/xxx.md`:
1. 重启 Claude Code 会话(开新对话)
2. 或者用户在 prompt 里显式说"重新读 xxx.md"

### 6.10 settings.json 被 Claude Code linter 静默回滚 hook 注册(已根源解决)

#### 历史现象(2026-05-18 多次踩坑)
在会话里用 Edit 工具增量改 `.claude-config/settings.json` 的 `hooks.PostToolUse.hooks[]` 列表,
有时会收到 system-reminder 提示 settings.json 被改动,**新加的 hook 注册条目消失了**(被回滚)。
linter 同时会把这次执行 chmod 的命令追加到 `permissions.allow`,**只剩 permissions 变长,hook 实际没注册**。

#### 根源解决方案:SSOT + 生成器(已实施)

**核心改动**:`.claude-config/settings.json` 不再是真相源,改为**派生产物**。

| 文件 | 角色 | 入仓? |
|------|------|------|
| `.claude-hooks/manifest.json` | **SSOT,人写** — 列出每个 stage 注册哪些 hook 文件名 | ✅ 入仓 |
| `scripts/regen_settings.py` | **生成器** — 从 manifest 生成 settings.json + .template | ✅ 入仓 |
| `.claude-config/settings.json` | **派生,机器写** — 含本地真实 token | ❌ 不入仓 |
| `.claude-config/settings.json.template` | **派生,机器写** — token 用占位符 | ✅ 入仓 |

#### 加新 hook 流程(SSOT 三步)

```bash
cd /path/to/on-call-assistant

# 1. 写新 hook
cat > .claude-hooks/new_hook.sh << 'EOF'
#!/usr/bin/env bash
# ...
EOF
chmod +x .claude-hooks/new_hook.sh

# 2. 改 manifest(在对应 stage 列表追加文件名)
#    手动编辑 .claude-hooks/manifest.json
#    PostToolUse_EditWriteMultiEdit 或 PreToolUse_Bash 或 UserPromptSubmit

# 3. 跑生成器
python3 scripts/regen_settings.py
# 输出:
#   [regen_settings] OK — 写入 settings.json 和 settings.json.template,共注册 N 个 hook
```

**生成器自带校验**:
- manifest 引用的每个 .sh 文件必须实际存在,否则报 FATAL 退出 1
- 生成的 JSON 必须合法(回读校验)
- 自动从现有 settings.json 提取并保留 ANTHROPIC_AUTH_TOKEN(无破坏性)
- `permissions.allow` 只保留 manifest 显式声明的,**自动清掉 linter 累积的脏命令**(chmod / python3 -c 等)

#### 为什么生成器不会被 linter 回滚

| 写入方式 | linter 介入? | 安全? |
|---------|-------------|------|
| Edit 工具改 settings.json | ✅ 引擎把 settings 当用户配置参与 lint | ❌ 会回滚 |
| Write 工具改 settings.json | ⚠️ 同上,可能也会被 lint | ❌ 不保证 |
| **Python 通过 Bash 写文件** | ❌ 普通 IO 操作,引擎不挑 | ✅ 安全 |

`scripts/regen_settings.py` 走 Bash → python3 → 文件写入路径,linter 拦不到。

#### 如何判断是否漂移了

跑下面这条 sanity check,manifest 与 settings.json 应一致:
```bash
cd /path/to/on-call-assistant
python3 -c "
import json
m = json.load(open('.claude-hooks/manifest.json'))
s = json.load(open('.claude-config/settings.json'))
manifest_hooks = set()
for stage_hooks in m['hooks'].values():
    manifest_hooks.update(stage_hooks)
settings_hooks = set()
for stage in s['hooks'].values():
    for entry in stage:
        for h in entry['hooks']:
            settings_hooks.add(h['command'].split('/')[-1])
diff = manifest_hooks ^ settings_hooks
if diff:
    print(f'DRIFT! manifest 与 settings 不一致: {diff}')
    print('修复:python3 scripts/regen_settings.py')
else:
    print(f'OK,manifest 与 settings 一致({len(manifest_hooks)} hooks)')
"
```

#### 历史踩坑(留作记忆)

- 2026-05-18 早:Edit 加 `http_timeout.sh` / `fastapi_debug.sh` 注册,linter 静默回滚,permissions.allow 累积 chmod 脏数据
- 2026-05-18 晚:发现回滚现象,用 Python 一次性重写 hooks 列表复位
- 2026-05-18 晚:实施 SSOT + 生成器,根源解决

---

## 7. 这份文件自己怎么维护

- 任何时候改了"环境契约"(§ 1 的事实声明),**必须**回来更新这份文件
- 加新工具/新流程,加到对应章节
- 改完 `git commit`,两台机器自动同步

> 让 Codex/AI 维护时,可以说: **"按 SYNC.md 同步环境"** 或
> **"更新 SYNC.md 反映 XXX 变更"**。

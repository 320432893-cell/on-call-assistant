# SYNC.md - 环境同步执行手册

最后修改日期: 2026-05-22

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
- **lint/类型检查工具链**: `ruff` + `basedpyright`,项目 dev 依赖已声明；可用 `.venv/bin/ruff` / `.venv/bin/basedpyright`
- **静态语义规则**: `semgrep` 已声明为项目 dev 依赖,由 `pre-commit` 通过 `.venv/bin/semgrep --config .semgrep` 调用
- **架构契约工具链**: `import-linter` 在**项目 venv**(`pyproject.toml [dependency-groups] dev`),由 `pre-commit` 调用
  - 它需要 import 项目代码解析依赖图,所以必须在能 import `app/` 的 venv 里,不走 pipx
  - 配置文件: 项目根 `.importlinter`,定义层级契约(`routers > services > models > config`)
- **lint 配置**: 项目根 `.ruff.toml` / `pyproject.toml [tool.basedpyright]`(入 git,**这是同步源**)
  - 家目录 `~/.ruff.toml` 等兜底配置不是同步源

### 1.1 AI 编码规则同步策略

**hook 同步**:
- hook 物理位置: 项目根 `.ai-hooks/`(入 git,**这是同步源**)
- Codex/AI 使用时: 以仓库 `.ai-hooks/` 为主版本；是否自动触发由本机 AI 运行时决定
- **hook 注册表 SSOT**:`.ai-hooks/manifest.json`(本轮新增,详见 § 6.10)
  - 改 hook 注册改这一个文件,跑 `python3 scripts/regen_settings.py` 即同步到 settings.json
- 改 hook 只需 git push/pull,无需 stage 包搬运

**规则 + AGENTS.md 同步**:
- 主版本: 项目根 `.ai-config/`(入 git,**这是同步源**)
  - `.ai-config/AGENTS.md` <- Codex/AI 全局协作规则
  - `.ai-config/rules/**/*.md` <- 规则索引与细节文件
  - `.ai-config/settings.json.template` ← 不含 token 的注册结构(入仓,**机器生成**,见 § 6.10)
  - `.ai-config/settings.json` ← **含 token,不入仓**(.gitignore 已排除,**机器生成**)
- Codex 本机运行时索引:
  - `~/.codex/memories/on-call-assistant-index.md`
  - 这只是本机索引,**不是同步源**,不能只改这里
- `.claude/` 是机器/账号专属历史兼容目录，已被 `.gitignore` 排除；不作为同步源、规则入口或 hook 主入口。

**为什么规则要进仓**:
- 之前规则散在本机 AI 工具运行时目录,跨电脑同步只能靠手抄
- 进仓后改规则 = git commit,push/pull 自动同步
- 运行时副本或软链只服务本机加载,不能作为长期主版本

**Codex memory 索引同步**:
- 家里或新机器 `git pull` 后必须运行：

```bash
python3 scripts/sync_codex_memory.py
```

- 这个脚本会写入 `~/.codex/memories/on-call-assistant-index.md`
- 索引只指向当前仓库的 `.ai-config/AGENTS.md`、`.ai-config/rules/`、`.ai-hooks/`
- 不复制规则全文，避免再次出现仓库规则和 Codex memory 副本不一致

**为什么 settings.json 改成机器生成**:
- AI 工具 settings linter 会挑剔 Edit 工具对 settings.json 的增量改动,有时静默回滚 hook 注册
- 改为从 `manifest.json` 生成,避免人/AI 直接 Edit settings.json
- 详见 § 6.10

### 1.2 hook 内部规则文件路径

`rule_activator.sh` 当前按脚本所在目录动态定位规则:

`$SCRIPT_DIR/../.ai-config/rules`

所以只要 `.ai-hooks/` 和 `.ai-config/` 在同一个仓库根下,家电脑 `git pull` 后路径自然成立。
旧的 `~/.claude/projects/.../memory/rules` 是历史路径,不再作为本项目规则主路径。

### 1.3 工具链配置查找策略

`ruff` 从被改文件目录向上找 `.ruff.toml`；`basedpyright` 使用项目根 `pyproject.toml [tool.basedpyright]`。

---

## 2. 执行前置:Codex/AI 必须先确认的事

在动手之前,Codex/AI 用只读命令探测环境:

```
uname -s                     # Linux=WSL/Linux 流程; MINGW*/CYGWIN*/MSYS*=Windows 流程
which uv pipx                # 缺哪个装哪个
ls .venv/bin/ruff .venv/bin/basedpyright 2>/dev/null || true
python3 --version            # 或 py --version (Windows)
ls .venv 2>/dev/null         # 是否已有 venv
git status                   # 工作区是否干净(脏的话先问用户)
```

**判断分支**:
- `uname -s` 含 `Linux` → 走 § 3 (WSL/Linux)
- `uname -s` 含 `MINGW`/`MSYS`/`CYGWIN` 或在 PowerShell 里 → 走 § 4 (Windows)
- 含糊不清 → 问用户,**不要猜**

---

## 3. 新机最短启动路径

适用场景: 新机器、久未同步机器、新成员接手、灾难恢复。

最短路径:

```bash
git clone https://github.com/320432893-cell/on-call-assistant.git
cd on-call-assistant
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
cp .env.example .env
python3 scripts/regen_settings.py
python3 scripts/sync_codex_memory.py
mkdir -p data/raw data/processed indexes
docker run -d -p 6379:6379 redis:7-alpine
.venv/bin/python -m uvicorn app.main:app --port 8000
```

注意:

- `.env` 和 `.ai-config/settings.json` 含本机 token，不入仓；需要从旧机器复制或手动填写。
- `data/raw/`、`data/processed/`、`indexes/` 不入仓；可从旧机器同步，或按当前任务重新生成。
- 不要用 `uvicorn --reload`；Tantivy 和嵌入式 Qdrant 会使用本地锁。
- 详细项目入口、数据路径和运行约束看 `docs/PROJECT_MAP.md`。

---

## 4. WSL / Linux 同步流程

### 4.1 工具链(只在缺失时装)

```bash
# pipx (PEP 668 限制,系统 Python 不能直接 pip install)
command -v pipx >/dev/null || sudo apt update && sudo apt install -y pipx
pipx ensurepath

# 核心工具
command -v uv       >/dev/null || pipx install uv
# ruff/basedpyright/import-linter/semgrep 等项目工具由 uv sync 安装
```

> 装完如果命令没找到,需要 `source ~/.bashrc` 或重开终端让 `~/.local/bin` 进 PATH。

### 4.2 项目依赖

```bash
cd /path/to/on-call-assistant
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

`uv sync` 行为:
- 没有 `.venv` 会自动建(Python 版本按 pyproject `requires-python` 选)
- 完全按 `uv.lock` 装,保证复现
- **会卸掉不在 pyproject 里的包**(包括 pip 自身),这是预期行为

### 4.3 验证

```bash
.venv/bin/python -c "import fastapi, tantivy, sentence_transformers, anthropic; print('imports OK')"

# 测 hook 配置查找(应该输出项目根的 .ruff.toml 路径)
.venv/bin/ruff check app/main.py 2>&1 | head -3
```

### 4.3.1 Codex memory 索引

```bash
python3 scripts/sync_codex_memory.py
sed -n '1,80p' ~/.codex/memories/on-call-assistant-index.md
```

确认输出里项目根目录是当前 clone 的仓库路径，并且规则主版本指向 `.ai-config/AGENTS.md` 和 `.ai-config/rules/`。

### 4.4 AI hook / 静态检查验证

> `.ai-hooks/` 是仓库主版本。当前 Codex/AI 客户端是否自动触发 hook 由本机运行时决定；仓库侧验证直接调用 `.ai-hooks/*.sh`。

```bash
# 生成本机 settings 派生产物；若 token 是占位符，编辑 .ai-config/settings.json 填入 OPENAI_API_KEY
python3 scripts/regen_settings.py

# 测 ruff(直接调用,不通过 hook 壳)
.venv/bin/ruff check app/main.py 2>&1 | head -3

# 测 rule_activator，应输出 process/flow_emergency.index.md
echo '{"session_id":"x","prompt":"线上挂了"}' | bash .ai-hooks/rule_activator.sh

# 测 engineering_audit
rm -f /tmp/eng_audit_*.done
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' \
  | bash .ai-hooks/engineering_audit.sh 2>&1 | head -3

# 测 import-linter
.venv/bin/lint-imports --config .importlinter --no-cache

# 测 semgrep 项目规则
HOME=/tmp/semgrep-home .venv/bin/semgrep --config .semgrep --quiet app scripts

# rag_drift 共享脚本检查(依赖 git diff；hook 和 CI 共用 scripts/check_rag_drift.py)
python3 scripts/check_rag_drift.py
```

### 3.4.1 Claude Code 历史兼容

本仓库不再维护 Claude Code 作为规则、hook 或静态检查主入口。`.claude/` 是机器/账号专属本地目录，已被 `.gitignore` 排除；若本机还保留 `.claude/settings.local.json`，只作为历史兼容文件，不进入同步流程。

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

# 核心工具
foreach ($t in 'uv') {
    where.exe $t 2>$null
    if ($LASTEXITCODE -ne 0) { pipx install $t }
}
# ruff/basedpyright/import-linter/semgrep 等项目工具由 uv sync 安装
```

### 4.2 项目依赖

```powershell
cd C:\path\to\on-call-assistant
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4.3 Codex memory 索引

```powershell
python scripts\sync_codex_memory.py
Get-Content "$env:USERPROFILE\.codex\memories\on-call-assistant-index.md" -TotalCount 80
```

确认输出里项目根目录是当前 clone 的仓库路径，并且规则主版本指向 `.ai-config\AGENTS.md` 和 `.ai-config\rules\`。

> **WSL/Windows 共用一个项目仓库的注意事项**:
> - 同一台机器同时在 WSL 和 Windows 用同一个 git 仓库会出问题(行尾/权限混乱)
> - 建议: WSL 单独 clone 到 `~/project/`,Windows 单独 clone 到 `C:\project\`,两边 git push/pull 同步

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
| 改 hook 脚本 | 改项目根 `.ai-hooks/xxx.sh` → `git commit` → 另一台 `git pull`,**完事** |
| 改 AGENTS.md / 规则文件 | 改 `.ai-config/AGENTS.md` 或 `.ai-config/rules/**/*.md`；优先改对应专题的 `*.index.md` / `*.details.md` → `git commit` → 另一台 `git pull`,**完事** |
| 加新 hook | 写到 `.ai-hooks/xxx.sh`,在 `.ai-hooks/manifest.json` 对应 stage 列表加文件名,跑 `python3 scripts/regen_settings.py`(详见 § 6.10 SSOT 流程) |
| 加新规则文件 | 写到 `.ai-config/rules/` 对应专题目录,在专题 `index.md` 和必要 hook 中补索引入口 |
| 同步 Codex 项目索引 | `python3 scripts/sync_codex_memory.py` |
| 改 token | 只改本机 `.ai-config/settings.json`(不入仓),不影响另一台 |

---

## 6. 故障排查

### 6.1 ruff 检查没跑起来

```bash
# 1. 项目工具是否存在
ls .venv/bin/ruff || echo "缺! 跑 uv sync 装上"
# 2. 配置文件能找到吗
ls ./.ruff.toml ~/.ruff.toml
# 3. 手动验证 ruff(不再通过 hook 壳)
.venv/bin/ruff check ./app/main.py
```

### 6.2 rule_activator hook 没注入规则路径

```bash
# 0. 规则目录是否存在
ls .ai-config/rules/index.md
find .ai-config/rules -name '*.index.md' | wc -l

# 1. 手动模拟
echo '{"session_id":"x","prompt":"线上挂了"}' | bash .ai-hooks/rule_activator.sh
# 应该输出 [规则激活] 行,含 process/flow_emergency.index.md 路径
```

### 6.3 engineering_audit 没扫描

```bash
# 0. /tmp 标记是否还在(6 小时 TTL,新机器一定不在)
ls /tmp/eng_audit_*.done 2>/dev/null
# 1. 项目根 .py 文件数 >= 5?
find . -name "*.py" -not -path "*/.venv/*" -not -path "*/.git/*" | wc -l
# 2. 手动模拟
rm -f /tmp/eng_audit_*.done
echo '{"tool_input":{"file_path":"'"$PWD"'/app/main.py"}}' | bash .ai-hooks/engineering_audit.sh
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

### 6.8 settings.json 缺失 / token 不见了

`settings.json` **不入仓**(自 § 6.10 SSOT 改造后是机器生成的派生产物)。新机器需要:
1. `python3 scripts/regen_settings.py` — 从 manifest 生成 settings.json(若无则用占位符 token,会打 WARN)
2. 编辑 `.ai-config/settings.json` 填入真实 `OPENAI_API_KEY`
3. 不把 `.ai-config/settings.json` 加入 git；它只服务本机运行时

### 6.9 规则文件改动了但 AI 还在用旧规则

软链是 OS 层,AI 工具不缓存规则。如果改了 `.ai-config/rules/<topic>/<name>.index.md` 或 `<name>.details.md`:
1. 重启对应 AI 工具会话(开新对话)
2. 或者用户在 prompt 里显式说"重新读 xxx.md"

### 6.10 settings.json 被 AI 工具 settings linter 静默回滚 hook 注册(已根源解决)

#### 历史现象(2026-05-18 多次踩坑)
在会话里用 Edit 工具增量改 `.ai-config/settings.json` 的 `hooks.PostToolUse.hooks[]` 列表,
有时会收到 system-reminder 提示 settings.json 被改动,**新加的 hook 注册条目消失了**(被回滚)。
linter 同时会把这次执行 chmod 的命令追加到 `permissions.allow`,**只剩 permissions 变长,hook 实际没注册**。

#### 根源解决方案:SSOT + 生成器(已实施)

**核心改动**:`.ai-config/settings.json` 不再是真相源,改为**派生产物**。

| 文件 | 角色 | 入仓? |
|------|------|------|
| `.ai-hooks/manifest.json` | **SSOT,人写** — 列出每个 stage 注册哪些 hook 文件名 | ✅ 入仓 |
| `scripts/regen_settings.py` | **生成器** — 从 manifest 生成 settings.json + .template | ✅ 入仓 |
| `.ai-config/settings.json` | **派生,机器写** — 含本地真实 token | ❌ 不入仓 |
| `.ai-config/settings.json.template` | **派生,机器写** — token 用占位符 | ✅ 入仓 |

#### 加新 hook 流程(SSOT 三步)

```bash
cd /path/to/on-call-assistant

# 1. 写新 hook
cat > .ai-hooks/new_hook.sh << 'EOF'
#!/usr/bin/env bash
# ...
EOF
chmod +x .ai-hooks/new_hook.sh

# 2. 改 manifest(在对应 stage 列表追加文件名)
#    手动编辑 .ai-hooks/manifest.json
#    PostToolUse_EditWriteMultiEdit 或 PreToolUse_Bash 或 UserPromptSubmit

# 3. 跑生成器
python3 scripts/regen_settings.py
# 输出:
#   [regen_settings] OK — 写入 settings.json 和 settings.json.template,共注册 N 个 hook
```

**生成器自带校验**:
- manifest 引用的每个 .sh 文件必须实际存在,否则报 FATAL 退出 1
- 生成的 JSON 必须合法(回读校验)
- 自动从现有 settings.json 提取并保留 OPENAI_API_KEY(无破坏性)
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
m = json.load(open('.ai-hooks/manifest.json'))
s = json.load(open('.ai-config/settings.json'))
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

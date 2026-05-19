# 新电脑 clone 后启动指南

> 适用场景:换电脑 / 新成员 / 灾难恢复
> 目标:从 `git clone` 到能跑业务,**不漏装、不漏配**

---

## 0. 前置

- 已安装:Git / Python 3.11+ / uv / pre-commit
- 已 clone 仓库:`git clone https://github.com/320432893-cell/on-call-assistant.git`
- 进入目录:`cd on-call-assistant`

---

## 1. Python 环境

```bash
# 用 uv 同步依赖(锁文件 uv.lock 已入库)
uv sync

# 激活虚拟环境
source .venv/bin/activate   # Linux/WSL
# .venv\Scripts\activate    # Windows PowerShell
```

验证:`python --version` 应匹配 `pyproject.toml` 的 `requires-python`。

---

## 2. 环境变量 `.env`

```bash
# .env.example 已入库,实际 .env 不入库(.gitignore 已排除)
cp .env.example .env

# 编辑 .env,填入真实值(token / API key / DB 连接等)
# 旧电脑直接拷贝:scp /old-machine/.env ./
```

**关键字段**:见 `.env.example` 注释。

---

## 3. Claude Code 配置

```bash
# settings.json 含 token,不入库;只入 template
# 用模板生成实际配置文件
cp .claude-config/settings.json.template .claude-config/settings.json

# 编辑 .claude-config/settings.json 填入实际 token / 路径
```

`.claude/`(本地缓存)新电脑会自动重建,不用管。

---

## 3.5 Claude Code 软链建立(关键!不建 Claude Code 看不到规则和 hook)

仓库里的 `CLAUDE.md` / 规则 / hook 不会被 Claude Code 自动加载,必须把 `~/.claude/` 下的关键路径软链到仓库内的实文件:

```bash
# 备份(若 ~/.claude/ 已有同名文件)
mv ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak 2>/dev/null
mv ~/.claude/hooks ~/.claude/hooks.bak 2>/dev/null
mv ~/.claude/settings.json ~/.claude/settings.json.bak 2>/dev/null

# 建软链(假设仓库 clone 在 /home/<user>/data_project/on-call-assistant-20260514/)
REPO=/home/$(whoami)/data_project/on-call-assistant-20260514
ln -s $REPO/.claude-config/CLAUDE.md     ~/.claude/CLAUDE.md
ln -s $REPO/.claude-hooks                ~/.claude/hooks
ln -s $REPO/.claude-config/settings.json ~/.claude/settings.json   # 注意:settings.json 实文件不入库,见 § 3
```

验证:
```bash
ls -la ~/.claude/CLAUDE.md ~/.claude/hooks ~/.claude/settings.json
# 三行都应显示 -> 指向 .claude-config / .claude-hooks 内的实路径
```

**Windows / WSL 注意**:
- WSL 用上面的 `ln -s` 即可
- 纯 Windows PowerShell 用 `New-Item -ItemType SymbolicLink`(需管理员权限),或改用硬复制(后续仓库更新得手动同步)

---

## 4. Pre-commit 钩子

```bash
# 装本地 git hook(用于提交前自动跑 ruff/mypy/detect-secrets)
pre-commit install

# 首次跑全文件验一遍(可选,确认环境正常)
pre-commit run --all-files
```

---

## 5. 数据目录

```bash
# 这些目录 .gitignore 排除,clone 不带,需要单独处理
mkdir -p data/raw data/processed indexes

# 从旧电脑同步(选其一):
# 选项 A:rsync 拷数据(推荐)
# rsync -av /old-machine/on-call-assistant/data/ ./data/
# rsync -av /old-machine/on-call-assistant/indexes/ ./indexes/

# 选项 B:重新跑数据初始化脚本
# python scripts/init_data.py
```

数据来源 / 准备方式 → 看 `PROJECT_CONTEXT.md` / `SYNC.md` / `TODO.md`。

---

## 6. IDE(可选)

- PyCharm:打开 `data_project.code-workspace` 或直接打开 `on-call-assistant-20260514/` 目录
- VSCode:`.vscode/settings.json` 已入库,扩展按 `.vscode/extensions.json`(如有)安装

---

## 7. 启动验证

```bash
# 跑测试看环境完整性
pytest -x

# 启动后端(根据实际入口)
# python -m app.main
# uvicorn app.main:app --reload
```

---

## 8. 常见问题

| 问题 | 排查 |
|---|---|
| `uv sync` 慢 | 切清华镜像:`uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| pre-commit 报 detect-secrets 失败 | 检查 `.secrets.baseline` 是否随仓库带来 |
| `.claude-config/settings.json` 缺失 | 见 § 3,从 template 复制 |
| 业务功能跑不起来,提示数据缺失 | 见 § 5,数据目录需单独同步 |
| Claude Code 无法识别规则文件 | 检查软链 `~/.claude/CLAUDE.md` → `.claude-config/CLAUDE.md` |

---

## 9. 旧电脑迁移检查清单

离开旧电脑前,确保以下东西已带走或同步:
- [ ] `.env` 文件(或里面的 token/key)
- [ ] `.claude-config/settings.json`(token 实文件)
- [ ] `data/raw/` `data/processed/` `indexes/`(数据)
- [ ] 任何放在 `.gitignore` 排除目录的实验产物
- [ ] PyCharm 个人配置(若需要)

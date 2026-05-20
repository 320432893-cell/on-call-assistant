#!/usr/bin/env python3
"""Write the Codex project memory index so it points at this repository."""

from __future__ import annotations

from pathlib import Path


PROJECT_NAME = "on-call-assistant"
REPO_ROOT = Path(__file__).resolve().parent.parent
CODEX_MEMORIES = Path.home() / ".codex" / "memories"
INDEX_PATH = CODEX_MEMORIES / f"{PROJECT_NAME}-index.md"


def build_index() -> str:
    personal_rules = Path.home() / ".codex" / "memories" / "personal-coding-rules.md"
    return f"""# {PROJECT_NAME} Codex 索引

项目根目录：`{REPO_ROOT}`

写代码时先遵守 `{personal_rules}`，再按本索引读取项目内具体规则文件。

## 规则主版本

本项目的 AI 规则主版本在仓库内，随 git 同步：

- `{REPO_ROOT / ".ai-config" / "AGENTS.md"}`
- `{REPO_ROOT / ".ai-config" / "rules"}/*.md`
- `{REPO_ROOT / ".ai-hooks"}/*.sh`
- `{REPO_ROOT / "SYNC.md"}`
- `{REPO_ROOT / "BOOTSTRAP.md"}`
- `{REPO_ROOT / "PROJECT_CONTEXT.md"}`

`~/.codex/memories` 只保存本索引，不复制规则全文。不要把 memory 副本当作规则主版本。

## 任务前读取顺序

1. 先读 `{REPO_ROOT / ".ai-config" / "AGENTS.md"}`。
2. 再按任务类型读取 `{REPO_ROOT / ".ai-config" / "rules"}` 下的对应规则。
3. 涉及同步、换机器、hook、settings 时读取 `{REPO_ROOT / "SYNC.md"}`。
4. 涉及新电脑启动或灾难恢复时读取 `{REPO_ROOT / "BOOTSTRAP.md"}`。
5. 涉及项目背景和运行约束时读取 `{REPO_ROOT / "PROJECT_CONTEXT.md"}`。

## 常用规则入口

- 通用流程/硬约束：`.ai-config/rules/workflow.md`
- 老项目改动、bug 修复、重构、首次接手：`.ai-config/rules/flow_legacy_project.md`
- 新项目、新模块、架构决策：`.ai-config/rules/flow_new_project.md`
- 规则、hook、settings、lint/CI 维护：`.ai-config/rules/flow_rule_maintenance.md`
- 规则治理和静态下沉：`.ai-config/rules/governance.md`
- 代码语义和设计范式：`.ai-config/rules/code.md`
- 架构边界：`.ai-config/rules/architecture.md`
- FastAPI / 后端：`.ai-config/rules/backend.md`
- 前端：`.ai-config/rules/frontend.md`
- GUI：`.ai-config/rules/gui.md`
- 数据处理：`.ai-config/rules/data.md`
- 打包交付：`.ai-config/rules/package.md`
- 浏览器自动化：`.ai-config/rules/web-automation.md`
- 用户可见交互：`.ai-config/rules/interaction.md`

## 项目检查命令

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run lint-imports --config .importlinter --no-cache
uv run pytest
```

## 运行约束

- 不要使用 `uvicorn --reload`；Tantivy index writer 可能产生锁冲突。
- Phase3 依赖 Redis；Redis 不可用时 `/v3/chat` 按设计返回 503。
- 修改 `LLM_PROVIDER` 后，需要重启 uvicorn 或重置 provider 单例。
- bge-m3 向量维度是 1024；更换 embedding 模型需要重建 `indexes/qdrant`。
"""


def main() -> int:
    CODEX_MEMORIES.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(build_index(), encoding="utf-8")
    print(f"[sync_codex_memory] wrote {INDEX_PATH}")
    print(f"[sync_codex_memory] repo root: {REPO_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

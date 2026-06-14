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
- `{REPO_ROOT / ".ai-config" / "rules"}`/**/*.md
- `{REPO_ROOT / ".ai-hooks"}/*.sh`
- `{REPO_ROOT / "docs" / "TOOLING_CONTRACTS.md"}`

`~/.codex/memories` 只保存本索引，不复制规则全文。不要把 memory 副本当作规则主版本。

## 任务前读取顺序

1. 先读 `{REPO_ROOT / ".ai-config" / "AGENTS.md"}`。
2. 写代码后按 `{REPO_ROOT / ".ai-config" / "AGENTS.md"}` §代码审查时机表，必要时读取 `{REPO_ROOT / ".ai-config" / "rules" / "engineering" / "code.index.md"}`。
3. 涉及同步、换机器、hook、settings 时读取 `{REPO_ROOT / "docs" / "TOOLING_CONTRACTS.md"}`。

## 常用规则入口

- 主规则 + 触发索引：`.ai-config/AGENTS.md`
- 设计模式 + 子 agent 复核：`.ai-config/rules/engineering/code.index.md`
- 跨语言（含 TS/Go）：`.ai-config/rules/engineering/polyglot.index.md`
- ML 时序 / 数据管道：`.ai-config/rules/process/modes.index.md`
- 工具 / CI / hook 契约：`.ai-config/config/tooling.registry.toml`

## 项目检查命令

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
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

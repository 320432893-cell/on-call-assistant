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
2. 新项目 / 新模块读取 `{REPO_ROOT / ".ai-config" / "rules" / "process" / "flow_new_project.index.md"}`。
3. 写代码后按 `{REPO_ROOT / ".ai-config" / "AGENTS.md"}` 的代码审查门禁，必要时读取 `{REPO_ROOT / ".ai-config" / "rules" / "engineering" / "code.index.md"}`。
4. 其他工程 / 交付规则仅在用户声明体检、审查、复盘或验收时读取对应规则。
3. 涉及同步、换机器、hook、settings 时读取 `{REPO_ROOT / "docs" / "TOOLING_CONTRACTS.md"}`。

## 常用规则入口

- 总入口：`.ai-config/rules/index.md`
- 新项目流程：`.ai-config/rules/process/flow_new_project.index.md`
- 代码审查细则：`.ai-config/rules/engineering/code.index.md`
- 工程体检专题：`.ai-config/rules/engineering/index.md`
- 交付体检专题：`.ai-config/rules/delivery/index.md`
- 规则、hook、settings、lint/CI 维护：`.ai-config/AGENTS.md`

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

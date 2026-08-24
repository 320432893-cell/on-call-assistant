# On-Call Assistant

一个基于 FastAPI 的 SOP 检索与排障助手，四个阶段递进：关键词检索 → 向量语义检索 → 带会话状态的流式 Agent → 年报 PDF 的解析与 RAG 检索。

- Phase1：基于 Tantivy 的关键词检索。
- Phase2：基于 bge-m3 和嵌入式 Qdrant 的语义检索。
- Phase3：带 Redis 会话状态的流式 Agent 对话，含 `readFile` / `writeFile` 工具。
- Phase4：面向 `market-impact-study` 的年报 PDF 解析和语义检索。

## 先说三件事

**语料不在仓库里。** SOP 原文和年报 PDF 都没有提交，所以 clone 下来直接跑，Phase1/2 的索引是空的。要看效果需要自备语料后重建索引。

**`market-impact-study/` 是什么。** 那是一个独立的金融市场影响研究项目（事件研究、归因分析、年报数据管线），Phase4 的 RAG 语料就来自它。它和 On-Call SOP 助手没有业务关系，只是共用了这套 PDF 解析与检索链路，所以放在同一个仓库里。只看助手本身，读 `app/` 即可。

**当前状态。** Phase1–3 已跑通；Phase4 目前只有检索端点，还不是生成式的 `/v4/ask`。其余已知限制逐条记在 `docs/AI_HANDOFF.md` 的风险清单里——那份是核过现状的，不是计划书。

## 文档入口

- [项目地图](docs/PROJECT_MAP.md)：稳定入口、运行路径、数据路径、易懂架构图、模块边界和 source of truth。
- [AI 接手](docs/AI_HANDOFF.md)：当前风险、未验证项和下一步安全动作。
- [工具契约](docs/TOOLING_CONTRACTS.md)：工具链、CI、pre-commit 和 AI hook/settings 的维护入口。
- [错误目录](docs/ERROR_CATALOG.md) 与 [事故记录](docs/INCIDENTS.md)：报错文案的单一来源，以及踩过的坑。

## 快速启动

```bash
uv sync
cp .env.example .env
# 在 .env 中填入 provider key。
docker run -d -p 6379:6379 redis:7-alpine
.venv/bin/python -m uvicorn app.main:app --port 8000
```

不要使用 `--reload`；Tantivy 和嵌入式 Qdrant 会使用本地存储锁。

页面：

- Phase1：http://127.0.0.1:8000/v1
- Phase2：http://127.0.0.1:8000/v2
- Phase3：http://127.0.0.1:8000/v3
- API docs：http://127.0.0.1:8000/docs

## 检查

```bash
.venv/bin/python scripts/test_phase1.py
.venv/bin/python scripts/test_phase2.py
.venv/bin/python scripts/test_phase3.py
.venv/bin/python scripts/test_report_pdf.py
.venv/bin/python scripts/test_v4_report.py
```

`scripts/test_v4_report.py` 会调用运行中的 HTTP 服务，并要求年报 chunk 已经完成入库。

## 这个仓库怎么防止自己烂掉

不是"写了测试"，而是每条约束都交给一个会报红的工具，而不是靠人记。

| 机制 | 在哪 | 它防什么 |
|---|---|---|
| 依赖方向与模块边界 | `.importlinter`、`tools/check_module_boundary.py` | 模块反向依赖、跨层 import——靠纪律守不住，交给 linter |
| 静态规则 11 条 | `.semgrep/*.yml` | 已经修过的错误形态复发。规则名就是踩过的坑：`rag-hygiene`、`http-timeout`、`no-raw-sleep`、`observability-contracts`、`playwright-robustness` |
| AI 改动约束 | `.ai-hooks/` 6 个 hook + 4 个自测 | AI 改代码时绕过约定：危险 shell、提交安全、RAG 漂移、重命名审计。**hook 自己也有测试**，见 `.ai-hooks/tests/` |
| 报错文案不漂 | `docs/ERROR_CATALOG.md` + `tests/test_error_catalog.py` | 错误信息改了但文档没跟——测试会红 |
| 检索链路漂移 | `scripts/check_rag_drift.py` + `.semgrep/rag-hygiene.yml` | 引用的 chunk/字段悄悄变了 |
| 密钥不进仓库 | `.secrets.baseline` | 提交里混进凭证 |
| 提交前 / 远端 | `.pre-commit-config.yaml`、`.ruff.toml`、`.github/workflows/ci.yml` | 本地跳过的检查，CI 上仍然跑 |
| 回归 | `tests/`（5 个 pytest）、`scripts/test_phase*.py`（5 个冒烟）、`tools/check_regression.py` | 四个 Phase 的主链路 |

**已知缺口，写在这里而不是等人发现：检索和回答质量没有评测集。** 上面这些守的是"链路没坏"，守不住"答得对不对"——那一档目前还靠人看。

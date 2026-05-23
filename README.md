# On-Call Assistant

这是一个基于 FastAPI 的 On-Call SOP 助手项目：

- Phase1：基于 Tantivy 的关键词检索。
- Phase2：基于 bge-m3 和嵌入式 Qdrant 的语义检索。
- Phase3：带 Redis 会话状态的流式 Agent 对话。
- Phase4：面向 `market-impact-study` 的年报 PDF 解析和语义检索。

## 文档入口

- [项目地图](docs/PROJECT_MAP.md)：稳定入口、运行路径、数据路径、易懂架构图、模块边界和 source of truth。
- [AI 接手](docs/AI_HANDOFF.md)：当前风险、未验证项和下一步安全动作。
- [环境同步](docs/SYNC.md)：跨机器同步、工具链、AI hook/settings 的执行手册。

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

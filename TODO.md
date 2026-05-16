# On-Call Assistant TODO

## 已交付（题面三阶段全过）

### Phase1 — 关键词搜索（30 分）
- [x] `POST /v1/documents` 文档入库
- [x] `GET /v1/search?q=...` 关键词搜索（BM25）
- [x] `GET /v1/` 搜索页面
- [x] 题面 5 用例：OOM / 故障 / replication / CDN / & 全过

### Phase2 — 语义搜索（30 分）
- [x] `GET /v2/search?q=...` 语义搜索（bge-m3 + Qdrant COSINE）
- [x] `GET /v2/` 搜索页面（首次访问自动灌库）
- [x] 命中率优化：passage 前置标题/部门/tag + query/passage 双前缀
- [x] 题面 3 用例：服务器挂了 / 黑客攻击 / 机器学习模型出问题 全过

### Phase3 — On-Call Agent（40 分）
- [x] `POST /v3/chat` SSE 流式（事件：session / state / think / tool_call / tool_result / answer / done）
- [x] `GET /v3/session/{id}` / `DELETE /v3/session/{id}` 会话查询/删除
- [x] `GET /v3/` 对话页面
- [x] 4 状态状态机：S0_IDLE → S1_PLAN → S2_TOOL → S3_GENERATE → S4_DONE
- [x] 单工具 `readFile`（路径安全：拒绝绝对路径、`..` 穿越、resolve 落点校验）
- [x] LLM Provider 抽象（3 类协议）
  - [x] AnthropicProvider（Claude）
  - [x] OpenAICompatProvider（OpenAI / DeepSeek / 通义 / Kimi / 豆包 / 智谱 等，base_url 切换）
  - [x] GeminiProvider（google-genai 新 SDK）
- [x] Redis SessionStore（TTL 1800s）
- [x] 浏览器验收 5 个题面用例

## 题面外、按 test1.md 收敛剔除的项

- ~~Phase1 `/document/{id}` 文档详情~~（题面未要求）
- ~~Phase2 `/v2/search/hybrid` 混合搜索~~（题面未要求）
- ~~Phase3 多工具 `search_sop / create_ticket / query_status`~~（题面仅允许 readFile）
- ~~Phase3 状态机 S1_COLLECT / S2_RETRIEVE~~（与题面"直答"用例冲突）

## 关键修复记录

- `fa3d3f5` Tantivy whitespace tokenizer（解决 `q=&` 题面用例）
- `8898e43` Tantivy stale lock 自愈（防 uvicorn --reload 异常退出后全部 500）
- `a9bc959` starlette TemplateResponse 新签名（解决所有页面入口 500）
- `1102f8f` HuggingFace 国内镜像 + 取消硬编码离线（解决 bge-m3 加载失败）
- `3eb3ff0` Phase2 命中率优化（passage 前置标题 + bge-m3 双侧前缀）

## 跑通前置条件（你来准备）

- [x] 本地 Redis（`redis://localhost:6379/0`）已通过 WSL 启动
- [x] `.env` 已配 LLM 凭据（OpenAI 兼容端点 + heroai.icu）
- [x] bge-m3 已通过 hf-mirror.com 拉取到本地缓存

## 启动方式

```bash
# 不带 --reload（避免 Tantivy 锁冲突）
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 三个页面入口
http://127.0.0.1:8000/v1   # 关键词搜索
http://127.0.0.1:8000/v2   # 语义搜索（首次 30-60s）
http://127.0.0.1:8000/v3   # Agent 对话
```

## 后续可做（非必需，加分项）

- [ ] Phase2 章节级 chunk（拆细粒度向量，进一步拉开分差）
- [ ] Phase3 前端 Provider 切换（dropdown 选 Claude / DeepSeek / 通义）
- [ ] Phase1 命中词高亮（snippet 用 `<mark>` 包裹）
- [ ] 把 `scripts/test_phase*.py` 重写为 pytest 风格（目前是 main() 脚本）
- [x] 清理 `requirements.txt` 中冗余的 `google-generativeai`（已被 `google-genai` 取代）

## Phase4 — 年报 RAG（market-impact-study，进行中）

**目标**：基于上市公司年报 PDF 做向量检索 + 跨年报对比 + 战略/薪酬等结构化信息提取，作为 LLM 的 RAG 上下文。

**当前状态**：Step 1 PDF 解析已完成验证，下一步灌库 + 检索接口。

### Step 1 — PDF → chunks（已完成 2026-05-16）
- [x] `pymupdf>=1.26.0` 加入 requirements
- [x] `data/raw/annual_reports/移远通信_2025.pdf` 首份样本就位（232页，PDF1.7，无加密，含 772 条书签）
- [x] `app/services/report_pdf.py` 书签驱动的章节级 chunker
  - 算法：全文拼接 + 叶子标题切片（避免同页多 chunk 文本重复的 bug）
  - 占位文本剔除（"□适用√不适用" 类模板节）
  - 表格 markdown 化 + 跨页表格去重
  - 超长 chunk 软切（max 4000 字，按段落/句号）
- [x] `scripts/test_report_pdf.py` 验证脚本
- [x] 输出 `data/processed/annual_reports/移远通信_2025/chunks.jsonl`（339 chunk，平均 531 字，693 表）
- [x] 抽样验证关键章节（战略/薪酬/风险/研发/董事）全部精准命中

### Step 2 — 灌库 + 检索接口（TODO）
- [ ] `QdrantService` 加多 collection 支持（`upsert_to(collection,...)` / `search_in(collection,...)`），不破坏 v2 旧调用
- [ ] `app/services/report_indexer.py` chunks → Qdrant `annual_reports` collection
  - chunk_id → 稳定 hash（md5），避免 `abs(hash())` 跨进程不稳
  - payload: `{company, year, section_path, section_title, page_start, page_end, snippet, tables}`
- [ ] `app/routers/v4_report.py`
  - `POST /v4/ingest`（手动触发解析+灌库；不做自动首次灌库，因为年报灌库慢且无进度反馈）
  - `GET /v4/search?q=&company=&year=&limit=`（支持 metadata filter）
  - `GET /v4/companies` 列出已灌库公司
- [ ] `scripts/test_v4_report.py` 验证检索质量（query：发展战略 / 董事薪酬 / 研发投入 / 主要风险）

### Step 3 — Agent + 前端（后续，暂不做）
- [ ] LLM 生成端（RAG prompt 设计 + 调用现有 LLMProvider）
- [ ] 跨年报对比（多次检索 + agent 编排）
- [ ] 前端 `v4_report.html`

### Phase4 决策记录
| 决策 | 选择 | 理由 |
|------|------|------|
| 项目位置 | 在当前仓库加 v4 路由（非独立项目） | 共用 embedder/vectorstore 预热成本 |
| 集合隔离 | 独立 collection `annual_reports` | metadata schema 不同；与 v2 SOP 物理隔离 |
| Chunk 边界 | TOC 叶子节点 + 标题切片 | 移远PDF 772条书签，三级粒度 ~339 chunk |
| 表格处理 | markdown 化追加到所属 chunk 末尾 | LLM 能直接读懂；不单独建表格 chunk 避免割裂上下文 |
| chunk_id 格式 | `{company}_{year}#{section_path}[#partN]` | 例：`移远通信_2025#第三节/.../(四)` |
| 灌库触发 | 手动 `POST /v4/ingest`，不自动 | 年报灌库慢（~3-5分钟），无进度反馈会卡死首次请求 |
| Agent | 暂不做，先打通核心检索 | 用户明确：核心是 RAG，agent 和前端先放 |

## 文件结构（最终）

```
on-call-assistant-20260514/
├── PROJECT_CONTEXT.md              # 接手文档（含决策记录、调用链、约束）
├── TODO.md                         # 本文件
├── README.md
├── test1.md                        # 题面
├── pyproject.toml                  # pytest pythonpath
├── conftest.py                     # 项目根 sys.path 兜底
├── .env / .env.example
├── .gitignore
├── requirements.txt
│
├── app/
│   ├── main.py                     # FastAPI 入口 + lifespan（清 stale lock）
│   ├── config/settings.py          # pydantic-settings
│   ├── models/schemas.py           # Pydantic
│   ├── routers/
│   │   ├── v1.py                   # Phase1 关键词
│   │   ├── v2.py                   # Phase2 语义（含 _build_passage_text）
│   │   └── v3.py                   # Phase3 Agent SSE
│   ├── services/
│   │   ├── preprocessor.py         # HTML → 章节 + jieba 分词
│   │   ├── indexer.py              # Tantivy（whitespace tokenizer + 锁自愈）
│   │   ├── embedder.py             # bge-m3 + is_query 双侧前缀
│   │   ├── vectorstore.py          # Qdrant（嵌入式 path 模式）
│   │   ├── session_store.py        # Redis 会话
│   │   └── agent/
│   │       ├── tools.py            # readFile + 路径安全
│   │       ├── prompts.py          # system prompt + 文件清单
│   │       ├── llm_provider.py     # 3 类 Provider
│   │       └── state_machine.py    # 4 状态状态机 + SSE 事件
│   └── templates/
│       ├── v1_search.html
│       ├── v2_search.html
│       └── v3_chat.html            # SSE 客户端
│
├── data/raw/                       # 10 份 SOP HTML + metadata.json
├── indexes/                        # 运行时生成（gitignored）
│   ├── tantivy/
│   └── qdrant/
└── scripts/
    ├── __init__.py
    ├── init_data.py
    ├── test_phase1.py
    ├── test_phase2.py
    └── test_phase3.py
```

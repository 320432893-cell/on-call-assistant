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

## Phase4 — 年报 RAG（market-impact-study 子项目）

详见 [`market-impact-study/TODO.md`](market-impact-study/TODO.md)。

**进度速览**：
- Step 1 PDF → chunks ✅ 已完成 2026-05-16（`c8598a0`），产出 339 chunk / 693 表
- Step 2 灌库 + 检索接口 ✅ 已完成 2026-05-16，实测 4/4 query 全过、18/20 命中（详见子 TODO）
- Step 3 RAG 生成 🔵 下一步开工（`POST /v4/ask` 流式 + citations）
- Step 4 Agent + 前端 ⚪ 暂不做

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

# On-Call Assistant

> 面试编程题实现（题面见 `test1.md`），三阶段递进：关键词搜索 → 语义搜索 → Agent 对话。
> 数据集：10 份 On-Call SOP HTML（数据库 / 网络 / 安全 / ML 平台等）。

---

## 一、交付状态（题面用例 100% 命中）

| Phase | 分值 | 题面用例命中 | 说明 |
| --- | --- | --- | --- |
| Phase1 关键词 | 30 | ✅ 6/6（OOM / 故障 / replication / CDN / `&` / 主从延迟） | Tantivy + BM25 |
| Phase2 语义 | 30 | ✅ 3/3（"服务器挂了"→sop-001；"黑客攻击"→sop-005；"机器学习模型出问题"→sop-008） | bge-m3 + Qdrant COSINE |
| Phase3 Agent | 40 | ✅ 浏览器全量验收 5 个 SOP 问答；`readFile` + `writeFile` 工具调用链完整 | SSE + 4 状态机 |

---

## 二、技术栈

| 组件 | 选型 | 备注 |
| --- | --- | --- |
| 后端 | FastAPI | lifespan 内做 Tantivy stale lock 自愈 |
| 全文索引 | Tantivy（python-bindings） | `whitespace` tokenizer 让 `&` / `<` 标点可索引 |
| 向量检索 | Qdrant（嵌入式 path 模式） | 维度 1024 锁定 bge-m3 |
| Embedding | bge-m3（sentence-transformers） | 通过 `HF_ENDPOINT=hf-mirror.com` 国内镜像拉取 |
| 中文分词 | jieba | passage 入索引前预切 |
| LLM | 3 类 Provider 抽象 | Anthropic / OpenAI 兼容 / Gemini（google-genai 新 SDK） |
| 会话存储 | Redis | TTL 1800s |
| 模板 | Jinja2 | 三个 Phase 各一个页面 |

---

## 三、技术亮点（设计决策摘要）

### Phase1 — 让题面"标点用例"也能命中
- **问题**：题面要求 `q=&` 必须命中"网络&CDN"类标题，但默认 tokenizer 会把 `&` 当停用词剔除。
- **方案**：`title` / `content_raw` 用 `whitespace` tokenizer 保留全部字符；路由层对纯标点 query 加 substring fallback 兜底。

### Phase2 — 命中率从"猜"到"稳"
- **passage 前置标题/部门/tag**：每条 chunk 入向量库前拼接结构化字段，拉开主题分差。
- **bge-m3 双侧前缀**：query 加 `Represent this sentence for searching: `，passage 不加 —— 题面 3 个用例从 Top3 命中跳到 Top1 命中。
- **章节级 chunk**：每篇 SOP 拆 ~12 章节,每章节一个向量,`chunk_id="sop-001#3"` 含 `section_heading`。100 篇规模下仍能精准命中具体场景。
- **去重**：召回 `limit*3` 后按 `doc_id_root` 每文档保留 Top1 章节。

### Phase3 — Agent 状态机 + SSE
- **4 状态精简版**：`S0_IDLE → S1_PLAN → S2_TOOL → S3_GENERATE → S4_DONE`,去掉与题面"直答"用例冲突的 COLLECT / RETRIEVE。
- **工具集**：`readFile` + `writeFile`(题面允许"也可以往 data/ 添加任意文件",单工具无法覆盖写操作)。**路径安全**：拒绝绝对路径、`..` 穿越,resolve 后校验落点必须在 `data/` 目录内。
- **SSE 自定义事件**:`session / state / think / tool_call / tool_result / answer / done`,前端按事件类型分别渲染。
- **暂停语义**:前端 `AbortController` + 后端 `request.is_disconnected()` 真正中断 LLM 流;已生成部分写 Redis 时加 `[已暂停]` 后缀。
- **UI 左右两栏**:左侧对话气泡 / 右侧实时调用过程,强化题面"对话过程展示工具调用过程"的要求。

---

## 四、系统架构

### 调用链

```
Phase1  GET /v1/search?q=...
  └─ TantivyIndexer.search(parse_query[title, content, content_raw])
       └─ _generate_snippet(±80 字)

Phase2  GET /v2/search?q=...
  ├─ _ensure_indexed()                       # 首次访问灌库（章节级 ~120 chunk）
  ├─ embedder.encode(q, is_query=True)       # 双侧前缀
  ├─ vectorstore.search(limit*3)
  └─ 按 doc_id_root 去重,每文档 Top1

Phase3  POST /v3/chat (SSE)
  └─ AgentStateMachine.run
       循环：S1_PLAN → 决策（LLM tool_use? / 直答?）
             → S2_TOOL → readFile / writeFile（路径校验）
             → 回 S1_PLAN（多轮）或 S3_GENERATE → S4_DONE
       事件流:session / state / think / tool_call / tool_result / answer / done
```

### 分层

| 层 | 模块 |
| --- | --- |
| API | `app/routers/v{1,2,3}.py` (HTTP / SSE / 模板) |
| Service | `app/services/{preprocessor, indexer, embedder, vectorstore, session_store}.py`（模块级单例) |
| Agent | `app/services/agent/{tools, prompts, llm_provider, state_machine}.py` |
| 引擎 | tantivy / qdrant / sentence-transformers / anthropic / openai / google-genai / redis |
| IO | `data/raw/*.html`、`indexes/{tantivy,qdrant}`、Redis |
| 配置 | `app/config/settings.py` + `.env`（pydantic-settings 单例) |

---

## 五、项目结构

```
on-call-assistant-20260514/
├── app/
│   ├── main.py                     # FastAPI + lifespan（清 stale lock）
│   ├── config/settings.py          # pydantic-settings
│   ├── models/schemas.py
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
│   │       ├── tools.py            # readFile + writeFile + 路径安全
│   │       ├── prompts.py
│   │       ├── llm_provider.py     # 3 类 Provider
│   │       └── state_machine.py    # 4 状态机 + SSE 事件
│   └── templates/{v1,v2,v3}_*.html
├── data/raw/                       # 10 份 SOP HTML + metadata.json
├── indexes/                        # 运行时生成（gitignored）
├── scripts/
│   ├── init_data.py                # 生成 SOP HTML
│   └── test_phase{1,2,3}.py        # 三阶段全链路自测
├── test1.md                        # 题面
├── PROJECT_CONTEXT.md              # 接手文档（决策记录、调用链、约束）
├── TODO.md
└── requirements.txt
```

---

## 六、快速跑通

```bash
# 1. Redis（任选其一）
docker run -d -p 6379:6379 redis:7-alpine
# 或 WSL: sudo apt install redis && sudo service redis-server start

# 2. .env 配置
cp .env.example .env
# 填 LLM_API_KEY / LLM_PROVIDER / LLM_BASE_URL 等凭据

# 3. 启动（不带 --reload，避免 Tantivy 锁冲突）
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 4. 浏览器入口
#    Phase1 关键词:  http://127.0.0.1:8000/v1
#    Phase2 语义:    http://127.0.0.1:8000/v2   （首次约 30-60s 灌库）
#    Phase3 Agent:   http://127.0.0.1:8000/v3
```

### API 端点

| 阶段 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| Phase1 | POST | `/v1/documents` | 文档入库 |
| Phase1 | GET | `/v1/search?q=...` | 关键词搜索（BM25） |
| Phase2 | GET | `/v2/search?q=...` | 语义搜索（首次自动灌库） |
| Phase3 | POST | `/v3/chat` | Agent SSE 流式对话 |
| Phase3 | GET / DELETE | `/v3/session/{id}` | 会话查询 / 删除 |
| 公共 | GET | `/health` | 存活检查 |

---

## 七、已知约束

1. **uvicorn 不要用 `--reload`**：Tantivy IndexWriter 同一目录全局唯一,reload 时旧 worker 锁未释放会 LockBusy。已在 `main.py` lifespan 加 stale lock 自愈兜底,但 reload 模式下仍可能踩坑。
2. **Phase3 强依赖 Redis**：不可用时 `/v3/chat` 返回 503（按设计阻断而非降级）。
3. **bge-m3 首次拉取约 2GB**：用 `HF_ENDPOINT=https://hf-mirror.com` 国内镜像。
4. **Qdrant 维度锁定 1024**：来自 bge-m3。换模型必须 `rm -rf indexes/qdrant` 重建。
5. **Provider 单例缓存**：切 `.env` 中 `LLM_PROVIDER` 需重启 uvicorn 或调 `reset_llm_provider()`。
6. **Windows 控制台 GBK**：`scripts/test_phase*.py` 已加 `sys.stdout.reconfigure(encoding="utf-8")` 兜底。

---

## 八、关键修复记录

```
84737d6  feat: 章节级 chunk + UI 左右两栏 + 暂停按钮
6533567  feat: 适配官方 SOP HTML 结构 + writeFile 工具 + & 标点 fallback
3eb3ff0  feat(v2): 语义检索命中率优化（标题/部门/tag 前置 + bge-m3 双侧前缀）
1102f8f  fix(embedder): 关闭硬编码离线 + hf-mirror 镜像
a9bc959  fix(templates): TemplateResponse 新签名（解决 /v{1,2,3}/ 全部 500）
8898e43  fix(indexer): Tantivy stale lock 自愈
fa3d3f5  fix(indexer): 标点用例 `&` 命中（whitespace tokenizer）
```

---

## 九、后续可做（非必需）

- Phase3 启动时先 `readFile('_catalog.md')` 查目录,SOP 规模扩到 100 篇时省 token
- Phase3 前端 Provider 切换 dropdown（Claude / DeepSeek / 通义切换）
- Phase1 snippet 命中词 `<mark>` 高亮
- `scripts/test_phase*.py` 重写为 pytest 风格
- `writeFile` 后自动重建索引 hook（当前需手动清 `indexes/` 重启）

---

> 详细决策记录与调用链见 `PROJECT_CONTEXT.md`，进度清单见 `TODO.md`。

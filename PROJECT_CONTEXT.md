# PROJECT_CONTEXT — On-Call Assistant

> Claude 接手项目的最小上下文。任何修改前先核对决策记录与已知约束。

## 1. 项目定位
- 类型：面试编程题（`test1.md`）的实现，三阶段递进。
- 核心目标：基于 10 份 On-Call SOP HTML，构建关键词搜索 / 语义搜索 / Agent 助手。
- 评分：Phase1 30 + Phase2 30 + Phase3 40。
- 备注：作为产品经理面试作品，优先快速产出可运行初版。

## 2. 当前交付状态（已通过验收）

| Phase | 题面用例命中 |
| --- | --- |
| Phase1 关键词 | ✅ 6/6（OOM / 故障 / replication / CDN / & / 主从延迟） |
| Phase2 语义 | ✅ 3/3（服务器挂了 → sop-001；黑客攻击 → sop-005；机器学习模型出问题 → sop-008） |
| Phase3 Agent | ✅ 浏览器验收 5 个 SOP 问答；readFile + writeFile 两个工具完整 |

## 3. 入口清单

| 入口 | 位置 | 用途 |
| --- | --- | --- |
| FastAPI 应用 | `app/main.py:app` | uvicorn 启动入口 |
| 健康检查 | `GET /health` | 存活检查 |
| Phase1 路由 | `app/routers/v1.py` (`/v1`) | 文档入库 / 关键词搜索 / 搜索页 |
| Phase2 路由 | `app/routers/v2.py` (`/v2`) | 语义搜索 / 搜索页（首次自动灌库） |
| Phase3 路由 | `app/routers/v3.py` (`/v3`) | Agent SSE 对话 / session CRUD / 对话页 |
| 数据初始化 | `scripts/init_data.py:generate_html_files` | 10 份 SOP HTML + metadata.json |
| 三阶段测试 | `scripts/test_phase{1,2,3}.py` | 全链路自测 |

服务层公开方法（单例）：
- `get_preprocessor()` → `DocumentPreprocessor.parse_html(html, doc_id)`
- `get_indexer()` → `TantivyIndexer.{add_document, commit, search, get_document}`
- `get_embedder()` → `EmbeddingService.encode(text, is_query: bool)` ← **注意 is_query 参数**
- `get_vectorstore()` → `QdrantService.{upsert, upsert_batch, search, get, delete, count, health_check}`
- `get_session_store()` → `SessionStore.{create_session, get_history, append_message, clear_session, health_check}`
- `get_llm_provider()` → 按 `settings.LLM_PROVIDER` 返回 Anthropic / OpenAICompat / Gemini

## 4. 调用链

### Phase1 — `/v1/search?q=...`
```
v1.search_documents → TantivyIndexer.search
  ├─ parse_query(q, fields=[title, content, content_raw])
  ├─ searcher.search → hits
  └─ _generate_snippet（按 query 截取 ±80 字）
```

### Phase2 — `/v2/search?q=...`
```
v2.semantic_search
  ├─ _ensure_indexed()  # 首次访问灌库（章节级，~120 chunk）
  │   └─ 每章节生成一个向量，chunk_id="sop-001#3"，含 section_heading
  ├─ embedder.encode(q, is_query=True)
  ├─ vectorstore.search(query_vec, limit=limit*3)
  └─ 按 doc_id_root 去重，每文档保留 Top1 章节，返回 limit 条
```

### Phase3 — `/v3/chat` (SSE)
```
v3.chat → SessionStore.get_history → AgentStateMachine.run
  循环：S1_PLAN → 决策（LLM tool_use? / 直答?）
        → S2_TOOL → readFile / writeFile (路径校验)
        → 回 S1_PLAN（多轮）或 S3_GENERATE → S4_DONE
  事件流：session / state / think / tool_call / tool_result / answer / done
  SessionStore.append_message（user + assistant）
```

## 5. 层级结构

| 层 | 模块 | 职责 |
| --- | --- | --- |
| API | `app/routers/v{1,2,3}.py` | HTTP / SSE / 模板渲染 |
| Service | `app/services/{preprocessor,indexer,embedder,vectorstore,session_store}.py` | 业务能力，模块级单例 |
| Agent | `app/services/agent/{tools,prompts,llm_provider,state_machine}.py` | 工具 / prompt / 多 LLM / 4 状态机 |
| 引擎 | tantivy / qdrant / sentence-transformers / anthropic / openai / google-genai / redis | 第三方 |
| IO | `data/raw/*.html`、`indexes/{tantivy,qdrant}`、Redis | 文档 + 索引 + 会话 |
| 配置 | `app/config/settings.py` + `.env` | pydantic-settings 单例 |
| 模型 | `app/models/schemas.py` | Pydantic Schema |



## 6. 决策记录（本项目已拍板）

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| Phase3 工具集 | `readFile` + `writeFile` 两个工具 | 题面允许"也可以往 data/ 添加任意文件"，单工具无法覆盖写操作 |
| Phase3 LLM | 3 类 Provider 抽象（Anthropic / OpenAI兼容 / Gemini） | 国产模型通过 OpenAI 兼容端点 + base_url 切换 |
| Redis 会话 | 用 Redis（本地起） | 用户明确要求 |
| `/v2/search/hybrid`、`GET /document/{id}` | 删除 | 题面未要求 |
| 状态机 | 4 状态精简版（S0→S1_PLAN→S2_TOOL→S3_GENERATE→S4_DONE） | 去掉与题面冲突的 COLLECT/RETRIEVE |
| SSE 协议 | 自定义事件 think/tool_call/tool_result/answer/state/done | 前端语义清晰 |
| Tantivy schema | title、content_raw 都用 `whitespace` tokenizer | 让 `&`、`<` 等标点字符可索引 |
| Phase1 标点查询 fallback | 路由层 substring 兜底（q 仅含非字母数字时） | 官方 HTML 里 "网络&CDN" 这种粘连 token，whitespace tokenizer 切不开 |
| Embedding 工程 | passage 前置 标题/部门/标签 + bge-m3 双侧前缀（query 加、passage 不加） | 拉开主题分差，命中率显著提升 |
| preprocessor 章节抽取 | 扁平 `find_all(["h1","h2","h3","p","ul","ol","table","pre"])` | 适配官方 HTML 的 `<main><h2><h3>` 嵌套结构 |
| Phase2 章节级 chunk | 每篇拆 ~12 章节，每章节一个向量 | 100 篇文档下仍能精准命中具体场景；Phase2 命中率显著提升 |
| Phase3 UI 左右两栏 | 左对话 / 右调用过程；加暂停按钮 | 演示效果好；"对话过程展示工具调用过程"题面要求强化 |
| 暂停语义 | 前端 AbortController + 后端 `request.is_disconnected()` | 真正中断 LLM 流；已生成部分写 Redis 加 `[已暂停]` 后缀

## 7. 跑通步骤

```bash
# 1. Redis（用户本地）
docker run -d -p 6379:6379 redis:7-alpine
# 或 WSL: sudo apt install redis && sudo service redis-server start

# 2. .env（首次）
cp .env.example .env
# 填 LLM_API_KEY 等凭据

# 3. 启动（不带 --reload 避免 Tantivy 锁问题）
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 4. 浏览器访问
# Phase1 关键词:  http://127.0.0.1:8000/v1
# Phase2 语义:    http://127.0.0.1:8000/v2   （首次约 30-60s 灌库）
# Phase3 Agent:   http://127.0.0.1:8000/v3
```

## 8. 关键修复记录（commit 链）

```
84737d6  feat: 章节级 chunk + UI 左右两栏 + 暂停按钮
6533567  feat: 适配官方 SOP HTML 结构 + writeFile 工具 + & 标点 fallback
21f2021  docs: 同步终态
3eb3ff0  feat(v2): 语义检索命中率优化（标题/部门/tag前置 + bge-m3 双侧前缀）
1102f8f  fix(embedder): 关闭硬编码离线 + hf-mirror 镜像
a9bc959  fix(templates): TemplateResponse 新签名（解决 /v{1,2,3}/ 全部 500）
8898e43  fix(indexer): Tantivy stale lock 自愈（防 uvicorn --reload 异常退出）
fa3d3f5  fix(indexer): & 用例（whitespace tokenizer）
36edca5  Phase2 + Phase3 MVP + IDE/test 工程化
ba5fe32  baseline
```

## 9. ⚠️ 已知约束

1. **uvicorn 不要用 `--reload`**：Tantivy IndexWriter 同一目录全局唯一，reload 时旧 worker 锁未释放会 LockBusy。已在 `main.py` lifespan 加自动清理 stale lock 兜底，但 reload 模式下仍可能踩坑。
2. **Phase3 强依赖 Redis**：不可用时 `/v3/chat` 返回 503（按设计阻断而非降级）。
3. **Provider 单例缓存**：切 `.env` 中 `LLM_PROVIDER` 需要重启 uvicorn 或调 `reset_llm_provider()`。
4. **bge-m3 首次拉取约 2GB**：用了 `HF_ENDPOINT=https://hf-mirror.com` 国内镜像。模型存在 `~/.cache/huggingface/hub/models--BAAI--bge-m3`。
5. **Qdrant 维度锁定 1024**：来自 bge-m3。换模型必须 `rm -rf indexes/qdrant` 重建。
6. **Windows 控制台 GBK 编码**：所有 `scripts/test_phase*.py` 都加了 `sys.stdout.reconfigure(encoding="utf-8")` 兜底。
7. **Google SDK 已切到新版 `google-genai`**：`requirements.txt` 与 venv 都已清理掉旧版 `google-generativeai` 及其孤立依赖（`google-ai-generativelanguage`、`google-api-python-client`、`google-auth-httplib2`、`google-api-core`、`googleapis-common-protos`、`grpcio-status`、`httplib2`、`uritemplate`、`proto-plus`）。

## 10. 后续可做（非必需）

- Phase3 `_catalog.md`：Agent 启动时不需要看 system prompt 全文清单，先 readFile('_catalog.md') 查目录（100 篇时省 token）
- Phase3 LLM Provider 切换 UI（前端 dropdown 选 Claude / DeepSeek / 通义）
- Phase1 加 highlight 高亮（snippet 里把命中词用 `<mark>` 包起来）
- 补 pytest 用例（当前 `test_phase*.py` 是脚本风格，non-pytest）
- writeFile 后自动重建索引 hook（当前需手动 rm indexes/{tantivy,qdrant} 重启）

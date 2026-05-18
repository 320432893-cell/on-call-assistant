# market-impact-study — TODO

> 上市公司年报 RAG 子项目：基于年报 PDF 做向量检索 + 跨年报对比 + 战略/薪酬等结构化信息提取，作为 LLM 的 RAG 上下文。
>
> **代码位置**：本子项目代码物理上托管在 `on-call-assistant-20260514` 仓库内，挂在 `/v4/*` 路由与 `app/services/report_*.py`。
> 不另起仓库的理由：共用 embedder/vectorstore/llm_provider 单例与 bge-m3 预热成本。

---

## 项目目标

| 能力 | 说明 |
| --- | --- |
| A. 多年报问答 | 查"某公司在年报中说了什么"（战略、研发、薪酬等） |
| B. 跨年报对比 | 比较多家公司在同一话题上的表述/数据 |
| C. 主题/情感分析 | 识别风险措辞、战略变化、行业趋势 |
| D. 结构化信息提取 | 战略要点、部门员工薪酬、研发投入、董事会等接口拿不到的细粒度数据 |

---

## 当前状态

**Step 1 已完成（2026-05-16）** —— PDF 解析链路打通，质量验证通过。
**Step 2 已完成（2026-05-16）** —— 灌库 + 检索接口实测通过，召回 4/4 全过、18/20 命中期望关键词。
**Step 3 待开工** —— RAG 生成（`POST /v4/ask` 流式答案）。

---

## 回家继续做：从这里开始

### 当前可直接运行的状态

- 服务已通过实测：`POST /v4/ingest` → `n_indexed=339`；`scripts/test_v4_report.py` → 4/4 query 全过
- Qdrant 库里有 `annual_reports` collection，包含 移远通信_2025 的 339 chunk（重启后仍在，path 模式持久化）

### 启动复现命令（WSL）

```bash
# 终端 A：起服务（首次重启 bge-m3 reload 约 30 秒，模型已在本地缓存不会再下）
cd ~/data_project/on-call-assistant-20260514
.venv/bin/python -m uvicorn app.main:app --port 8000

# 终端 B：确认库还活着（应返回 n_indexed=339；为 0 则需重灌）
curl http://127.0.0.1:8000/v4/health

# 重灌（仅在 n_indexed=0 时需要；md5 稳定 id 重灌不会翻倍）
curl -X POST http://127.0.0.1:8000/v4/ingest \
  -H "Content-Type: application/json" \
  -d '{"company":"移远通信","year":2025}'

# 跑检索回归（4 query 应 4/4 全过）
./.venv/bin/python scripts/test_v4_report.py
```

### 下一步建议（Step 3 入口）

直接做 `POST /v4/ask`：
1. 复用 v3 `LLMProvider`（`app/services/agent/llm_provider.py`）
2. 检索 top-K（K=5 起步）→ 拼 RAG prompt（system: 仅基于上下文回答；user: query + numbered passages）
3. SSE 流式返回（参考 v3 SSE 事件结构，但状态机简化为 retrieve → generate）
4. payload 里带 `text`（完整章节）+ `tables`（markdown），LLM 上下文充足

---

## 进度清单

### Step 1 — PDF → chunks ✅ 已完成 2026-05-16

- [x] `pymupdf>=1.26.0` 加入 `requirements.txt`
- [x] `data/raw/annual_reports/移远通信_2025.pdf` 首份样本就位（232页，PDF1.7，无加密，含 772 条书签）
- [x] `app/services/report_pdf.py` 章节级 chunker
  - [x] 书签 TOC → 叶子节点
  - [x] 全文拼接 + 标题切片（修复同页多 chunk 文本重复 bug）
  - [x] 占位文本剔除（"□适用√不适用" 模板节）
  - [x] 表格 markdown 化 + 跨页表格去重
  - [x] 超长 chunk 软切（max 4000 字，按段落/句号）
- [x] `scripts/test_report_pdf.py` 验证脚本
- [x] 输出 `data/processed/annual_reports/移远通信_2025/chunks.jsonl`
  - 339 chunk / 平均 531 字 / 693 表（attach 在 chunk 上）
- [x] 抽样验证关键章节：战略 / 薪酬 / 研发 / 风险 / 董事 全部精准命中

**Step 1 commit**：`c8598a0 feat(v4): 年报 PDF 解析器（书签驱动章节切片 + 表格抽取）`

### Step 2 — 灌库 + 检索接口 ✅ 已完成 2026-05-16

决策已确认（方案 A + 手动 ingest），实施 + 实测通过：

- [x] `app/services/vectorstore.py` 加多 collection 支持（`ensure_collection` / `upsert_batch_to` / `search_in` / `count_in` / `scroll_distinct`）+ md5 稳定 `_stable_point_id`
- [x] `app/services/report_indexer.py` chunks → Qdrant `annual_reports` collection
  - passage 前置「公司 / 年度 / 章节」+ 表格 markdown 追加（沿用 v2 双侧前缀）
  - payload: `{company, year, section_path, section_title, page_start, page_end, snippet, text, tables, n_chars, has_tables}`
  - `ingest_from_pdf` / `ingest_from_jsonl` 两条入口
  - snippet 渲染时剥占位串（`√适用□不适用` 等模板，仅影响 snippet，chunk.text 主体保留）
- [x] `app/routers/v4_report.py` 全部端点改 `def`（非 async），避免 ingest 阻塞 event loop
  - `POST /v4/ingest`（优先复用已有 jsonl，缺失或 force_reparse=true 时现场解析）
  - `GET /v4/search?q=&company=&year=&limit=`（payload 等值过滤）
  - `GET /v4/companies` / `GET /v4/health`
- [x] `app/main.py` + `app/routers/__init__.py` 挂载 v4_router
- [x] `scripts/test_v4_report.py` 改为 HTTP 客户端模式（避免与 uvicorn 抢 Qdrant 嵌入式锁）
  - 4 query 实测：4/4 全过、18/20 top-5 命中、top-1 全部精准命中真实章节

**实测结果（2026-05-16）：**

| Query | top-1 命中章节 | top-1 score |
| --- | --- | --- |
| 公司未来三到五年的发展战略 | 第三节/.../(一)行业格局和趋势 | 0.556 |
| 董事和高级管理人员的薪酬情况 | 第四节/.../(三)董事、高级管理人员薪酬情况 | 0.589 |
| 研发投入金额和研发人员构成 | 第三节/.../4、研发投入 | 0.650 |
| 公司面临的主要风险有哪些 | 十、重大风险提示（指向(四)可能面对的风险） | 0.602 |

ingest 实测耗时：74.67s（339 chunk，bge-m3 单进程 CPU，模型已驻留内存）。

### Step 3 — RAG 生成 + 跨年报对比 🔵 下一步开工

- [ ] `POST /v4/ask` SSE 流式（事件：retrieve / passages / answer / done）
  - 复用 v3 `LLMProvider`（无需重写 provider 抽象）
  - retrieve top-K=5（实测向量召回已够，先不加 rerank）
  - prompt：system 约束"仅基于给定 passages 回答，无法回答时直接说明"；user 拼 numbered passages（含 section_path + page_range + text + tables）
  - 必须返回 citations（passage idx → chunk_id），前端可点击溯源
- [ ] 跨年报对比（多次检索 + 简单编排）
  - 用户 query → 拆 N 个公司分别检索 → 合并上下文 → LLM 横向对比
- [ ] 多公司年报扩展（下载并灌库其他公司，至少补 2-3 家做对比测试用）

### Step 4 — Agent + 前端 ⚪ 暂不做

- [ ] Agent 多轮工具编排（参考 v3 `state_machine.py`）
- [ ] `app/templates/v4_report.html` 前端

> 用户明确：**核心是 RAG，agent 和前端先放**。

---

## 决策记录

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 项目位置 | 当前 on-call-assistant 仓库加 `/v4/*` 路由 | 共用 embedder/vectorstore 单例预热成本；不影响面试项目交付 |
| 集合隔离 | 独立 collection `annual_reports` | metadata schema 不同；与 v2 SOP 物理隔离 |
| Chunk 边界 | TOC 叶子节点 + 标题切片 | 移远 PDF 772 条书签，三级粒度产出 ~339 chunk |
| 表格处理 | markdown 化追加到所属 chunk 末尾 | LLM 直接可读；不单独建表格 chunk 避免割裂上下文 |
| chunk_id 格式 | `{company}_{year}#{section_path}[#partN]` | 例：`移远通信_2025#第三节/.../(四)` |
| 灌库触发 | 手动 `POST /v4/ingest` | 年报灌库慢（3-5分钟），无进度反馈会卡死首次请求 |
| PDF 解析库 | PyMuPDF（pymupdf 1.27+） | 自带 TOC + find_tables；无需 OCR（可编辑 PDF） |
| Embedding | 复用 bge-m3（1024 维，双侧前缀策略） | v2 已验证中文长文本场景 |
| Agent | 暂不做 | 用户明确先打通核心 RAG |

---

## 文件结构（v4 部分）

```
on-call-assistant-20260514/
├── app/
│   ├── routers/
│   │   └── v4_report.py                 # ✅ /v4/ingest /v4/search /v4/companies /v4/health
│   └── services/
│       ├── report_pdf.py                # ✅ PDF → ReportChunk
│       ├── report_indexer.py            # ✅ chunks → Qdrant + snippet 占位串清洗
│       └── vectorstore.py               # ✅ 加多 collection 支持 + md5 稳定 point_id
├── scripts/
│   ├── test_report_pdf.py               # ✅ Step 1 验证
│   └── test_v4_report.py                # ✅ Step 2 HTTP 检索回归（4/4 通过）
├── data/
│   ├── raw/annual_reports/
│   │   └── 移远通信_2025.pdf             # ✅ 首份样本
│   └── processed/annual_reports/
│       └── 移远通信_2025/chunks.jsonl    # ✅ 339 chunk
└── market-impact-study/
    └── TODO.md                          # 本文件
```

---

## 已知约束 / 注意事项

1. **chunk_id 跨进程稳定性**：v4 已用 md5；v2 旧 `vectorstore.upsert` 仍是 `abs(hash(doc_id))`，潜伏 bug：v2 重启后 `get(doc_id)`/`delete(doc_id)` 会失效。但 v2 路由从不调它们，未爆发。如要修：5 行改动 + 清掉 `indexes/qdrant/sop_documents` 重灌 v2。
2. **跨页大表**：PyMuPDF `find_tables` 对跨页表格会在每页各识别一份，已用前 100 字签名做去重。复杂跨页财务表（合并资产负债表）可能仍丢行，Step 3 上 LLM 后实测再优化。
3. **占位章节误删**：当前用"剔除占位串后剩余 < 20 字"判断，可能误伤极短的实质内容（如纯一句话节）。如果发现召回缺失，调阈值。
4. **Qdrant 嵌入式 path 锁**：v2/v4 共用 `indexes/qdrant/`，**单进程多 collection OK；多进程会拿不到锁直接 fail**。`scripts/test_v4_report.py` 已改 HTTP 客户端模式规避。后续跑任何"独立进程也要访问 Qdrant"的脚本，要么走 HTTP，要么改 server 模式。
5. **同步端点必须 `def` 不能 `async def`**：v4 全部端点已是 `def`（FastAPI 会丢线程池跑）。`async def` + 同步阻塞调用会冻结整个 event loop（ingest 期间 health/search 全卡），这是 Step 2 实测踩过的坑。后续加端点务必沿用 `def`。
6. **uvicorn 启动目录**：必须在 `~/data_project/on-call-assistant-20260514` 下起，否则 `data/processed/...` 相对路径找不到。

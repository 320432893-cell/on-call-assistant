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
**Step 2 进行中** —— 灌库 + 检索接口（待决策两个点后开干）。

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

### Step 2 — 灌库 + 检索接口 🔵 待决策后开干

**待用户确认（电脑充电后回来确认）**：

1. **Qdrant 多 collection 改造方案**：
   - **方案A（推荐）**：`QdrantService` 加 `upsert_to(collection, ...)` / `search_in(collection, ...)`，不破坏 v2 旧调用，path 复用避免双客户端锁问题
   - 方案B：年报项目独立写 `ReportVectorStore` 类自管 Qdrant 客户端

2. **灌库触发方式**：
   - **手动 `POST /v4/ingest`（推荐）**：年报灌库慢（3-5分钟），自动首次触发会卡死请求且无进度
   - 自动触发（仿 v2 的 `_ensure_indexed`）

**确认后实施**：

- [ ] `app/services/vectorstore.py` 加多 collection 支持（按方案 A）
- [ ] `app/services/report_indexer.py` chunks → Qdrant `annual_reports` collection
  - chunk_id 用 md5 稳定 hash（替代 `abs(hash())` 跨进程不稳）
  - payload: `{company, year, section_path, section_title, page_start, page_end, snippet, tables}`
- [ ] `app/routers/v4_report.py`
  - `POST /v4/ingest`（解析 + 灌库）
  - `GET /v4/search?q=&company=&year=&limit=`（支持 metadata filter）
  - `GET /v4/companies`（列出已灌库公司）
- [ ] `scripts/test_v4_report.py` 检索质量验证
  - 4 类典型 query：发展战略 / 董事薪酬 / 研发投入 / 主要风险

### Step 3 — RAG 生成 + 跨年报对比 ⚪ 后续

- [ ] LLM 生成端（RAG prompt + 调用现有 `LLMProvider`）
- [ ] 跨年报对比（多次检索 + agent 编排）
- [ ] 多公司年报扩展（下载并灌库其他公司）

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
│   │   └── v4_report.py                 # 待写：/v4/ingest /v4/search /v4/companies
│   └── services/
│       ├── report_pdf.py                # ✅ PDF → ReportChunk
│       ├── report_indexer.py            # 待写：chunks → Qdrant
│       └── vectorstore.py               # 待改：加多 collection 支持
├── scripts/
│   ├── test_report_pdf.py               # ✅ Step 1 验证
│   └── test_v4_report.py                # 待写：Step 2 检索验证
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

1. **chunk_id 跨进程稳定性**：现有 v2 `vectorstore.upsert` 用 `abs(hash(doc_id))`，Python `PYTHONHASHSEED` 默认随机，重启后 point_id 会变。年报场景必须改 md5。
2. **跨页大表**：PyMuPDF `find_tables` 对跨页表格会在每页各识别一份，已用前 100 字签名做去重。复杂跨页财务表（合并资产负债表）可能仍丢行，Step 2 上线后实测再优化。
3. **占位章节误删**：当前用"剔除占位串后剩余 < 20 字"判断，可能误伤极短的实质内容（如纯一句话节）。如果发现召回缺失，调阈值。
4. **Qdrant 嵌入式 path 锁**：v2 已占用 `indexes/qdrant/`。多 collection 共用同一 path，单进程无锁冲突；多进程需走 server 模式。

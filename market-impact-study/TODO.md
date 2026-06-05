# TODO

## 项目背景

本项目面向 CFO 汇报，研究主题是**移为通信上市以来市值驱动因素与竞品动作对标分析**。

核心问题不是预测股价，而是回答：

- 移为通信市值变化经历了哪些阶段。
- 业绩、资本动作、管理层信号、产品创新、客户订单、风险事件分别对市值影响多大。
- 竞品做了哪些创新性动作，市场是否买账，移为能学习什么。
- 竞品正负面事件对移为是否有外溢影响。
- 哪些管理动作、披露方式和投关节奏更可能提升市场认知。

研究对象：

| 角色 | 公司 |
|---|---|
| 研究主体 | 移为通信 |
| 竞品/参照 | 移远通信、高新兴、广和通、日海智能、锐明技术、有方科技、美格智能、博实结 |

第一阶段原则：

- 数据能自动采集就自动采集，不从零人工精选。
- Tushare 做行情、市值、估值、财务和资本动作底座。
- AKShare、东方财富、巨潮等公开源做公告、研报、新闻、调研和互动问答候选池。
- PDF 用于 RAG、证据链和结构化抽取，不要求人工逐篇阅读。
- 主线以客观市值变化、相对竞品表现、关键事件证据和管理层可读结论为核心；CAR、异常市值影响和后续统计/ML 只作为辅助解释工具。

## 当前进度

截至 2026-05-26，已完成第一轮数据采集、事件/CAR 辅助底表、RAG 证据候选、中文 Top 表、数据质量校验和管理层信号台账初版。

### 已搭建脚本

| 脚本 | 用途 |
|---|---|
| `probe_tushare_availability.py` | 探测 Tushare 接口、字段、覆盖期 |
| `check_tushare_probe_quality.py` | 汇总 Tushare 空值、覆盖和单位风险 |
| `collect_tushare_data.py` | 批量落盘 Tushare 行情、估值、财务、公告标题等 |
| `probe_public_sources.py` | 探测公开免费数据源 |
| `collect_eastmoney_ir.py` | 采集东方财富机构调研/业绩说明会 |
| `collect_akshare_sources.py` | 通过 AKShare 采集公告、研报、新闻、互动易等 |
| `download_eastmoney_notice_pdfs.py` | 按关键词下载东方财富公告 PDF |
| `summarize_collected_data.py` | 汇总已采集数据清单 |
| `build_management_signal_tables.py` | 生成管理层信号台账和来源覆盖缺口 |
| `build_rag_text_source_manifest.py` | 生成第二轮统一 RAG 文本来源清单，区分 PDF、公告 API、研报、调研、互动问答和新闻 |
| `compare_rag_chunk_experiments.py` | 对比 RAG 预处理、前缀和滑动窗口实验组合的 chunk 体积和样本文本 |
| `build_rag_event_group_evidence.py` | 将候选事件级 RAG 命中增强到分析事件组和市值变化主表 |
| `build_ml_readiness_tables.py` | 生成统计/ML 建模准入诊断表，检查事件重叠、资本动作子类样本量和竞品外溢污染 |

### 已采集数据

| 来源 | 数据 | 覆盖 | 行数/文件 |
|---|---|---:|---:|
| Tushare | 日行情 | 9/9 | 19,191 |
| Tushare | 日市值、估值、换手率 | 9/9 | 19,191 |
| Tushare | 复权因子 | 9/9 | 19,671 |
| Tushare | 公告标题 | 9/9 | 26,027 |
| Tushare | 财务三表 | 9/9 | 1,394 |
| Tushare | 财务指标 | 9/9 | 523 |
| Tushare | 业绩预告/快报 | 8/9 | 301 |
| Tushare | 分红、回购、质押、股东户数 | 基本覆盖 | 5,121 |
| Tushare | 指数行情 | 4 个指数 | 15,805 |
| AKShare/巨潮 | 信息披露公告 | 9/9 | 12,854 |
| AKShare/东方财富 | 个股公告，含公告类型和链接 | 9/9 | 13,480 |
| AKShare/东方财富 | 个股研报，含 PDF 链接 | 9/9 | 606 |
| AKShare/东方财富 | 个股新闻 | 9/9 | 90 |
| 东方财富 | 机构调研/业绩说明会 | 9/9 | 885 |
| AKShare/巨潮 | 调研披露 | 7/9 | 377 |
| AKShare/互动易 | 投资者问答 | 7/9 | 170 |
| 东方财富公告 PDF | 高价值关键词公告 PDF | 697 份有效 | 约 307MB |

### 关键输出位置

| 文件/目录 | 内容 |
|---|---|
| `data/raw/tushare/` | Tushare 原始 CSV |
| `data/raw/akshare/` | AKShare 采集的公告、研报、新闻、互动问答 |
| `data/raw/eastmoney_ir/` | 东方财富机构调研和业绩说明会 |
| `data/documents/eastmoney_notice_pdfs/` | 已下载公告 PDF |
| `data/documents/eastmoney_notice_pdf_manifest.csv` | 公告 PDF 清单、状态、来源链接 |
| `data/summary/collection_inventory.csv` | 全部采集资产明细 |
| `data/summary/collection_rollup.json` | 数据源汇总 |
| `data/tushare_probe/` | Tushare 探测和质量快照 |
| `data/public_source_probe/` | 公开源探测矩阵 |
| `data/processed/top_events/` | Top 事件、竞品动作、客观市值变化和异常影响榜单 |
| `data/processed/validation/validation_report.md` | 数据质量和 CAR 抽样复算报告 |
| `data/processed/preview_report.html` | CFO 可视化报告静态预览初版 |
| `data/processed/management/management_signal_ledger.csv` | 管理层/投关/卖方/公告信号台账，5557 行数据记录 |
| `data/processed/management/management_signal_coverage_gaps.csv` | 管理层信号来源覆盖缺口，54 行来源/公司缺口记录 |
| `data/processed/rag_event_group_evidence_enhanced.csv` | 事件组级 RAG 证据增强表，覆盖 6550 个分析事件组 |
| `data/processed/rag_event_group_evidence_coverage.csv` | RAG 证据覆盖统计，按全局、公司、分类和公司-分类汇总 |
| `data/processed/rag_event_group_evidence_gaps.csv` | RAG 证据缺口诊断，按优先级列出缺口原因 |
| `data/processed/rag_text_source_manifest.csv` | 第二轮统一 RAG 文本来源清单，14406 条，含 697 条 PDF、12757 条公告 API 候选和 952 条结构化辅助来源 |
| `data/processed/rag_chunk_experiment_summary.csv` | RAG 预处理实验对比汇总，记录不同清洗/前缀/窗口组合的 chunk 数、字符数和膨胀比例 |
| `data/processed/rag_chunk_experiment_samples.csv` | RAG 预处理实验样本文本，便于人工检查前缀和清洗是否误伤 |
| `data/processed/ml_readiness/ml_readiness_summary.md` | 统计/ML 建模准入诊断摘要，记录资本动作子类、短窗干净样本和竞品外溢重叠污染 |
| `data/processed/ml_readiness/capital_action_subtype_counts.csv` | 资本动作子类样本量、公司覆盖、短窗干净样本和建模准入标签 |
| `data/processed/ml_readiness/event_overlap_summary.csv` | 事件重叠窗口汇总，覆盖全事件、CAR 成功事件、资本动作、移为自身和竞品外溢 |

### 已确认的技术事实

- 9 家公司代码和上市日已完整解析。
- Tushare 行情、估值、财务、公告标题、指数数据可用。
- `daily_basic.total_mv` 和 `circ_mv` 是万元口径，财务报表金额是元口径，后续必须统一单位。
- 东方财富公告 PDF 可由公告代码构造：

  ```text
  https://pdf.dfcfw.com/pdf/H2_{announcement_code}_1.pdf
  ```

  示例：

  ```text
  AN202605151822350865
  https://pdf.dfcfw.com/pdf/H2_AN202605151822350865_1.pdf
  ```

- PDF 下载需要校验 `%PDF` 文件头；本批 720 条高价值公告中 697 条有效，23 条为空或无效。
- 东方财富机构调研数据质量高，可直接用于管理层信号和机构关注度指标。
- 公告标题和公告类型已经足以生成自动事件候选池；公告正文/PDF 用于证据链和 RAG。

## 当前缺口

- [x] 自动事件候选池已生成：`data/processed/event_candidates.csv`。
- [x] CAR 和异常市值影响已计算：`data/processed/event_candidates_scored.csv`。
- [x] 分析事件组已生成，避免同日多附件公告重复计权：`data/processed/event_analysis_groups_scored.csv`。
- [x] 竞品事件对移为的外溢底表已生成：`data/processed/peer_spillover_to_yiwei.csv`。
- [x] RAG ingest 清单已生成：`data/processed/rag_ingest_manifest.csv`。
- [x] 公告 PDF 文本切块已生成：`data/processed/rag_notice_chunks.jsonl`。
- [x] 数据质量校验和 CAR 抽样复算已生成：`data/processed/validation/validation_report.md`。
- [x] 面向 CFO 的可视化报告静态预览初版已生成：`data/processed/preview_report.html`。
- [x] 中文字段 Top 表已生成，覆盖自身事件、竞品动作、客观市值变化、异常市值影响和 IPO 初期事件。
- [x] 管理层信号台账已生成：`data/processed/management/management_signal_ledger.csv`。
- [x] 管理层信号来源覆盖缺口已生成：`data/processed/management/management_signal_coverage_gaps.csv`。
- [x] RAG 证据已增强到事件组级市值变化主表：`data/processed/rag_event_group_evidence_enhanced.csv`。
- [x] RAG 事件组覆盖统计已生成：`data/processed/rag_event_group_evidence_coverage.csv`。
- [x] RAG 证据缺口诊断已生成：`data/processed/rag_event_group_evidence_gaps.csv`。
- [x] 交互式市值影响 dashboard 已生成：`data/processed/interactive_market_dashboard.html`。
  - 默认聚焦移为通信，展示原始总市值渐变折线和事件点。
  - 筛选链路为：时间期间 -> 月份/自定义日期 -> 事件窗口 -> 事件类型 -> 二级事件。
  - 事件点和事件表均支持加号加入多事件展示篮；事件详情保留证据链接。
  - 多公司原始值对比保留在叠加、泳道、气泡、事件对齐和下方可比矩阵，不在默认主线图中压缩展示。
- [ ] 事件分类仍是规则初版，“其他”占比高，PPT 前需人工/LLM 辅助复核 Top 事件。
- [ ] 管理层信号台账仍是自动整合初版，需围绕管理层动作、投关表达、战略表达、卖方认知和市场反应做人工/LLM 复核。
- [ ] RAG 覆盖率仍偏低：第二轮结构化文本来源补入后，6550 个分析事件组中 1167 组有 RAG 证据命中，覆盖率约 17.82%；Top 优先级事件覆盖仍低，主要缺口是公告 API 候选尚未分批抓取正文。
- [ ] 第二轮 RAG 覆盖率提升要继续补“文本来源覆盖”，不要继续堆匹配规则；当前 `rag_text_source_manifest.csv` 已生成 12757 条 `notice_api` 候选，但为避免上万次网络请求，尚未全量抓取公告页面/API 正文。
- [ ] 面向 CFO 的数据验收 HTML 页尚未生成；当前已有 Markdown/CSV 校验报告，但不是管理层可直接浏览的 dashboard。
- [ ] 报告主线需从“CAR 解释事件”调整为“客观市值变化 + 同期竞品/行业对照 + 证据链”，CAR 放到辅助列。
- [ ] 管理层信息主线需从“有多少数据”推进到“哪些管理动作/披露方式/投关节奏与市场认知变化相关”。
- [ ] 当前 CAR 使用剔除自身的竞品等权组合做基准，尚未加入指数基准、滚动 beta、市值加权和显著性检验。
- [ ] 竞品外溢已排除移为上市前事件，但早期上市初期高波动仍需在报告中单独标注。
- [x] 事件重叠窗口首轮诊断已生成：`data/processed/ml_readiness/event_overlap_summary.csv`。
- [ ] 事件重叠污染很高，分类权重只能作为候选排序和解释入口，不能直接当因果贡献；下一步需重做事件簇合并/剔除规则后再建模。
- [ ] 沪市/科创板互动问答数据不完整：移远通信、有方科技在 `cninfo_irm_questions` 采集失败，后续需用上证 e 互动或其他源补。
- [ ] 新浪评级接口全部失败，暂不作为主数据源；东方财富研报已足够支撑第一版。
- [ ] 23 条无效公告 PDF 可后续用 Playwright 或页面正文兜底，不阻塞主流程。

## 下一步任务

### 0. 立即任务：RAG 全量增强和事件-市值证据链

- [x] 将候选事件级 RAG 命中增强到分析事件组和市值变化主表：
  - `data/processed/rag_event_group_evidence_enhanced.csv`
  - `data/processed/rag_event_group_evidence_coverage.csv`
- [x] 第一轮提升事件组 RAG 覆盖率：
  - 方法：标题归一化、事件组多标题扩展、同公司近日期公告 chunk 规则挂接。
  - 结果：覆盖从 666/6550 提升到 756/6550，覆盖率约 11.54%。
  - 新增匹配方法：`direct_title_date`、`expanded_group_title`、`weak_category_date`。
  - 缺口诊断：5794 个未覆盖事件组中，5472 个缺少近日期 chunks，说明下一步应优先扩充文档来源或 manifest 挂接。
- [ ] 第二轮提升事件组 RAG 覆盖率：
  - [ ] 诊断输入：
    - 使用 `data/processed/rag_event_group_evidence_gaps.csv`，优先处理 `gap_reason=no_nearby_chunks` 且 `event_priority_score` / `objective_change_score` 高的事件组。
    - 按公司、事件分类、年份、source_type 汇总缺口，判断是 PDF 未下载、公告正文未抽取、研报/调研未入库，还是互动问答缺源。
  - [ ] 扩充文本来源，不改变 RAG 策略：
    - [x] 已有公告 PDF 继续作为强证据来源。
    - [ ] 无 PDF 或 PDF 未下载事件，优先用东方财富公告页面/API 文本兜底；已生成 `notice_api` 候选，尚未全量抓取正文。
    - [x] 研报先纳入标题、摘要、评级、机构和 PDF 链接；有 PDF 再抽正文。
    - [x] 调研/业绩说明会先纳入结构化纪要字段，保留接待对象、接待人、披露日和活动日。
    - [x] 互动问答先纳入问答正文和更新时间，沪市/科创板缺源单独标注。
  - [ ] 生成第二轮 RAG 文本 manifest / chunks：
    - [x] 新增 `data/processed/rag_text_source_manifest.csv`，统一记录来源、公司、日期、标题、文本来源强度和原始链接。
    - [x] 扩展 `data/processed/rag_notice_chunks.jsonl`，保留 `text_source` 区分 `pdf`、`notice_api`、`research_report`、`ir_record`、`irm_qa`、`news`。
    - [x] 不改变 embedding、chunk 策略、索引结构。
  - [x] 重新生成事件组证据增强表：
    - 已重跑 `build_rag_event_group_evidence.py`。
    - 覆盖率从 756/6550（约 11.54%）提升到 1167/6550（约 17.82%）；其中强证据 717 组、辅助证据 419 组、弱证据 31 组。
    - Top 优先级覆盖仍低：Top50 为 0/50、Top100 为 2/100、Top200 为 17/200，下一步应按缺口分批抓公告 API 正文。
  - [ ] 验收标准：
    - 优先看 Top 事件覆盖率，而不是只看全量覆盖率。
    - 证据分级必须保留：PDF/公告原文为强证据，研报/调研/互动问答为辅助证据，弱规则命中不能直接写入结论。
    - 抽样检查新增证据，确认不会把同公司同日无关公告误挂到事件。
- [ ] 生成“事件-市值变化-证据链”CFO 主表：
  - 每个事件组保留事件日期、公司、分类、标题、事件前市值、5/20/60 日客观市值变化、相对竞品变化、CAR 辅助列、RAG 证据状态和最佳证据摘要。
  - 按客观市值变化、优先级评分和证据状态筛出 Top 正/负事件。
  - 管理层信号复核清单只作为辅助，不作为主线。
- [x] 生成交互式市值影响 dashboard 原型：
  - 输出：`data/processed/interactive_market_dashboard.html`。
  - 生成器：`build_interactive_market_dashboard.py`。
  - 数据：使用 `data/raw/tushare/daily_basic/*.csv` 的原始总市值，单位亿元；不使用中位数或平均替代。
  - 事件：使用 `data/processed/rag_event_group_evidence_enhanced.csv`，并回填 `event_candidates_scored.csv` / `event_analysis_groups_scored.csv` 中的证据链接。
  - 当前设计决定：默认页只讲移为通信主线；竞品比较通过模式切换和矩阵承载；右侧只保留事件展示篮，不再放“市值信息概览”。
- [ ] 更新 CFO 预览报告：
  - 在 `data/processed/preview_report.html` 增加管理层信号页或管理层专题区。
  - CAR 保持辅助列，主线改成事件、客观市值变化、竞品对照和 RAG 证据链。
- [ ] 仍需生成管理层可直接浏览的数据验收 HTML 页，输出建议：
  - `data/processed/validation/data_quality_dashboard.html`
  - `data/processed/validation/data_quality_summary.csv`
- [x] 中文字段版本已覆盖主要 Top 表，字段包括：

  ```text
  event_date -> 事件日期
  company -> 公司
  primary_category -> 一级分类
  title -> 事件标题
  market_value_before -> 事件前市值
  market_value_change_1d/5d/20d/60d -> 事件后市值变化
  peer_relative_change -> 相对竞品变化
  car_p0_p20 -> CAR[0,+20]
  abnormal_mv_impact -> 异常市值影响
  evidence_url/local_pdf_path -> 证据链接/PDF路径
  ```

- [x] 运行检查：
  - 2026-06-05 已运行 `../.venv/bin/python ../tools/check.py changed`。
  - market-impact 相关检查通过：python compile、ruff、import-linter、semgrep、22 个 pytest、basedpyright、market-impact-validation。
  - 当前唯一失败为既有规则镜像问题：`AGENTS.md must mirror .ai-config/AGENTS.md exactly`，不是 dashboard 改动引入。

### 1. 生成自动事件候选池

- [x] 合并以下数据源：
  - Tushare `anns_d`
  - AKShare 东方财富个股公告
  - 东方财富研报
  - 东方财富新闻
  - 东方财富机构调研
  - 互动易问答
  - Tushare 业绩预告、快报、回购、分红
- [x] 去重并统一字段：

  ```text
  event_id
  company
  symbol
  event_date
  source_type
  title
  summary
  source_url
  local_pdf_path
  raw_category
  ```

- [x] 用规则自动分类：
  - 业绩信号
  - 资本动作
  - 管理层战略/投关信号
  - 产品/技术创新
  - 客户/订单
  - 政策/行业
  - 风险事件
  - 竞品动作
- [x] 加入关键词标签：
  - 回购、分红、股权激励、员工持股、定增、并购、减持、解禁
  - 业绩预告、业绩快报、预增、预减、亏损、扭亏
  - 投资者关系、机构调研、业绩说明会
  - 新产品、战略合作、客户、中标、订单、海外、AI、卫星通信、车联网、两轮车
  - 问询函、风险提示、诉讼、减值、商誉、存货、应收

### 2. 计算 CAR 和异常市值影响

- [x] 基于 Tushare 行情和市值数据计算日收益。
- [x] 使用剔除自身的竞品组合做第一版基准。
- [x] 事件窗口：

  ```text
  CAR[-1,+1]
  CAR[0,+5]
  CAR[0,+20]
  CAR[0,+60]
  ```

- [x] 计算异常市值影响：

  ```text
  异常市值影响 = 事件前总市值 × CAR
  ```

- [x] 标记上市前事件、行情未覆盖事件、IPO/上市流程事件、交易异常波动事件。
- [ ] 标记事件重叠窗口，避免过度归因。
  - [x] 首轮诊断已完成：`build_ml_readiness_tables.py` 输出 `data/processed/ml_readiness/`。
  - [ ] 下一步需要把诊断结果反向用于事件组重构：同公司连续公告、重组进展、股权激励解锁/注销、分红流程等应合并为事件簇或降级为描述。

### 3. 生成事件优先级评分

- [x] 建立候选事件评分：

  ```text
  事件优先级 =
  标题/公告类型权重
  + 关键词权重
  + 是否有 PDF/研报/调研跟进
  + CAR 绝对值
  + 成交额放大
  + 是否竞品创新动作
  ```

- [x] 输出：
  - 移为通信自身事件 Top 100
  - 竞品动作 Top 100
  - 正向市值影响 Top 50
  - 负向市值影响 Top 50
  - 竞品动作对移为外溢影响 Top 50

### 4. 接入 RAG 证据链

- [x] 对已下载 PDF 做文本抽取。
- [x] 生成 RAG ingest 清单：

  ```text
  document_id
  company
  symbol
  source_type
  title
  publish_date
  source_url
  local_path
  event_candidate_id
  ```

- [x] 将候选事件级 RAG 命中增强到分析事件组和市值变化主表：
  - `data/processed/rag_event_group_evidence_enhanced.csv`
  - `data/processed/rag_event_group_evidence_coverage.csv`
  - `data/processed/rag_event_group_evidence_gaps.csv`
- [ ] 将公告页面/API 文本、研报、调研纪要和互动问答正文纳入现有 RAG 文本来源；研报/调研/互动问答/新闻结构化文本已纳入，公告 API 正文待分批抓取。
- [x] 新增 RAG 预处理实验开关：增强清洗、元信息前缀和滑动窗口参数已接入 `extract_rag_notice_texts.py --experiment`，默认主流程不变，召回和排序暂不调整。
- [x] 新增用户 query 补全实验工具：`enrich_rag_query.py` 可补全公司别名/代码、事件意图词和市场反应指标词，尚未接入召回和排序。
- [x] 新增 RAG chunk 实验对比：`compare_rag_chunk_experiments.py --limit 120` 已生成对比表；增强清洗单独使用可让 chunks 从 1454 降至 1428，前缀+1400/240 窗口增至 1720，前缀+1200/240 增至 1908，前缀+1000/300 增至 2251。
- [x] RAG 预处理样本问题已修：增强清洗已去除免责声明残留，前缀模式下结构化文本不再重复 `标题：...`。
- [ ] RAG 暂停深入调试：RAG 是项目辅助证据层，不作为下一阶段主线；后续只在需要证据覆盖时按 Top 缺口分批补公告 API 正文，不继续调召回和排序。
- [ ] 支持按事件返回原文段落、证据强弱等级和相似竞品案例。

### 5. 可视化报告原型

- [ ] 下一阶段主线转向报告和管理层可读交付，优先生成“事件-市值变化-证据链”CFO 主表和数据验收 HTML dashboard。
- [x] 市值全景页交互原型：`data/processed/interactive_market_dashboard.html`。
  - 默认主线图：移为通信原始总市值渐变折线 + 事件点标注。
  - 模式切换：主线、泳道、叠加、气泡、事件对齐。
  - 事件篮：支持多事件加入、移除和事件对齐视图。
  - 链接：有来源 URL/PDF 的事件在事件表和详情中保留可点击证据链接。
- [ ] 市值全景页正式稿：继续精修视觉层级、事件点密度、默认文案和 CFO 汇报口径。
- [ ] 事件影响权重页：各类事件贡献、正负贡献、持续性。
- [ ] 竞品动作外溢页：

  ```text
  横轴：竞品自身 CAR
  纵轴：移为同期 CAR
  ```

- [ ] 竞品动作榜：产品创新、客户突破、资本动作、投关表达。
- [ ] CFO 汇报 PPT 初稿。

### 6. 交互式 dashboard 当前状态

- [x] 生成器：`build_interactive_market_dashboard.py`。
- [x] 输出文件：`data/processed/interactive_market_dashboard.html`。
- [x] 当前设计闭包：
  - 默认主线聚焦移为通信。
  - 主图只显示原始总市值渐变折线和事件点，不展示“竞品原始市值压缩带”。
  - 已删除“市值信息概览”，右侧保留事件展示篮。
  - 事件支持多选加入展示篮；事件详情和表格保留证据链接。
  - 不使用中位数/平均值替代公司原始市值。
- [ ] 待继续精修：
  - 需要浏览器截图验收；当前环境缺 Playwright/浏览器，尚未做真实截图验收。
  - 事件点密度、标签避让、hover 细节和右侧事件篮视觉层级仍需按实际页面观感继续调。
  - “所有公司都在一起”的总表仍未定稿，目前先用可比矩阵和气泡模式承载。

## 统计分析方法论：资本运作/竞品动作 → 市值影响

> 主线是**市值影响**（客观市值变化 + 同期竞品对照）；CAR / abnormal return 是辅助引擎与因果骨架，不是主角。本节是把"辅助统计/ML"从含糊提法落成可执行研究设计。研究方法可调，但下列三条命门不可破。

### 定位：估计而非预测

- 交付物不是"会预测股价的模型"，是**"每类资本运作/竞品动作对市值的可信影响 + 不确定性区间 + 成立条件 + 失效边界"**。
- 数据量（见下）只够做**估计/归因**，做个股点位预测必过拟合，反而制造决策风险。

### 数据底数（已用 pandas 复核）

- 分析事件组共 6550，覆盖 9 家通信模组公司。
- 移为通信（主体）事件组 782，其中**资本动作 194（CAR 全部算成功）**、产品/技术创新 171、业绩信号 66、管理层信号 56。
- 全赛道资本动作事件 1630。
- **独立单位是 9 家公司，不是 6550 行**——这是所有统计推断的硬约束。

### 路线乙：跨公司面板（已选定）

- 用全部 9 家、1630 个资本动作做跨公司面板，而非只用移为 194（单公司只有 1 个 cluster，无法做稳健推断）。
- 移为是面板中信息最厚的一个公司，单独成"移为专章"。
- 结论是"通信模组赛道级"，移为是其中案例；**一般化仅限赛道内，不外推其他行业**。

### 双章结构（两个不同的因果问题，不混入同一回归）

- **A 章 · 自身资本运作 → 移为市值**：处理对象 = 移为事件，放进 9 家面板估计。
- **B 章 · 竞品动作 → 移为市值（外溢）**：处理对象 = 竞品事件，响应单位 = 移为；底表 `peer_spillover_to_yiwei.csv`。

### 双窗口分工

- **[0,+5] 短窗 = 因果主力**：显著性、效应大小、排序**只在短窗下断言**。
- **[0,+60] 长窗 = 描述性辅助**：只讲市值轨迹是否延续，**标注含其他因素，不做因果归因**。

### 三条命门（破一条则结论作废）

1. **竞品/行业对照是因果骨架，不是装饰**：裸的市值变化（亿元）混着大盘与行业，剔除同行同期后才能归因。
2. **外溢章符号会自我抵消**：竞品利好对移为有**替代（负）**与**共振（正）**两股反向力，只算总平均必得"无影响"的假结论。MUST 按竞品事件类型拆开估计——产品/订单/份额→替代为主，政策/技术突破→共振为主。
3. **9 个 cluster 是硬下限**：低于聚类稳健 SE 的经验门槛（30-40），普通聚类 SE 失效，**必须用 wild cluster bootstrap**；跨公司比较用 %（规模归一），落地给 CFO 再把 % × 代表性市值翻译回亿元。

### 七步流程（taskwork 顺序）

0. 把问题逼成可证伪句子 + 写下双向预期（效应在/不在各长什么样），锁定估计范式。
1. 资本运作子分类学（增发/并购/回购/股权激励/资产注入/分拆/重组）+ 事件去重 + 入选剔除标准（剔 IPO/停牌/同期叠加其他重大事件）。当前 `primary_category` 是规则初版、"其他"占比高，需 LLM 复核。
2. 复审 CAR/abnormal 因变量：前瞻偏差（只用事件时点已知价格/基准）、补基准（当前仅竞品等权组，需加指数基准/滚动 beta/市值加权/显著性检验）。oracle 已有 `validate_market_outputs.py`。
3. 特征工程（LLM 抽取结构化事件属性）：类型/相对规模/关联交易/支付方式/溢价率/是否首次/控股权变更/市场环境。**point-in-time 铁律**（特征必须事件时点前可知）+ 理论驱动、少而强。
4. 描述性分析先行（最便宜的证伪）：按子类看竞品校正后的市值变化分布；信号在粗切片都看不见就别建模。排序用 %，头条用亿元。
5. 建模：A 章跨公司面板回归 + 公司固定效应 + 按公司聚类 + wild cluster bootstrap；B 章按竞品事件类型分符号估计。进阶贝叶斯分层 partial pooling。**禁深度学习/树集成当主模型、禁个股预测**。
6. 防自欺验证：留一公司检验（9 家抽掉任一结论还在吗，最关键）、安慰剂随机事件日、多重比较 FDR 校正、换窗口换基准稳健性。
7. 交付：效应估计 + 区间 + 成立条件 + 失效边界；主线对齐"客观市值变化 + 竞品对照 + 证据链"，CAR 作辅助列；明确声明不外推赛道外、不做个股预测。

### 事件重叠窗口（A、B 两章共同命门）

- 同公司事件时间聚集会污染 CAR 归因（本文件"当前缺口"已标）。
- B 章尤其关键：测竞品事件对移为的反应时，**必须排除移为同期也有自身事件的窗口**，否则量到的是移为自己的事件而非外溢。
- 首轮 ML 准入诊断已生成：`data/processed/ml_readiness/ml_readiness_summary.md`。
  - 全事件组 [0,+5] 重叠率约 85.68%；资本动作 [0,+5] 重叠率约 88.04%。
  - 资本动作 1630 组中，CAR 成功且 [0,+5] 无同公司重叠的只有 195 组。
  - 竞品外溢 OK 事件 4596 组中，排除移为自身 [0,+5] 同窗事件后只剩 747 组。
  - 结论：当前不适合直接进入面板回归；最麻烦的主线工作是先重构事件簇和入选剔除标准。

### Step0 进度与待拍板（下次续起点）

研究设计骨架（路线乙 / 双章 / 双窗 / 三命门 / 七步）已定且已落本节。**Step0 = 把问题逼成可证伪句子，尚未定稿**；首轮 ML 准入诊断已经证实重叠污染是当前最大障碍。下次从以下三个未拍板点续起，三点定了才进 Step1，避免下游返工：

- **问题是否按数据预算分层**（主要矛盾）：独立单位只有 9 家公司，子类切太细 → wild cluster bootstrap 区间必跨 0，承诺的精度不能超过数据能兑现的精度。首轮规则子类下没有任何资本动作达到“主力估计候选”；股东增减持/限售流通、股权质押/解押、股权激励/员工持股、股份回购、分红/权益分派暂只能做描述+谨慎估计。待拍板：先做事件簇重构后再判断 2-3 类能否下因果断言，还是本阶段统计/ML 全部降级为描述性支持。
- **头条因果窗口**：取干净的 [0,+5]，还是改 [-1,+5] 吃掉 A 股公告前消息泄漏（定增 / 并购尤甚）。已算窗口含 CAR[-1,+1]，可先用它佐证泄漏幅度再定。
- **头条异常收益基准**：用 peer-adjusted（剔同行同期，对齐「竞品对标」本意、CFO 易懂）当主口径、市场模型 / 滚动 beta / 市值加权留 Step6 稳健性；还是反过来。

## 注意事项

- 不把 Tushare token 写入仓库文件。
- 新增依赖 `akshare` 已安装到根目录 `.venv`，未写入 `pyproject.toml` 和 `uv.lock`。
- 当前 `data/` 目录体积较大，是否入库需单独决定；默认不应提交大型原始数据和 PDF。
- 事件结论不能只靠关键词，需要结合 CAR、成交额、研报/调研跟进和原文证据。
- PDF/RAG 是证据层，不是因果判断层。

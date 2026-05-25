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

截至 2026-05-25，已完成第一轮数据采集。

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
- [ ] 事件分类仍是规则初版，“其他”占比高，PPT 前需人工/LLM 辅助复核 Top 事件。
- [ ] 面向 CFO 的数据验收页尚未生成：需要说明数据覆盖、缺失、PDF 挂接率、事件数量、CAR 抽查复核结果和口径限制。
- [ ] 面向 CFO 的可视化报告初版尚未生成：不能停留在 Excel，需要静态 HTML/截图级页面先跑通叙事。
- [ ] 当前输出表字段偏工程化，需生成中文字段版本和指标口径说明，方便管理层直接阅读。
- [ ] 报告主线需从“CAR 解释事件”调整为“客观市值变化 + 同期竞品/行业对照 + 证据链”，CAR 放到辅助列。
- [ ] 当前 CAR 使用剔除自身的竞品等权组合做基准，尚未加入指数基准、滚动 beta、市值加权和显著性检验。
- [ ] 竞品外溢已排除移为上市前事件，但早期上市初期高波动仍需在报告中单独标注。
- [ ] 事件重叠窗口尚未系统标记，分类权重只能作为候选排序和解释入口，不能直接当因果贡献。
- [ ] 沪市/科创板互动问答数据不完整：移远通信、有方科技在 `cninfo_irm_questions` 采集失败，后续需用上证 e 互动或其他源补。
- [ ] 新浪评级接口全部失败，暂不作为主数据源；东方财富研报已足够支撑第一版。
- [ ] 23 条无效公告 PDF 可后续用 Playwright 或页面正文兜底，不阻塞主流程。

## 下一步任务

### 0. 立即任务：数据验收页和 CFO 可视化初版

- [ ] 生成数据验收页，输出建议：
  - `data/processed/validation/data_quality_dashboard.html`
  - `data/processed/validation/data_quality_summary.csv`
- [ ] 数据验收页至少包含：
  - 9 家公司行情、市值、公告、研报、调研、PDF 覆盖情况。
  - 事件候选池、分析事件组、竞品外溢底表的行数和时间覆盖。
  - PDF 有效率、无效 PDF 清单、缺失互动问答来源。
  - CAR 抽查复核结果和异常市值影响单位说明。
  - 明确写出哪些结论可用，哪些只能作为候选排序。
- [ ] 生成 CFO 可视化报告初版，优先静态 HTML，输出建议：
  - `reports/cfo_market_impact_preview.html`
  - `reports/assets/`
- [ ] CFO 可视化报告第一版页面：
  - 市值全景：移为通信 vs 竞品上市以来总市值曲线。
  - 阶段拆解：移为市值高点、低点、关键拐点和同期事件。
  - 事件总览：按业绩、资本动作、管理层信号、产品创新、客户订单、风险事件、竞品动作分组。
  - 客观变化主表：事件前市值、事件后 1/5/20/60 日市值变化、相对竞品变化、是否跑赢。
  - CAR 辅助列：CAR、异常市值影响、状态标记，不作为主标题结论。
  - 竞品动作页：展示竞品重大动作及市场反应，不使用“可学习”作为正式页标题。
  - 证据链页：Top 事件对应公告/PDF/研报/调研来源链接。
- [ ] 生成中文字段版本，至少覆盖：

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

- [ ] 运行检查：
  - `python3 tools/check.py changed`
  - 或至少对报告生成脚本运行 Ruff、pytest 和 `market-impact-validation`。

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

- [ ] 将公告 PDF、研报 PDF、调研纪要纳入现有 RAG 项目。
- [ ] 支持按事件返回原文段落和相似竞品案例。

### 5. 可视化报告原型

- [ ] 市值全景页：移为通信 vs 竞品市值曲线和关键事件标注。
- [ ] 事件影响权重页：各类事件贡献、正负贡献、持续性。
- [ ] 竞品动作外溢页：

  ```text
  横轴：竞品自身 CAR
  纵轴：移为同期 CAR
  ```

- [ ] 竞品动作榜：产品创新、客户突破、资本动作、投关表达。
- [ ] CFO 汇报 PPT 初稿。

## 注意事项

- 不把 Tushare token 写入仓库文件。
- 新增依赖 `akshare` 已安装到根目录 `.venv`，未写入 `pyproject.toml` 和 `uv.lock`。
- 当前 `data/` 目录体积较大，是否入库需单独决定；默认不应提交大型原始数据和 PDF。
- 事件结论不能只靠关键词，需要结合 CAR、成交额、研报/调研跟进和原文证据。
- PDF/RAG 是证据层，不是因果判断层。

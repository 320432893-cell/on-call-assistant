# Market Impact Study 项目交接

## 项目目标

本项目面向 CFO 汇报，研究主题是移为通信上市以来市值驱动因素与竞品动作对标分析。主线不是预测股价，而是解释：

- 移为通信市值变化经历了哪些阶段。
- 业绩、资本动作、管理层信号、产品创新、客户订单、风险事件对市值变化的关系。
- 竞品动作是否对移为形成替代或共振外溢。
- 哪些管理动作、披露方式和投关节奏更可能提升市场认知。

研究主体：移为通信。竞品/参照：移远通信、高新兴、广和通、日海智能、锐明技术、有方科技、美格智能、博实结。

## 当前真实进度

截至本次核对，已完成第一轮数据采集、事件/CAR 辅助底表、RAG 证据候选、中文 Top 表、数据质量校验、管理层信号台账初版、CFO 事件-市值变化-证据链主表、数据验收 HTML 和单页交互式市值事件工作台。

核心可用入口：

| 入口 | 路径 | 用途 |
|---|---|---|
| 单页工作台 | `data/processed/market_impact_workbench.html` | CFO/分析人员浏览市值走势、事件影响、竞品对比、事件对齐/外溢、Top 专题 |
| 数据验收页 | `data/processed/validation/data_quality_dashboard.html` | 检查数据覆盖、事件分布、基础校验和 CAR 复算抽样 |
| CFO 主表 | `data/processed/cfo_event_evidence_chain.csv` | 事件-客观市值变化-竞品对照-RAG 证据链主表 |
| 项目交接 | `docs/PROJECT_HANDOFF.md` | 下一位 AI 的续作入口 |

## 数据与产物口径

已采集数据：

| 来源 | 数据 | 覆盖 | 实际行数/文件 |
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
| AKShare/互动易 | 投资者问答 | 7/9 | 190 |
| 东方财富公告 PDF | 高价值关键词公告 PDF | 697 份有效 | 约 307MB |

关键产物：

| 产物 | 路径 | 当前状态 |
|---|---|---|
| 自动事件候选池 | `data/processed/event_candidates.csv` | 已生成 |
| CAR 和异常市值影响 | `data/processed/event_candidates_scored.csv` | 已生成 |
| 分析事件组 | `data/processed/event_analysis_groups_scored.csv` | 6,550 组 |
| 竞品外溢底表 | `data/processed/peer_spillover_to_yiwei.csv` | 已生成 |
| RAG 文本来源清单 | `data/processed/rag_text_source_manifest.csv` | 14,406 条 |
| RAG chunks | `data/processed/rag_notice_chunks.jsonl` | 14,219 条 |
| 事件组证据增强表 | `data/processed/rag_event_group_evidence_enhanced.csv` | 6,550 组 |
| RAG 证据覆盖统计 | `data/processed/rag_event_group_evidence_coverage.csv` | 已生成 |
| RAG 证据缺口诊断 | `data/processed/rag_event_group_evidence_gaps.csv` | 5,383 组缺口 |
| 管理层信号台账 | `data/processed/management/management_signal_ledger.csv` | 5,557 行 |
| 管理层信号覆盖缺口 | `data/processed/management/management_signal_coverage_gaps.csv` | 54 行 |
| CFO 主表 | `data/processed/cfo_event_evidence_chain.csv` | 6,550 组 |
| 数据验收 HTML | `data/processed/validation/data_quality_dashboard.html` | 已生成 |
| 单页工作台 | `data/processed/market_impact_workbench.html` | 已生成 |

## 已确认技术事实

- 9 家公司代码和上市日已完整解析。
- Tushare 行情、估值、财务、公告标题、指数数据可用。
- `daily_basic.total_mv` 和 `circ_mv` 是万元口径；报告输出市值金额时统一换算为亿元。
- 东方财富公告 PDF 可由公告代码构造：`https://pdf.dfcfw.com/pdf/H2_{announcement_code}_1.pdf`。
- PDF 下载需校验 `%PDF` 文件头；720 条高价值公告中 697 条有效，23 条为空或无效。
- 东方财富机构调研数据质量较高，可用于管理层信号和机构关注度指标。
- 公告标题和公告类型足以生成自动事件候选池；公告正文/PDF 用于证据链和 RAG。

## 真实缺口

1. 事件分类仍是规则初版，“其他”占比高；PPT 前必须人工/LLM 复核 Top 事件。
2. 管理层信号台账仍是自动整合初版；需要围绕管理层动作、投关表达、战略表达、卖方认知和市场反应做人工/LLM 复核。
3. RAG 覆盖率仍偏低：6,550 个分析事件组中 1,167 组有 RAG/结构化证据，覆盖率约 17.82%。Top 优先级事件覆盖尤其低。
4. `rag_text_source_manifest.csv` 中已有 `notice_api=12757` 候选，但 `rag_notice_chunks.jsonl` 中尚无 `notice_api` chunk。也就是公告页面/API 正文尚未抓取入 chunks；研报、调研、互动问答、新闻结构化文本已入 chunks。
5. 报告主线仍需从“CAR 解释事件”调整为“客观市值变化 + 同期竞品/行业对照 + 证据链”，CAR 只作辅助列。
6. 当前 CAR 使用剔除自身的竞品等权组合做基准，尚未加入指数基准、滚动 beta、市值加权和显著性检验。
7. 事件重叠污染很高，分类权重只能作为候选排序和解释入口，不能直接当因果贡献。
8. 沪市/科创板互动问答数据不完整：移远通信、有方科技在 `cninfo_irm_questions` 采集失败，后续需用上证 e 互动或其他源补。
9. 23 条无效公告 PDF 可后续用 Playwright 或页面正文兜底，不阻塞主流程。

## 下一步建议

优先顺序：

1. 按 `data/processed/rag_event_group_evidence_gaps.csv` 处理 Top 缺口，优先抓取 `notice_api` 正文并重新生成 chunks。
2. 复核 Top 事件分类和事件标题，尤其是“其他”、交易异常、流程型公告、同日多附件公告。
3. 重构事件簇合并/剔除规则，降低同公司连续公告、重组进展、股权激励解锁/注销、分红流程等重复计权。
4. 更新 `data/processed/preview_report.html` 或直接基于 `market_impact_workbench.html` 出 CFO 汇报稿，主线使用客观市值变化、同期竞品对照和证据链。
5. 管理层专题从“有多少数据”推进到“哪些动作/表达/节奏与市场认知变化相关”。

## 运行与验证

常用生成命令在 `market-impact-study` 目录运行：

```bash
../.venv/bin/python build_rag_text_source_manifest.py
../.venv/bin/python extract_rag_notice_texts.py
../.venv/bin/python build_rag_event_group_evidence.py
../.venv/bin/python build_cfo_event_evidence_chain.py
../.venv/bin/python build_data_quality_dashboard.py
../.venv/bin/python build_market_impact_workbench.py
```

切片闭包检查使用父项目工具：

```bash
../.venv/bin/python ../tools/check.py changed
```

注意：仓库根的 `AGENTS.md` / `.ai-config/AGENTS.md` 镜像清理属于其他任务，不是本项目续作范围。

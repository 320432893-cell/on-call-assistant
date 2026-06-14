# 建模入口与图表生成报告

## 为什么今天做这些

- 不需要人工判断，且后续 EDA、特征工程、建模和报告都会复用。
- 建模宽表减少重复 join，避免不同脚本读不同口径。
- 复核 overlay 模板让人工修正独立于原始 SSOT，保证可追溯。
- SVG/HTML 图表不依赖额外绘图库，当前环境可直接生成和查看。

## 生成产物

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| 建模宽表 | `data/processed/modeling/modeling_dataset_v1.csv` | 后续训练、EDA、图表统一入口 |
| 人工复核模板 | `data/processed/data_governance/manual_review_overlay_template.csv` | 前 100 条高优先级事件人工复核 |
| 数据治理 dashboard | `market-impact-study/data/processed/modeling/data_governance_dashboard.html` | 汇总样本、标签和图表 |
| 图表 manifest | `figures/data_governance/figure_manifest.csv` | 报告/PPT 图表索引 |

## 建模范围分布

| modeling_scope     |   rows |
|:-------------------|-------:|
| robustness_or_case |   5484 |
| main               |    444 |
| exclude_from_model |    249 |
| case_or_audit_only |    167 |
| clean_sensitivity  |     54 |

## 图表清单

| figure_id   | path                                                                       | title            | data_source                | why                                   |
|:------------|:---------------------------------------------------------------------------|:-----------------|:---------------------------|:--------------------------------------|
| F-DG-01     | market-impact-study/figures/data_governance/sample_policy_distribution.svg | 样本策略分布           | sample_policy_summary.csv  | 说明哪些样本进入主模型、稳健性、案例或排除，避免后续训练临时筛样本。    |
| F-DG-02     | market-impact-study/figures/data_governance/review_reason_distribution.svg | 人工复核原因分布         | top_event_review_queue.csv | 展示为什么这些事件需要人工复核，支撑事件治理过程。             |
| F-DG-03     | market-impact-study/figures/data_governance/main_label_histogram.svg       | 20日相对市值反应分布      | modeling_dataset_v1.csv    | 检查主标签是否被极端值主导，并为 winsorize/分位数分析提供依据。 |
| F-DG-04     | market-impact-study/figures/data_governance/category_event_count.svg       | 事件类型样本量          | category_audit_summary.csv | 展示事件分类结构，突出其他类占比和分类审计必要性。             |
| F-DG-05     | market-impact-study/figures/data_governance/category_label_boxplot.svg     | 事件类型 x 20日相对市值反应 | modeling_dataset_v1.csv    | 为后续特征工程和报告中的事件类型解释提供直观依据。             |

## 使用边界

- `modeling_dataset_v1.csv` 是建模入口，不代表所有字段都可直接入模；训练脚本仍需根据特征注册表筛字段。
- 人工复核模板是 overlay，不应覆盖原始 SSOT。
- 当前图表是数据治理图，不是模型效果图；模型效果图要等 baseline 和主模型训练后生成。

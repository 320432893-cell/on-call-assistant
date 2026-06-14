# 人工复核应用摘要

## 结论

- 已应用人工数字复核 100 条。
- 人工标记可保留事件 30 条；不进主模型 70 条。
- 人工标记噪声/流程事件 70 条。
- `keep=1` 只表示人工确认事件有经济含义；是否进入主模型仍受原始样本策略和同窗重叠约束。

## 输出产物

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| reviewed overlay | `market-impact-study/data/processed/data_governance/manual_review_overlay_reviewed.csv` | 保存人工判断的标准化结果 |
| reviewed 建模宽表 | `market-impact-study/data/processed/modeling/modeling_dataset_reviewed_v1.csv` | 后续 baseline/model 优先读取 |
| 数字复核摘要 | `market-impact-study/data/processed/data_governance/manual_review_numeric_summary.csv` | 机器可读的复核统计 |

## 复核状态分布

| manual_review_status | events |
| --- | --- |
| noise | 70 |
| reclassified | 30 |

## 修正后类型分布

| manual_corrected_category | events |
| --- | --- |
| 交易机制/IPO | 12 |
| 产品/技术创新 | 2 |
| 客户/订单 | 4 |
| 管理层/投关信号 | 1 |
| 纯流程/其他 | 58 |
| 资本动作 | 19 |
| 风险事件 | 4 |

## reviewed 建模范围分布

| reviewed_modeling_scope | events |
| --- | --- |
| case_or_audit_only | 226 |
| clean_sensitivity | 54 |
| exclude_from_model | 249 |
| main | 444 |
| robustness_or_case | 5425 |

## 使用边界

- 原始 SSOT 未被修改。
- 人工标为噪声或不保留的事件会降为 `case_or_audit_only`。
- 人工标为保留但原始仍为重污染或结构性排除的事件，不自动升入主模型。

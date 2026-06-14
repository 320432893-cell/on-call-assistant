# 数据治理摘要

## 结论

- 已生成 360 条人工复核队列，优先覆盖极端标签、移为自身事件、`其他` 类和同窗重叠事件。
- 已固化样本使用策略：主模型、clean 稳健性、案例/审计、排除样本分开管理。
- 当前不新增显性或隐性特征，只治理样本和标签，降低后续建模与报告返工。

## 主标签体检

| scope | label | n | mean | std | p01 | p05 | p50 | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| default_training_candidate | relative_mv_return_p0_p20 | 5982 | 0.0035589052129425896 | 0.1520506311031958 | -0.30329457659910625 | -0.19569655010036252 | -0.0107826416379951 | 0.2461977183248094 | 0.5931583677826082 |

## 复核原因分布

| reason | events |
| --- | --- |
| overlap_dirty_p20 | 360 |
| category_other | 349 |
| large_mv_impact | 180 |
| extreme_relative_label | 116 |
| subject_company | 71 |
| top_positive_label | 63 |
| top_negative_label | 51 |
| not_default_training | 33 |

## 事件类型审计

| primary_category | events | default_training_candidates | main_label_n | median_relative_mv_return_p20 | median_abnormal_mv_impact_yi_p20 | overlap_dirty_p20 | audit_priority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 其他 | 2264 | 1977 | 2105 | -0.0067861161771911 | -0.4481051131416397 | 2152 | 高 |
| 资本动作 | 1625 | 1594 | 1605 | -0.0104403155875648 | -0.7426071407922286 | 1615 | 高 |
| 管理层/投关信号 | 621 | 601 | 601 | -0.0196386382567805 | -1.2077290490265011 | 602 | 高 |
| 产品/技术创新 | 572 | 533 | 552 | -0.01342493454422835 | -0.6255326757803594 | 551 | 高 |
| 业绩信号 | 557 | 542 | 542 | -0.0107684132935004 | -0.729070800000001 | 553 | 高 |
| 政策/行业 | 340 | 334 | 334 | -0.0087362750920535 | -0.7565258666680004 | 335 | 高 |
| 风险事件 | 306 | 292 | 301 | -0.003909411068395 | -0.2673447914057143 | 298 | 高 |
| 客户/订单 | 113 | 109 | 109 | -0.015841529275748 | -1.5288149116144611 | 112 | 高 |

## 样本策略摘要

| sample_policy | split | events |
| --- | --- | --- |
| case_or_audit_only | test | 35 |
| case_or_audit_only | train | 112 |
| case_or_audit_only | valid | 20 |
| exclude_from_model | excluded_unlabeled | 249 |
| main_clean_sensitivity | test | 22 |
| main_clean_sensitivity | train | 25 |
| main_clean_sensitivity | valid | 7 |
| main_model_with_overlap_flag | test | 142 |
| main_model_with_overlap_flag | train | 275 |
| main_model_with_overlap_flag | valid | 27 |
| robustness_or_case | test | 1421 |
| robustness_or_case | train | 3493 |
| robustness_or_case | valid | 570 |

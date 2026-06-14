# 样本使用策略

## 原则

- 主模型优先服务解释与复现，不承诺预测绝对市值。
- 有主标签、非 IPO/交易机制事件、满足时间切分的样本可进入默认建模候选。
- 同窗重叠不是直接删除理由，但必须分层：主模型可用、clean 稳健性、重污染案例/附录。
- 人工复核只改分类和样本使用建议，不直接改原始 SSOT；修正结果后续应单独落表。

## 策略定义

| 策略 | 用途 | 边界 |
| --- | --- | --- |
| `main_model_with_overlap_flag` | 第一版主模型样本 | 有主标签且轻度重叠，模型中需控制/标记污染风险 |
| `main_clean_sensitivity` | 稳健性/敏感性检验 | 20 日窗口无同公司重叠，但样本少，不单独作为主模型 |
| `robustness_or_case` | 稳健性或案例复盘 | 重叠污染较重，不适合直接支撑主结论 |
| `case_or_audit_only` | 报告案例或审计保留 | IPO、交易机制、不满足默认候选等 |
| `exclude_from_model` | 不入模 | 主标签缺失 |

## 当前样本分布

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

## 人工复核入口

- `data/processed/data_governance/top_event_review_queue.csv` 是优先复核清单。
- 复核字段包括 `manual_keep_for_model`、`manual_is_noise`、`manual_corrected_category`、`manual_notes`。

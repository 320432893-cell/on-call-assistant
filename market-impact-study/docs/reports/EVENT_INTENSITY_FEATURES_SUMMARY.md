# 事件强度特征摘要

## 结论

- 已生成 enhanced v2 建模宽表：6398 行，244 列。
- 新增事件强度数值特征 26 个，来源仅限标题、摘要和事件组标题。
- 未读取公告正文或 RAG chunk；特征只描述事件披露文本中的金额、百分比、方向和类型旗标。

## 覆盖率较高的新增特征

| feature | non_null | missing_rate | coverage |
| --- | --- | --- | --- |
| evt_is_contract_order | 6398 | 0.0 | 1.0 |
| evt_is_earnings_report | 6398 | 0.0 | 1.0 |
| evt_is_forecast | 6398 | 0.0 | 1.0 |
| evt_is_impairment | 6398 | 0.0 | 1.0 |
| evt_is_inquiry | 6398 | 0.0 | 1.0 |
| evt_is_ir_activity | 6398 | 0.0 | 1.0 |
| evt_is_litigation_penalty | 6398 | 0.0 | 1.0 |
| evt_is_pledge | 6398 | 0.0 | 1.0 |
| evt_is_product_launch | 6398 | 0.0 | 1.0 |
| evt_is_repurchase | 6398 | 0.0 | 1.0 |
| evt_is_restructuring | 6398 | 0.0 | 1.0 |
| evt_is_subsidy | 6398 | 0.0 | 1.0 |
| evt_money_count | 6398 | 0.0 | 1.0 |
| evt_negative_word_count | 6398 | 0.0 | 1.0 |
| evt_percent_count | 6398 | 0.0 | 1.0 |
| evt_positive_word_count | 6398 | 0.0 | 1.0 |
| evt_profit_direction | 6398 | 0.0 | 1.0 |
| evt_percent_max_abs | 280 | 0.9562363238512035 | 0.043763676148796504 |
| evt_percent_mean | 280 | 0.9562363238512035 | 0.043763676148796504 |
| evt_money_max_to_mv | 217 | 0.9660831509846827 | 0.03391684901531733 |

## 输出产物

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| enhanced v2 建模宽表 | `market-impact-study/data/processed/modeling/modeling_dataset_enhanced_v2.csv` | 下一轮模型训练入口 |
| 事件强度 manifest | `market-impact-study/data/processed/modeling/event_intensity_feature_manifest.csv` | 记录新增强度特征 |
| 合并 manifest | `market-impact-study/data/processed/modeling/enhanced_feature_manifest_v2.csv` | 训练脚本入模特征清单 |

## 使用边界

- 金额和百分比来自规则抽取，适合做弱结构化信号，不等同于严格财务口径字段。
- 区间净利润特征优先识别含“净利润/利润”的表达；其他数字只进入通用金额/百分比统计。

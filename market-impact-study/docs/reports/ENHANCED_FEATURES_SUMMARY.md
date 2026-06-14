# 增强结构化特征摘要

## 结论

- 已生成 enhanced 建模宽表：6398 行，218 列。
- 新增可入模数值特征 75 个，覆盖交易估值/同行、财务质量、管理层滚动信号。
- 所有增强特征均按事件日前最近可得数据构造，不使用事件后窗口收益或标签字段。

## 特征组摘要

| source_group | features | avg_missing |
| --- | --- | --- |
| financial | 21 | 0.0637252712901353 |
| management_rolling | 12 | 0.0 |
| other | 3 | 0.021412941544232577 |
| trading_valuation_peer | 39 | 0.04849672573961414 |

## 输出产物

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| enhanced 建模宽表 | `market-impact-study/data/processed/modeling/modeling_dataset_enhanced_v1.csv` | 下一版模型训练入口 |
| 特征 manifest | `market-impact-study/data/processed/modeling/enhanced_feature_manifest.csv` | 记录新增特征、缺失率、来源组 |

## 使用边界

- 财务特征按公告日 `ann_date <= event_date` 取最近一期。
- 交易/估值特征使用事件日前一可得交易日，不包含事件日及之后表现。
- 管理层滚动信号只统计事件日前已披露记录。

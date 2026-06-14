# ML SSOT 数据集摘要

## 结论

- 已生成事件、标签、特征、时间切分和字段字典五张主表。
- `feature_master` 只保留事件日前或事件披露本身可获得的种子特征；事件后窗口结果只在 `label_master` 或事件诊断字段中出现。
- 默认主标签为 `relative_mv_return_p0_p20`，即 20 个交易日公司市值收益率减同行平均市值收益率。

## 产物规模

| table | rows | columns |
| --- | --- | --- |
| event_master | 6398 | 39 |
| label_master | 6398 | 28 |
| feature_master | 6398 | 49 |
| split_master | 6398 | 8 |
| data_dictionary | 124 | 6 |

## 切分与默认建模范围

| split | default_model_scope | rows |
| --- | --- | --- |
| excluded_unlabeled | audit_or_aux | 249 |
| test | audit_or_aux | 1598 |
| test | main_clean | 22 |
| train | audit_or_aux | 3880 |
| train | main_clean | 25 |
| valid | audit_or_aux | 617 |
| valid | main_clean | 7 |

## 后续扩展

- 明天可在不改变样本和标签口径的前提下，追加 point-in-time 财务、估值、交易历史和管理层滚动特征。

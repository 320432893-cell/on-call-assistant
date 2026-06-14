# ML SSOT 校验报告

## 结论

- SSOT 校验：20 项通过，0 项失败。
- 当前校验覆盖主键、表间对齐、时间切分、point-in-time 和目标泄露字段。

## 主表规模

| table | rows | columns |
| --- | --- | --- |
| event_master | 6398 | 39 |
| label_master | 6398 | 28 |
| feature_master | 6398 | 49 |
| split_master | 6398 | 8 |

## 校验明细

| check | status | detail |
| --- | --- | --- |
| event_master 必要字段 | pass | missing=[] |
| label_master 必要字段 | pass | missing=[] |
| feature_master 必要字段 | pass | missing=[] |
| split_master 必要字段 | pass | missing=[] |
| data_dictionary 必要字段 | pass | missing=[] |
| event_master 主键唯一 | pass | duplicated=0, rows=6398 |
| label_master 主键唯一 | pass | duplicated=0, rows=6398 |
| feature_master 主键唯一 | pass | duplicated=0, rows=6398 |
| split_master 主键唯一 | pass | duplicated=0, rows=6398 |
| label_master 与 event_master 键集合一致 | pass | symmetric_diff=0 |
| feature_master 与 event_master 键集合一致 | pass | symmetric_diff=0 |
| split_master 与 event_master 键集合一致 | pass | symmetric_diff=0 |
| feature_master point-in-time | pass | as_of_date>event_date rows=0 |
| feature_master 日期可解析 | pass | bad_date_cells=0 |
| split 取值合法 | pass | invalid=[] |
| 时间切分无穿越 | pass | violating_rows=0 |
| 训练/验证/测试均有样本 | pass | {'excluded_unlabeled': 249, 'test': 1620, 'train': 3905, 'valid': 624} |
| 默认切分样本主标签完整 | pass | missing=0 |
| feature_master 无目标泄露字段 | pass | columns=[] |
| 字段字典未将特征标为目标泄露 | pass | rows=0 |

## 缺失率最高字段

| table | column | rows | missing | missing_rate |
| --- | --- | --- | --- | --- |
| event_master | pdf_url | 6398 | 6398 | 1.0 |
| event_master | local_pdf_path | 6398 | 6398 | 1.0 |
| event_master | summary | 6398 | 5529 | 0.8641763050953423 |
| event_master | capital_action_subtype_hits | 6398 | 4822 | 0.7536730228196311 |
| event_master | capital_action_subtype | 6398 | 4773 | 0.7460143794935917 |
| event_master | category_tags | 6398 | 2264 | 0.3538605814316974 |
| event_master | source_url | 6398 | 690 | 0.10784620193810565 |
| event_master | overlap_categories_p0_p20 | 6398 | 180 | 0.028133791809940606 |
| event_master | aligned_trade_date | 6398 | 123 | 0.019224757736792747 |
| event_master | pre_trade_date | 6398 | 123 | 0.019224757736792747 |
| feature_master | pre_total_mv_yi | 6398 | 123 | 0.019224757736792747 |
| label_master | peer_avg_mv_return_p0_p5 | 6398 | 249 | 0.03891841200375117 |
| label_master | relative_mv_return_p0_p5 | 6398 | 249 | 0.03891841200375117 |
| label_master | peer_avg_mv_return_p0_p20 | 6398 | 249 | 0.03891841200375117 |
| label_master | relative_mv_return_p0_p20 | 6398 | 249 | 0.03891841200375117 |

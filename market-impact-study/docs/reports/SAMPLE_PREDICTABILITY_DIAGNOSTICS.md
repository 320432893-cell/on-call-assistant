# 样本可预测性诊断

## 结论

- reviewed 入模样本 498 条；clean-only 样本 54 条。
- clean-only 仅有 train=25、valid=7、test=22，适合作为敏感性分析，不适合作为主模型结论。
- 满足分类别训练最低样本门槛的类别数：3。
- 类别均值基线用于判断“类别本身是否有稳定解释力”，不是最终模型。

## 样本范围

| split | reviewed_modeling_scope | rows |
| --- | --- | --- |
| test | clean_sensitivity | 22 |
| test | main | 142 |
| train | clean_sensitivity | 25 |
| train | main | 275 |
| valid | clean_sensitivity | 7 |
| valid | main | 27 |

## 可单独分析的类别

| category | rows | train_rows | valid_rows | test_rows | target_mean | target_std | positive_share | negative_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 其他 | 209 | 138 | 11 | 60 | -0.026130518210113744 | 0.11624039641208013 | 0.3062200956937799 | 0.5311004784688995 |
| 资本动作 | 104 | 61 | 8 | 35 | -0.005634941448205099 | 0.10588449656300393 | 0.33653846153846156 | 0.46153846153846156 |
| 管理层/投关信号 | 68 | 30 | 9 | 29 | -0.007346252730177468 | 0.09931731986270909 | 0.3235294117647059 | 0.4117647058823529 |

## 类别均值基线

| baseline | split | n | mae | rmse | r2 | spearman_ic | directional_accuracy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| global_train_mean | valid | 34.0 | 0.06809253278448324 | 0.08100053918996689 | -0.12885354173943453 | 0.0 | 0.6764705882352942 |
| category_train_mean | valid | 34.0 | 0.07563866992510775 | 0.09058106275679889 | -0.4116811116439223 | -0.07937664703576106 | 0.5588235294117647 |
| global_train_mean | test | 164.0 | 0.07222423075291447 | 0.10412667202073508 | -0.0032529999246024843 | 0.0 | 0.6158536585365854 |
| category_train_mean | test | 164.0 | 0.07774290258270959 | 0.11110200800354395 | -0.14216883824023485 | -0.021485721885079134 | 0.5304878048780488 |

## clean-only 敏感性模型

| sample_scope | feature_set | model_name | feature_count | mae_valid | mae_test | spearman_ic_test | directional_accuracy_test |
| --- | --- | --- | --- | --- | --- | --- | --- |
| clean_sensitivity_only | base_only | dummy_mean | 46 | 0.08322696608052067 | 0.08270244106406821 | 0.0 | 0.5 |
| clean_sensitivity_only | full_safe | ridge | 136 | 0.06942325427733756 | 0.11772304918418124 | -0.30321852060982496 | 0.4090909090909091 |

## 输出产物

| 产物 | 路径 |
| --- | --- |
| 类别标签诊断 | `market-impact-study/data/processed/modeling/sample_diagnostics/category_label_diagnostics.csv` |
| 类别均值基线 | `market-impact-study/data/processed/modeling/sample_diagnostics/category_mean_baseline_metrics.csv` |
| clean-only 模型指标 | `market-impact-study/data/processed/modeling/sample_diagnostics/clean_only_model_metrics.csv` |

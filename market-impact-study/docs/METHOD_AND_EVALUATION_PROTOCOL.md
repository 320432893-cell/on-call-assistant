# 计算过程与评估协议

## 1. 文档目的

本协议补齐项目中所有关键计算、校验和模型评估口径，避免只给结果、不说明过程。

| 对象 | 本文回答的问题 |
| --- | --- |
| 标签 | 市值反应、相对收益、异常市值影响怎么算 |
| 样本 | 哪些样本进主模型，哪些只做稳健性或案例 |
| 特征 | 后续显性/隐性特征如何证明没有未来信息泄露 |
| 模型 | 回归、分类、解释、稳健性分别怎么评估 |
| 报告 | 每张核心表和图应该对应哪个计算依据 |

## 2. 事件与交易日对齐

事件日来自公告、研报、新闻、互动问答、机构调研等公开源披露日期。

| 字段 | 计算过程 | 用途 |
| --- | --- | --- |
| `event_date` | 原始事件披露日标准化为 `YYYY-MM-DD` | 事件发生口径 |
| `aligned_trade_date` | 取不早于 `event_date` 的第一个交易日 | 事件窗口起点 |
| `pre_trade_date` | `aligned_trade_date` 前一个交易日 | 事件前市值和基准状态 |
| `end_trade_date_p0_p20` | 从 `aligned_trade_date` 起向后第 20 个交易日 | 主窗口终点 |

原则：

- 事件窗口使用交易日，不使用自然日。
- 非交易日披露的事件，反应从下一交易日开始计算。
- 上市前事件保留审计，但不进入默认建模。

## 3. 标签计算过程

### 3.1 公司事件窗口市值收益率

对事件公司 `i`，窗口 `[0,+k]`：

```text
actual_mv_return_i,p0_pk
= (total_mv_i,end - total_mv_i,pre) / total_mv_i,pre
```

其中：

- `total_mv_i,pre` 来自事件前一交易日 `daily_basic.total_mv`。
- `total_mv_i,end` 来自窗口终点交易日 `daily_basic.total_mv`。
- Tushare `total_mv` 单位为万元；转亿元时除以 10000。

### 3.2 同行平均市值收益率

对同一窗口，剔除事件公司自身后计算同行平均：

```text
peer_avg_mv_return_i,p0_pk
= mean(actual_mv_return_j,p0_pk), j != i
```

用途：

- 控制行业共振。
- 避免把全行业上涨误判为某公司事件效果。

### 3.3 主标签：相对同行市值反应

```text
relative_mv_return_i,p0_pk
= actual_mv_return_i,p0_pk - peer_avg_mv_return_i,p0_pk
```

| 标签 | 角色 |
| --- | --- |
| `relative_mv_return_p0_p20` | 主标签 |
| `relative_mv_return_p0_p5` | 短期稳健性 |
| `relative_mv_return_p0_p60` | 延迟反应稳健性 |

解释口径：

- 正值：事件后公司市值表现强于同行。
- 负值：事件后公司市值表现弱于同行。
- 不表述为严格因果，只表述为事件窗口内相对市值反应。

### 3.4 CFO 展示标签：异常市值影响

```text
abnormal_mv_impact_yi_p0_pk
= pre_total_mv_yi * relative_mv_return_p0_pk
```

用途：

- 将收益率转为亿元，便于 CFO 看影响量级。
- 用于典型事件复盘和市值管理建议。

注意：

- 该值是事件窗口内相对同行的市值影响估计，不是会计利润，也不是严格因果损益。
- 极端值必须进入人工复核队列。

## 4. CAR 复算口径

CAR 用日收益异常收益累计，作为市值反应的辅助验证口径：

```text
ret_i,t = pct_chg_i,t / 100
peer_ret_i,t = mean(ret_j,t), j != i
abret_i,t = ret_i,t - peer_ret_i,t
car_i,[a,b] = sum(abret_i,t), t in [a,b]
```

现有 Oracle：

| 校验 | 结果 |
| --- | --- |
| 原始行情文件 | 9 家公司日行情和市值估值文件存在 |
| CAR 抽样复算 | 30/30 pass |
| 输出位置 | `docs/reports/VALIDATION_REPORT.md` |

## 5. 样本策略

样本不直接二分为“用/不用”，而是分层使用。

| 策略 | 用途 | 进入条件 | 边界 |
| --- | --- | --- | --- |
| `main_model_with_overlap_flag` | 第一版主模型 | 有主标签、非 IPO/交易机制、轻度重叠 | 需在报告中说明重叠风险 |
| `main_clean_sensitivity` | 稳健性检验 | 20 日窗口无同公司重叠 | 样本少，不单独作为主模型 |
| `robustness_or_case` | 稳健性或案例 | 重叠污染较重 | 不直接支撑主结论 |
| `case_or_audit_only` | 案例或审计 | IPO、交易机制、不满足默认候选 | 不进默认模型 |
| `exclude_from_model` | 排除建模 | 主标签缺失 | 只保留追溯 |

已生成：

- `data/processed/data_governance/sample_policy_master.csv`
- `docs/SAMPLE_POLICY.md`

## 6. 人工复核口径

人工复核不直接修改原始 SSOT，而是后续落为 overlay 表。

| 复核对象 | 为什么复核 | 后续处理 |
| --- | --- | --- |
| 极端正负标签 | 避免被异常窗口或交易机制带偏 | 确认、降级或标记噪声 |
| `其他` 类 | 分类含义弱，影响模型解释 | 修正为更具体事件类型 |
| 交易异常/停牌/IPO | 属于市场交易机制，不是经营事件 | 默认排除建模 |
| 同窗重叠事件 | 多事件共振，难以归因 | 主模型标记，稳健性分层 |
| 移为自身 Top 事件 | 报告和 CFO 复盘优先使用 | 人工写备注和证据链 |

当前入口：

- `data/processed/data_governance/top_event_review_queue.csv`

## 7. 特征计算原则

后续无论做显性特征还是隐性特征，都必须满足以下规则。

| 规则 | 说明 | 校验方式 |
| --- | --- | --- |
| point-in-time | 特征可用日期不得晚于事件日 | `as_of_date <= event_date` |
| 禁止后验窗口 | CAR、窗口收益、窗口终点、市值影响不进特征 | 泄露字段黑名单 |
| 原始值可审计 | winsorize、标准化、embedding 前保留原字段或来源 | 字段字典 |
| 特征分组 | 财务、估值、交易、事件、文本、管理层、竞品、市场状态分组 | 消融实验 |
| 隐性特征可追溯 | embedding、聚类、主题必须保留模型版本和输入文本 | 特征注册表 |

隐性特征必须额外记录：

| 字段 | 说明 |
| --- | --- |
| `feature_model_name` | 生成 embedding/主题/聚类的模型或方法 |
| `feature_model_version` | 模型版本、参数或随机种子 |
| `source_text_fields` | 使用了哪些文本字段 |
| `fit_scope` | 只在训练集 fit，还是全量无监督 fit |
| `leakage_assessment` | 是否可能使用事件后信息 |

## 8. 模型评估协议

### 8.1 回归主任务

主任务是复现和解释 `relative_mv_return_p0_p20`。

| 指标 | 解释 | 适用 |
| --- | --- | --- |
| MAE | 平均绝对误差，直观稳定 | 主指标 |
| RMSE | 对极端误差更敏感 | 辅助指标 |
| R2 / out-of-sample R2 | 解释方差比例 | 时间外评估 |
| Spearman IC | 预测排序和真实排序相关性 | CFO 事件优先级排序 |
| Directional Accuracy | 正负方向判断准确率 | 风险提示 |

最低评估表（2026-06-14 第一版 baseline，按验证集选出的模型为 `dummy_mean`，即全局均值基线；完整四模型与消融见 `archive/reports/BASELINE_MODEL_SUMMARY.md`（v2 基线，已归档；现行主结果见 v3/v4））：

| split | n | MAE | RMSE | R2 | Spearman IC | Directional Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 300 | 0.0924 | 0.1226 | 0.000 | 0.000 | 0.573 |
| valid | 34 | 0.0681 | 0.0810 | -0.129 | 0.000 | 0.676 |
| test | 164 | 0.0722 | 0.1041 | -0.003 | 0.000 | 0.616 |

> 解读：特征模型（Ridge/ElasticNet/HistGBM）在 test 上 R² 全为负、IC≈0，均未稳定跑赢均值基线。当前结论是“尚未发现稳定样本外信号”，不是“已解释市值反应”。后续任何替换主模型的结论，必须先在 test 上稳定优于该均值基线。

### 8.2 分类辅助任务

将主标签离散化：

```text
relative_mv_return_p0_p20 >= 0.02  => positive_revaluation
relative_mv_return_p0_p20 <= -0.02 => negative_shock
otherwise                         => neutral
```

| 指标 | 用途 |
| --- | --- |
| Precision / Recall / F1 | 正负冲击识别 |
| Macro F1 | 类别不平衡下的整体表现 |
| PR-AUC | 重点看正向重估或负向冲击 |
| Confusion Matrix | 看误判结构 |
| Brier Score / Calibration Curve | 看概率是否可解释 |

分类只作为 CFO 风险预警展示，不替代回归主任务。

### 8.3 消融实验

消融不是为了堆模型，而是证明特征组的边际贡献。

| 版本 | 特征组 | 比较指标 |
| --- | --- | --- |
| V0 | 仅事件基础字段 | baseline |
| V1 | 加财务和估值 | MAE、IC 改善 |
| V2 | 加交易历史 | MAE、IC 改善 |
| V3 | 加事件文本 | MAE、IC 改善 |
| V4 | 加管理层信号 | MAE、IC 改善 |
| V5 | 加竞品和市场状态 | 最终模型 |

报告中必须展示：

- 每个版本的 test 指标。
- 指标提升是否稳定。
- 如果提升不稳定，只放附录，不写成主结论。

### 8.4 分组评估

| 分组 | 为什么评估 |
| --- | --- |
| 公司 | 防止模型只对个别公司有效 |
| 年份 | 检查市场环境变化 |
| 事件类型 | 看模型是否只学到某类事件 |
| 样本策略 | 主模型样本、clean 样本、重污染样本表现分开看 |
| 标签分位 | 检查极端事件误差 |

## 9. 黑箱检测

| 风险 | 检测方式 | 输出 |
| --- | --- | --- |
| 过拟合 | train/valid/test 指标差距、学习曲线 | `metrics_master` |
| 数据泄露 | 特征黑名单、`as_of_date` 校验 | `ssot_validation_report.csv` |
| 分布漂移 | train/test 特征分布、PSI 或 KS | 分布漂移图 |
| 解释不稳定 | SHAP 与 permutation importance 对比 | 特征重要性对照图 |
| 极端值驱动 | winsorize 前后、剔除 Top 1% 重跑 | 稳健性表 |
| 样本污染 | clean / dirty 样本分别评估 | 样本策略分组指标 |
| 概率失真 | calibration curve、Brier score | 校准图 |

## 10. 稳健推断协议

固定效应回归用于检验关键事件信号与市值反应的稳健关联。

基础形式：

```text
relative_mv_return_i,t
= beta * event_signal_i,t
+ company_fixed_effect
+ time_fixed_effect
+ market_controls
+ peer_controls
+ error_i,t
```

| 组件 | 说明 |
| --- | --- |
| `event_signal` | 事件类型、管理层信号、风险事件等 |
| `company_fixed_effect` | 控制公司长期差异 |
| `time_fixed_effect` | 控制年度、季度或月份环境 |
| `market_controls` | 指数收益、市场波动等 |
| `peer_controls` | 同行表现或同行事件密度 |

Wild Cluster Bootstrap：

- 用于核心系数置信区间和 p 值稳健性。
- 不替代机器学习评估。
- 9 家公司时单纯公司聚类偏少，应补公司-年度、公司-季度或月份聚类敏感性。

## 11. 可视化验收清单

| 模块 | 必须有的图 | 解释问题 |
| --- | --- | --- |
| 数据覆盖 | 公司-年份事件热力图、来源覆盖图 | 数据是否均衡 |
| 标签 | 5/20/60 日标签分布、极端值、正中负比例 | 标签是否合理 |
| 样本治理 | 复核原因分布、样本策略分布 | 哪些样本可信 |
| 特征 | 缺失率、分布、训练/测试漂移 | 特征是否可用 |
| 模型 | 预测值 vs 真实值、误差分布、学习曲线 | 模型是否过拟合 |
| 消融 | 特征组增量贡献图 | 特征工程是否有价值 |
| 解释 | SHAP、Permutation、单事件 waterfall | 为什么这样预测 |
| 稳健性 | WCB 置信区间、clean/dirty 对照 | 结论是否稳 |
| CFO | 关键事件影响矩阵、风险预警矩阵 | 业务动作是什么 |

## 12. 报告写法边界

| 可以写 | 不应写 |
| --- | --- |
| “模型复现和解释历史事件后的相对市值反应” | “模型可以预测未来市值” |
| “相对同行收益控制了行业共振” | “已经证明事件导致市值变化” |
| “WCB 支持核心关联稳健” | “WCB 证明严格因果关系” |
| “clean 样本用于稳健性检验” | “全样本都是干净因果样本” |
| “隐性特征提升解释能力需通过消融证明” | “embedding 一定优于人工特征” |

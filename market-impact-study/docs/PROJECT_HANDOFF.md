# Market Impact Study 项目交接

> 最近核对：2026-06-14。本文件以当前磁盘真实产物为准；历史 RAG / CFO 证据链 / 单页工作台阶段的产物已不在仓库，相关入口已从本文移除。

## 2026-06-16 更新（务必先看：含一处影响头条结论的数据更正）

本日工作（详见 `docs/DECISION_LEDGER.md` 决策+不变量账本）：

1. **收口**：22 家扩展的交接文档此前谎称"22 家因果已完成"，实则磁盘没有——已更正；新建项目决策账本；修复一个被采集改造打断的测试；整个工作区补齐到通过全部静态闸。
2. **⚠️ 重要数据更正（账本 INV-006）**：项目的"异常机构关注"信号所依赖的 **IR 机构调研数据只覆盖 2025-06 以后**（原始量 2025 年较往年跳约 160 倍）。这是采集只到近期造成的**人为断层**，不是关注真的暴增。后果：
   - 9 家因果研究"二值机构关注显著影响相对反应（p≈0.001）"的**头条很可能被这个覆盖暴涨夸大**，不可单独引用（`CAUSAL_RESULTS.md` 顶部已加 caveat）。
   - v3/v4 预测模型里把"异常机构关注"当可解释信号的部分，同样受此影响，解读需谨慎。
3. **干净长面板重做（账本 INV-007）**：改用**有真实全 2017-2026 覆盖**的注意力代理——主用分析师**研报强度**、稳健性用市场**换手异常**——在 22 家上重建因果面板（n=1034）。结论诚实：会前异常关注 → 事后相对反应是**弱正向、两代理方向一致、加控制后变强，但不在常规水平显著**（研报 p≈0.27、换手 p≈0.08 边际）。详见 `docs/reports/CAUSAL_RESULTS_TIER2.md`。

新增/更新的关键文档指针：`docs/DECISION_LEDGER.md`（项目大脑，新 session 先读）、`docs/reports/CAUSAL_RESULTS_TIER2.md`（干净长面板结果）、`docs/reports/CAUSAL_RESULTS.md`（9 家，已加覆盖 caveat）、代码 `build_causal_panel_22.py`、数据 `data/processed/modeling/causal_22/`。

## 项目目标

本项目面向 CFO 市值管理决策，研究主题是移为通信上市以来市值驱动因素与竞品动作对标。主线不是预测股价，而是**解释和复现**事件后相对同行的市值反应，并转化为信息披露、投关、资本动作与风险沟通建议。

- 移为通信市值变化经历了哪些阶段、关键事件是什么。
- 业绩、资本动作、管理层信号、产品创新、客户订单、风险事件与市值反应的关系。
- 竞品动作是否对移为形成替代或共振外溢。
- 哪些管理动作、披露方式和投关节奏更可能提升市场认知。

研究主体：移为通信（300590）。竞品/参照：移远通信、高新兴、广和通、日海智能、锐明技术、有方科技、美格智能、博实结。

完整方法口径见 `docs/PROJECT_PLAN.md` 与 `docs/METHOD_AND_EVALUATION_PROTOCOL.md`，这两份是方案权威文件。

## 当前真实进度

截至 2026-06-14，项目已从早期“采集 + RAG 证据链”阶段推进到 **ML SSOT 建模阶段**，并跑通了第一版 baseline：

- 第一轮多源数据采集完成（Tushare 行情/估值/财务/指数、AKShare/东方财富公告·研报·新闻、东方财富 IR、巨潮披露）。
- 事件候选池、CAR/相对市值反应、事件分析组、竞品外溢底表已生成。
- ML SSOT 五张主表（`event_master`/`label_master`/`feature_master`/`split_master`/`data_dictionary` + `schema_contract.json`）已生成并通过 20/20 项 SSOT 校验。
- 数据治理：复核队列、样本策略分层、事件类型审计、治理图表与 dashboard 已生成。
- 人工数字复核已应用前 100 条（70 噪声、30 重分类），落为 overlay，不改原始 SSOT。
- 增强特征 v1（218 列）、事件强度特征 v2（244 列）已生成，入模 136 个 point-in-time 安全特征。
- 第一版 baseline（dummy/Ridge/ElasticNet/HistGBM）+ 特征组消融已跑通，结果见下文“当前真实结论”。

## 核心可用入口

| 入口 | 路径 | 用途 |
|---|---|---|
| 总体方案 | `docs/PROJECT_PLAN.md` | 题目、标签、特征组、模型与检验、十天计划 |
| 计算与评估协议 | `docs/METHOD_AND_EVALUATION_PROTOCOL.md` | 标签/特征/模型/稳健性/报告边界的权威口径 |
| ML SSOT 数据集 | `data/processed/ml_dataset/` | 五张主表 + schema 契约，建模唯一入口 |
| 建模宽表（最新） | `data/processed/modeling/modeling_dataset_enhanced_v2.csv` | 244 列，含全部 point-in-time 安全特征，训练入口 |
| baseline 结果 | `data/processed/modeling/baseline_models/` | 指标、消融、预测、Top 误差、模型注册表 |
| 治理 dashboard | `data/processed/modeling/data_governance_dashboard.html` | 样本、标签、治理图表可视化 |
| 数据预览页 | `data/processed/preview_report.html` | 早期采集预览（非主线） |
| 报告摘要目录 | `docs/reports/` | 各阶段机器生成的 Markdown 摘要 |

## 数据与产物口径

已采集数据（行数以当前磁盘为准）：

| 来源 | 数据 | 覆盖 | 实际行数 |
|---|---|---|---:|
| Tushare | 日行情 | 9/9 | 19,326 |
| Tushare | 日市值/估值/换手率 | 9/9 | 19,326 |
| Tushare | 复权因子 | 9/9 | 19,797 |
| Tushare | 财务三表 | 9/9 | 1,395 |
| Tushare | 财务指标 | 9/9 | 523 |
| Tushare | 指数行情 | 4 个指数 | 15,865 |
| AKShare/巨潮 | 信息披露公告 | 9/9 | 11,347 |
| AKShare/东方财富 | 个股公告 | 9/9 | 13,480 |
| AKShare/东方财富 | 个股研报 | 9/9 | 609 |
| AKShare/东方财富 | 个股新闻 | 9/9 | 90 |
| 东方财富 | 机构调研/业绩说明会 | 9/9 | 870 |
| AKShare/互动易 | 投资者问答 | 7/9 | 176 |

关键产物：

| 产物 | 路径 | 当前状态 |
|---|---|---|
| 事件候选池 | `data/processed/event_candidates.csv` | 15,174 行 |
| CAR/异常市值影响 | `data/processed/event_candidates_scored.csv` | 已生成 |
| 事件分析组 | `data/processed/event_analysis_groups_scored.csv` | 6,398 组 |
| 竞品外溢底表 | `data/processed/peer_spillover_to_yiwei.csv` | 5,367 行 |
| 管理层信号台账 | `data/processed/management/management_signal_ledger.csv` | 5,430 行 |
| 管理层信号覆盖缺口 | `data/processed/management/management_signal_coverage_gaps.csv` | 54 行 |
| ML SSOT 主表 | `data/processed/ml_dataset/` | 5 表，各 6,398 行；SSOT 20/20 通过 |
| 数据治理产物 | `data/processed/data_governance/` | 复核队列、样本策略、审计、overlay |
| 增强建模宽表 v1/v2 | `data/processed/modeling/modeling_dataset_enhanced_v1.csv`、`_v2.csv` | 218 / 244 列 |
| baseline 模型产物 | `data/processed/modeling/baseline_models/` | 已生成 |

> 注：早期文档曾引用 `market_impact_workbench.html`、`cfo_event_evidence_chain.csv`、`rag_*` 系列、`data_quality_dashboard.html`，这些产物当前不在仓库。如需，请重新运行对应脚本生成，不要以为它们已存在。

## 已确认技术事实

- 9 家公司代码和上市日已完整解析。
- `daily_basic.total_mv`、`circ_mv` 为万元口径；输出亿元时除以 10000。
- 主标签 `relative_mv_return_p0_p20` = 公司事件窗口市值收益率 − 同期剔除自身后的同行平均市值收益率。
- 默认时间切分：train ≤2022、valid =2023、test ≥2024；无主标签样本排除但保留审计（249 条）。
- SSOT 校验覆盖主键唯一、表间键集合一致、point-in-time（`as_of_date ≤ event_date`）、时间切分无穿越、目标泄露字段黑名单，全部通过。
- 公告标题和公告类型足以生成自动事件候选池；公告正文/PDF 暂未进入特征。

## 当前真实结论

> **2026-06-14 更新（v3 → v4）**：v2 baseline 的"无样本外信号"结论已被取代。改用**全标注样本（n=3905，带 overlap 特征）+ 行业内相对（截面秩）表示**，v3（HistGBM）test Spearman IC 从 0.000 升到 0.193（去重 0.163，9 家公司全为正）。v4 用 **LightGBM/XGBoost + 早停 + 正则**进一步到 **test IC 0.216、R² 转正 +0.027、2024 不再失效（按年 IC +0.175/+0.255/+0.312）**。可解释性三方一致：SHAP ∩ 置换重要性 ∩ 固定效应+聚类稳健+WCB（**相对规模** p<0.001，相对流动性/低波动/异常机构关注边际）。**⚠️ 其中"异常机构关注"特征受 2026-06-16 发现的 IR 覆盖断层影响（仅 2025-06 后有数据，账本 INV-006），其解释力不可按长期信号解读——见本文顶部更新。** 复现注册表 `data/processed/modeling/v4_models/v4_registry.json`。详见 `reports/V3_MODEL_AND_INTERPRETABILITY_SUMMARY.md`、`reports/NORMALIZED_FEATURES_SUMMARY.md`。定位：**弱而稳健、跨异质公司通用、可解释的排序信号；周期平均成立、非每期可靠。**

以下为 v2 第一版 baseline 的事实，保留以说明改进起点：

- 主模型样本经人工复核 + 样本策略过滤后**很小**：`reviewed_keep_for_training=1` 仅 498 条，实际带标签训练/验证/测试约 **300 / 34 / 164**。
- 按验证集选模型，**胜出的是 `dummy_mean`（直接预测全局均值）**：test MAE≈0.0722，**test Spearman IC = 0.0000**。
- Ridge / ElasticNet / HistGBM 在 test 上 **R² 全为负**（−0.31 ~ −0.07），test IC 接近 0（最高 HistGBM≈0.085，不稳定）。
- HistGBM 训练集 R²≈0.60、test 为负 → 典型过拟合 / 当前特征对 20 日相对市值反应**没有稳定的样本外解释力**。
- 特征组消融中，没有任何一组在 test 上稳定优于 `dummy_mean`。

结论：现阶段不能宣称“特征解释了市值反应”。下一步重点不是堆模型，而是**找到真正有样本外信号的特征 / 扩大有效样本 / 重新审视标签噪声**（详见“下一步建议”）。

## 真实缺口

1. ~~主模型样本过小~~ **已解决**：改用全标注样本 n=3905 + overlap 特征（v3/v4），不再用 n=300 子集。
2. ~~特征样本外信号弱~~ **已缓解**：行业内相对（截面秩）特征 + LightGBM，v4 test IC 0.216、R² 转正；但量级仍弱（IC~0.2、R²~0.03），是近有效市场本质，定位为"弱信号+强方法"。
3. ~~标签被极端值主导~~ **已处理**：训练用 1%/99% winsorize；结果经去极端值（IC 0.13）等对抗检查存活。
4. 事件分类仍是规则初版，“其他”占比高；仅前 100 条做了人工复核，Top 事件需继续复核。
5. 当前 CAR/相对收益基准为剔除自身的竞品等权组合，尚未加入指数基准、滚动 beta、市值加权和显著性检验。
6. 事件重叠污染高；overlap-heavy 样本（约 5,400 条）目前被划入 robustness/case，未进主模型，等于丢弃了 ~90% 数据。
7. 沪市/科创板互动问答不完整（移远、有方在 `cninfo_irm_questions` 采集失败）。
8. 公告正文/PDF/RAG 文本尚未进入特征，文本信号目前只有标题级关键词。

## 下一步建议

> 上一版"先证明有信号"的 6 步（诊断 IC / 扩样本 / 稳标签 / 补 surprise / SHAP+WCB）已全部完成：v4 test IC 0.216、R² 转正、三方可解释。surprise 与大波动检测为诚实 null。当前进入"交付物 + 应用"阶段。课程截止 **2026-07-03**，交 PPT+代码+数据。

剩余按拿分优先：

1. **结果解释与应用（评分 20%，最该补）**：把 SHAP/WCB 结论落到**移为通信案例公司**——逐事件复盘（用 `v4_models/shap/shap_event_examples.csv`）、经济含义解读、对比财务理论，产出**可操作 CFO 披露/投关/风险沟通建议**。
2. **可复现打包（模型质量 40% 的规范性）**：`run_pipeline.py` 串 SSOT→特征→v4→解释→lift/分类 + `requirements.txt`（含已装 lightgbm/xgboost/shap/statsmodels 版本）+ 复现 README + 随机种子核对。
3. **继续 Top 事件人工复核**：把"其他"类压下去，重分类落 overlay（当前仅复核 100/6398）。
4. **PPT 内容**（图表/排版由人做）：用 `reports/PRESENTATION_RESULTS_SUMMARY.md` + `ACCURACY_AND_EVALUATION_GUIDANCE.md` 的话术，主动讲"为何不报裸准确率"。
5. **可选方法补强**：文本 embedding、概率校准、PSI/KS 分布漂移、把截面池从 9 家扩到更宽同行（降低 xsrank 粗糙度、增 WCB 簇数）、查 2024 早段 regime。

主结果与可解释入口：`reports/V3_MODEL_AND_INTERPRETABILITY_SUMMARY.md`、`data/processed/modeling/v4_models/`、`data/processed/modeling/presentation/`。

## 运行与验证

常用生成命令从**仓库根目录**运行（注意不要在 `market-impact-study/` 内直接跑使用 `Path("market-impact-study/...")` 的脚本，否则写到嵌套错误路径）：

```bash
.venv/bin/python market-impact-study/build_ml_ssot_tables.py
.venv/bin/python market-impact-study/validate_ml_ssot.py
.venv/bin/python market-impact-study/build_data_governance_tables.py
.venv/bin/python market-impact-study/build_modeling_assets.py
.venv/bin/python market-impact-study/apply_manual_review_overlay.py
.venv/bin/python market-impact-study/build_enhanced_features.py
.venv/bin/python market-impact-study/build_event_intensity_features.py
.venv/bin/python market-impact-study/train_baseline_models.py
.venv/bin/python market-impact-study/analyze_sample_predictability.py
```

v3/v4 建模链路（行业内相对特征 → LightGBM/XGBoost → 解释 → 面试可读产物）：

```bash
.venv/bin/python market-impact-study/build_normalized_features.py        # 行业内相对/归一化特征 v3
.venv/bin/python market-impact-study/train_v3_normalized_models.py        # v3 模型 + 选型
.venv/bin/python market-impact-study/explain_v3_models.py                 # 置换重要性 + WCB + waterfall
.venv/bin/python market-impact-study/build_surprise_features.py           # 预期差特征（null 实验）
.venv/bin/python market-impact-study/train_v4_gbm_models.py               # v4 LightGBM/XGBoost + SHAP（主模型）
.venv/bin/python market-impact-study/build_presentation_artifacts.py      # 分位 lift + 三分类
.venv/bin/python market-impact-study/build_largemove_model.py             # 大波动检测（null 对照）
```

依赖：除 sklearn/scipy/numpy/pandas 外，v4/解释还需 `lightgbm xgboost shap statsmodels`（已装于 `../.venv`）。

切片闭包检查使用父项目工具：

```bash
.venv/bin/python tools/check.py changed
```

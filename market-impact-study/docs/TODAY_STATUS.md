# 今日状态：核心数据采集与事件标签底座

日期：2026-06-13（下方含 2026-06-14 增补）

## 2026-06-14 增补

06-13 的“明天建议”已基本完成，且跑通第一版 baseline：

- 人工数字复核已应用前 100 条（70 噪声、30 重分类），落 overlay，未改原始 SSOT（见 `reports/MANUAL_REVIEW_SUMMARY.md`）。
- 增强特征 v1（218 列）、事件强度特征 v2（244 列）已生成，入模 136 个 point-in-time 安全特征（见 `reports/ENHANCED_FEATURES_SUMMARY.md`、`reports/EVENT_INTENSITY_FEATURES_SUMMARY.md`）。
- 第一版 baseline + 消融已跑通（见 `reports/BASELINE_MODEL_SUMMARY.md`、`reports/SAMPLE_PREDICTABILITY_DIAGNOSTICS.md`）。

**诚实结论（v2）**：主模型带标签样本约 train 300 / valid 34 / test 164；按验证集选模型胜出的是 `dummy_mean`（预测全局均值），test Spearman IC = 0，Ridge/ElasticNet/HistGBM 的 test R² 全为负。即 v2 特征对 20 日相对市值反应**没有稳定的样本外解释力**。

## 2026-06-14/15 增补（v3 → v4，已突破）

后续诊断 + 重做特征/模型后，结论已被取代：

- **扩样本 + 行业内相对（截面秩）特征**：从 n=300 主子集改用全标注样本 n=3905 + overlap 特征，v3（HistGBM）test IC 0.000→0.193。
- **v4（LightGBM/XGBoost + 早停 + 正则）**：test IC **0.216**、R² 转正 +0.027、2024 不再失效；复现注册表落盘（`data/processed/modeling/v4_models/v4_registry.json`）。
- **可解释三方一致**：SHAP ∩ 置换重要性 ∩ 固定效应+聚类稳健+WCB（相对规模 p<0.001）。
- **面试可读**：分位首尾差 ~8pp、负向冲击 recall 0.53/PR-AUC 0.59、高置信方向准确率 65%@30%覆盖。
- **诚实 null（强化评估科学性）**：surprise 预期差特征无增量；大波动检测 AUC≈0.50（信号是方向因子倾斜，非波动率）。
- **课程对齐**：作业评分无 accuracy 硬门槛，重"评估科学性+预测效果+特征财务理论+解释+建议"；准确率口径见 `reports/ACCURACY_AND_EVALUATION_GUIDANCE.md`。

详见 `PROJECT_HANDOFF.md` 与 `reports/V3_MODEL_AND_INTERPRETABILITY_SUMMARY.md`、`reports/PRESENTATION_RESULTS_SUMMARY.md`。

---


## 结论

已完成 9 家公司核心结构化数据采集、公开源事件数据采集、事件候选池生成、CAR/相对市值反应计算、管理层信号台账、ML 建模准入诊断、ML SSOT 建模数据集和数据计算验证。

今天形成的底座已经足够支撑下一步构建第一版机器学习解释模型。`event_master`、`label_master`、`feature_master`、`split_master`、`data_dictionary` 已生成并通过 SSOT 校验。

## 已完成

| 模块 | 产物 | 结果 |
| --- | --- | --- |
| Tushare token probe | `data/tushare_probe/` | 9 家公司全部解析成功；核心行情、估值、财务、指数接口可用 |
| Tushare 核心采集 | `data/raw/tushare/` | 118 个接口-公司任务成功，4 个为空，9 个 `anns_d` 无权限 |
| AKShare 公开源采集 | `data/raw/akshare/` | 东方财富公告、研报、新闻 9 家全成功；巨潮部分接口有缺口 |
| 东方财富 IR | `data/raw/eastmoney_ir/` | 9 家全部成功，机构调研/业绩说明会 870 行 |
| 采集汇总 | `data/summary/collection_inventory.csv` | 已生成 |
| 事件候选池 | `data/processed/event_candidates.csv` | 15,174 行 |
| CAR/事件组 | `data/processed/event_analysis_groups_scored.csv` | 6,398 组 |
| 管理层信号 | `data/processed/management/management_signal_ledger.csv` | 5,430 行 |
| ML readiness | `data/processed/ml_readiness/` | 已生成事件重叠和资本动作准入诊断 |
| ML SSOT 建模数据集 | `data/processed/ml_dataset/` | 5 张主表已生成；schema contract 已落盘 |
| ML SSOT 校验 | `docs/reports/ML_SSOT_VALIDATION_SUMMARY.md` | 20/20 项通过；主键、切分、point-in-time、泄露字段均通过 |
| 数据治理 | `data/processed/data_governance/` | 已生成复核队列、标签质量摘要、事件类型审计和样本策略 |
| 建模入口与图表 | `data/processed/modeling/`、`figures/data_governance/` | 已生成建模宽表、复核 overlay 模板、5 张治理图和 HTML dashboard |
| 数据验证 | `docs/reports/VALIDATION_REPORT.md` | 基础检查 9/9 通过；CAR 抽样复算 30/30 通过 |
| 预览报告 | `data/processed/preview_report.html` | 已生成 |

## 关键数据规模

| 数据 | 行数 |
| --- | ---: |
| Tushare 日行情 | 19,326 |
| Tushare 市值估值 | 19,326 |
| Tushare 复权因子 | 19,797 |
| Tushare 财务指标 | 523 |
| Tushare 财务三表 | 1,395 |
| Tushare 指数行情 | 15,865 |
| 东方财富个股公告 | 13,480 |
| 巨潮信息披露公告 | 11,347 |
| 东方财富研报 | 609 |
| 东方财富新闻 | 90 |
| 东方财富机构调研/业绩说明会 | 870 |
| 互动问答 | 176 |
| `event_master` | 6,398 |
| `label_master` | 6,398 |
| `feature_master` | 6,398 行，49 列 |
| 默认 train/valid/test 样本 | 3,905 / 624 / 1,620 |
| 排除但保留审计样本 | 249 |
| SSOT 校验项 | 20/20 通过 |
| 人工复核队列 | 360 |
| 人工复核 overlay 模板 | 100 |
| 建模宽表 | 6,398 行，120 列 |
| 数据治理图表 | 5 |
| 第一版主模型候选样本 | 444 |
| clean 稳健性样本 | 54 |
| 重污染稳健性/案例样本 | 5,484 |

## 已固定的 SSOT 口径

| 表 | 职责 | 备注 |
| --- | --- | --- |
| `event_master.csv` | 事件组唯一口径 | 只放事件元数据、来源、类型、重叠污染诊断 |
| `label_master.csv` | 标签唯一口径 | 5/20/60 日相对市值收益率和异常市值影响；主标签为 `relative_mv_return_p0_p20` |
| `feature_master.csv` | 第一版种子特征 | 只放事件日前或事件披露本身可获得的特征；不放 CAR、窗口收益、结束日等后验字段 |
| `split_master.csv` | 固定时间切分 | train<=2022，valid=2023，test>=2024；无主标签样本排除但保留审计 |
| `data_dictionary.csv` | 字段字典 | 字段来源、业务含义、泄露风险 |
| `schema_contract.json` | schema 契约 | 后续模型和图表优先读取该契约下的表 |

## 已完成的数据治理

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| 人工复核队列 | `data/processed/data_governance/top_event_review_queue.csv` | 优先复核极端标签、移为自身事件、`其他` 类和同窗重叠事件 |
| 标签分布摘要 | `data/processed/data_governance/label_distribution_summary.csv` | 检查 5/20/60 日相对市值反应和异常市值影响分布 |
| 事件类型审计 | `data/processed/data_governance/category_audit_summary.csv` | 定位“其他”类和高重叠事件类型 |
| 样本策略主表 | `data/processed/data_governance/sample_policy_master.csv` | 将样本分为主模型、clean 稳健性、案例/审计、排除 |
| 数据治理报告 | `docs/reports/DATA_GOVERNANCE_SUMMARY.md` | 报告数据治理结论 |
| 样本使用策略 | `docs/SAMPLE_POLICY.md` | 固定后续训练、稳健性和案例复盘边界 |
| 计算与评估协议 | `docs/METHOD_AND_EVALUATION_PROTOCOL.md` | 补齐标签计算、Oracle、模型评估、黑箱检测和报告边界 |
| 建模宽表 | `data/processed/modeling/modeling_dataset_v1.csv` | 后续 EDA、训练和图表统一入口 |
| 复核 overlay 模板 | `data/processed/data_governance/manual_review_overlay_template.csv` | 前 100 条高优先级事件人工复核入口 |
| 图表清单 | `figures/data_governance/figure_manifest.csv` | 报告/PPT 图表索引，包含每张图为什么做 |
| 数据治理 dashboard | `data/processed/modeling/data_governance_dashboard.html` | 可直接打开查看样本、标签和治理图表 |
| 建模资产报告 | `docs/reports/MODELING_ASSETS_SUMMARY.md` | 说明宽表、模板和图表的生成依据与使用边界 |

## 当前缺口

| 缺口 | 影响 | 处理建议 |
| --- | --- | --- |
| Tushare `anns_d` 无权限 | 不能用 Tushare 公告标题 | 已由东方财富公告和巨潮公告替代，不阻塞 |
| 巨潮部分公司接口失败 | 移为通信等个别源缺口 | 东方财富公告覆盖完整，后续仅作为补充 |
| 新浪机构评级接口失败 | 该源不可用 | 已有东方财富研报 609 行，可放弃新浪源 |
| Dashboard 生成失败 | `build_data_quality_dashboard.py` 需要 `cfo_event_evidence_chain.csv` | 明天先生成 RAG/CFO 主表或改 dashboard 降级读取 |
| 事件分类“其他”占比高 | 影响报告解释质量 | 已进入 360 条人工复核队列，后续人工修正后单独落表 |
| 事件重叠污染高 | 不适合直接做简单因果归因 | 已分为主模型候选、clean 稳健性、重污染案例/附录 |
| clean 样本较少 | 严格剔除重叠后样本不足以单独支撑主模型 | clean 样本用于稳健性/敏感性检验，不单独作为主模型 |

## 明天建议入口

1. 人工处理 `top_event_review_queue.csv` 前 100 条，优先修正交易机制、流程公告和“其他”类。
2. 将人工修正结果落为独立 overlay 表，不直接改原始 SSOT。
3. 按 `METHOD_AND_EVALUATION_PROTOCOL.md` 生成标签、样本治理和后续模型评估图表。
4. 在不改变 SSOT 样本和标签口径的前提下，追加 point-in-time 财务、估值、交易历史、管理层滚动和竞品环境特征。
5. 跑第一版 Ridge/ElasticNet baseline 和 LightGBM/XGBoost，并按协议输出 MAE、IC、R2、分组评估和消融结果。

## 运行口径

所有旧脚本必须从仓库根目录运行，例如：

```bash
.venv/bin/python market-impact-study/build_event_candidates.py
```

不要从 `market-impact-study/` 目录内直接运行使用 `Path("market-impact-study/data/...")` 的旧脚本，否则会写到嵌套错误路径。

新增 SSOT 入口：

```bash
.venv/bin/python market-impact-study/build_ml_ssot_tables.py
.venv/bin/python market-impact-study/validate_ml_ssot.py
.venv/bin/python market-impact-study/build_data_governance_tables.py
.venv/bin/python market-impact-study/build_modeling_assets.py
```

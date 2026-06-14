# Market Impact Study 文档索引

本文档目录是 `market-impact-study` 的唯一 Markdown 文档入口。数据产物仍保留在 `data/`，HTML 报告仍保留在 `data/processed/`。

## 接手入口

先读这三份（项目现状 + 方法权威口径）：

- `PROJECT_HANDOFF.md`：项目现状、已完成产物、真实缺口、下一步建议（含第一版 baseline 诚实结论）。
- `PROJECT_PLAN.md`：题目、标签、特征组、模型与检验、十天执行计划。
- `METHOD_AND_EVALUATION_PROTOCOL.md`：标签/特征/模型/稳健性/报告边界的权威计算口径。

辅助口径文档：

- `PRESENTER_GUIDE.md`：**汇报人手册**——全流程、做了什么/效果、要补的知识、课程与 CFO 两套口径、问答预案。
- `NEXT_STEPS_AND_ROLES.md`：现状诚实判断、后续人机分工、特征/建模/解释下一步。
- `SAMPLE_POLICY.md`：样本分层使用策略与当前分布。
- `MANUAL_REVIEW_CODEBOOK.md`：人工数字复核填报码表。
- `TODAY_STATUS.md`：最近一次日切状态。

阶段摘要（机器生成，位于 `reports/`）：

- **最新主结果（先看这三份）**：`V3_MODEL_AND_INTERPRETABILITY_SUMMARY.md`（v3→v4 模型+可解释,IC 0.22）、`PRESENTATION_RESULTS_SUMMARY.md`（lift+三分类，面试可读）、`ACCURACY_AND_EVALUATION_GUIDANCE.md`（该报哪些"准确率"、对应课程评分项）。
- 特征链路：`NORMALIZED_FEATURES_SUMMARY.md`（行业内相对特征）、`SURPRISE_FEATURES_SUMMARY.md`（预期差，null result）、`ENHANCED_FEATURES_SUMMARY.md`、`EVENT_INTENSITY_FEATURES_SUMMARY.md`。
- 建模底座：`ML_SSOT_SUMMARY.md`、`ML_SSOT_VALIDATION_SUMMARY.md`、`MODELING_ASSETS_SUMMARY.md`、`BASELINE_MODEL_SUMMARY.md`、`SAMPLE_PREDICTABILITY_DIAGNOSTICS.md`。
- 数据与治理：`VALIDATION_REPORT.md`、`DATA_GOVERNANCE_SUMMARY.md`、`MANUAL_REVIEW_SUMMARY.md`、`ML_READINESS_SUMMARY.md`、`CFO_EVENT_EVIDENCE_CHAIN_SUMMARY.md`。

## 文档组织规则

- 新增 Markdown 只放在 `docs/` 下。
- `data/` 只放数据、HTML、CSV、JSON、PDF、JSONL 等可重建或分析产物。
- 生成脚本如需写 Markdown 摘要，应输出到 `docs/reports/`。

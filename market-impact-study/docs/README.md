# Market Impact Study 文档索引

本目录是 `market-impact-study` 的唯一 Markdown 文档入口。数据产物保留在 `data/`，HTML 报告保留在 `data/processed/`。

> **2026-06-18 主线重构**：现行唯一主线 = **解释市值变动**(估值水平解释 → 严谨归因 → 三角验证 → 交付仪表板,INV-035~043)。**已废弃**:① 资本动作→20日反应的事件因果线(INV-015~028,短期反应纯噪声,INV-043 留档);② 预测线 v3/v4(INV-009/010);③ 旧因果"机构关注→反应"(INV-007/008/011 安慰剂证伪)。废弃支线结论全留存于 `DECISION_LEDGER.md`。

## 接手入口（先读这三份）

- `DECISION_LEDGER.md`：**项目大脑**，顶部「主线声明」+ 决策/不变量账本(INV-001~043 + ADR)。**每个新 session 先读这份**，不重审已定、不踩已知;**现行主线见顶部「主线声明」(INV-035~043)**。
- `PROJECT_HANDOFF.md`：项目现状、已完成产物、真实缺口、下一步建议。
- `PROJECT_PLAN.md`：题目、标签、特征组、模型与检验、执行计划。

## 权威口径文档

- `METHOD_AND_EVALUATION_PROTOCOL.md`：标签/特征/模型/稳健性/报告边界的权威计算口径。
- `SAMPLE_POLICY.md`：样本分层使用策略与当前分布。
- `MANUAL_REVIEW_CODEBOOK.md`：人工数字复核填报码表（复核仍在进行，当前 100/6398）。

## 汇报交付

- `PRESENTER_GUIDE.md`：汇报人手册——全流程、做了什么/效果、要补的知识、课程与 CFO 两套口径、问答预案。

## 现行阶段摘要（市值变动主线,INV-035~043）

**交付产物**

- `data/processed/cfo_dashboard.html`(`build_cfo_dashboard.py` 产):6 段交付仪表板,只画过三角验证的硬结论。浏览器打开。
- 主线产物 JSON 全在 `data/processed/modeling/cate_14firm/`:`valuation_model.json`(估值解释)、`mcap_attribution.json`(逐家分解+战略)、`attribution_rigorous.json`(严谨归因)、`drivers_triangulation.json`(5 方法验证)。

> 主线硬结论(wild cluster bootstrap + 5 方法 consilience):**H1 成长被打折 5/5、H2 低杠杆↔高估值 5/5(稳健关联非因果)、H3 盈利驱动估值证伪 1/5**;移为纯出口但海外增速仅 +6% vs 赢家 +50~69%;横截面估值 ~50% 是情绪/小样本不可约(诚实天花板)。详见账本 INV-039~043。

> 🗑️ 2026-06-18 已删除 5 份废弃事件因果线时代报告(`YIWEI_CFO_CASE`/`FIRM_PROFILES`/`PEER_COMPARISON`/`POWER_ANALYSIS`/`SPEC_CURVE`),结论留存于账本 INV-019/021/022/024/025。当前主线报告 = `reports/MARKET_CAP_EXPLANATION.md`(2026-06-18 新建,主线唯一权威报告);汇报话术见 `PRESENTER_GUIDE.md`;结论详见账本 INV-035~046。

**数据底座与治理（现行口径）**

- `ML_SSOT_VALIDATION_SUMMARY.md`：SSOT 校验 20/20 通过。
- `DATA_GOVERNANCE_SUMMARY.md`：数据治理结论。
- `MANUAL_REVIEW_SUMMARY.md`：人工复核结论。
- `VALIDATION_REPORT.md`：数据基础检查 + CAR 抽样复算。

## 文档组织规则

- 新增 Markdown 只放在 `docs/` 下；现行文档放顶层或 `reports/`。**已废弃/被取代的直接删除(结论入 `DECISION_LEDGER.md`),不再保留归档目录。**
- `data/` 只放数据、HTML、CSV、JSON、PDF、JSONL 等可重建或分析产物。
- 生成脚本如需写 Markdown 摘要，应输出到 `docs/reports/`。

# Market Impact Study 文档索引

本文档目录是 `market-impact-study` 的唯一 Markdown 文档入口。数据产物仍保留在 `data/`，HTML 报告仍保留在 `data/processed/`。

## 接手入口

- `PROJECT_HANDOFF.md`：项目现状、已完成产物、真实缺口、下一步建议。
- `reports/VALIDATION_REPORT.md`：数据质量和 CAR 抽样复算摘要。
- `reports/CFO_EVENT_EVIDENCE_CHAIN_SUMMARY.md`：CFO 事件-市值变化-证据链主表摘要。
- `reports/ML_READINESS_SUMMARY.md`：统计/ML 建模准入诊断摘要。

## 文档组织规则

- 新增 Markdown 只放在 `docs/` 下。
- `data/` 只放数据、HTML、CSV、JSON、PDF、JSONL 等可重建或分析产物。
- 生成脚本如需写 Markdown 摘要，应输出到 `docs/reports/`。

# CFO 事件-市值变化-证据链主表摘要

- 主表事件组数：6550
- 移为通信自身事件组：782
- 有 RAG/结构化证据事件组：1167，覆盖率 17.82%
- 证据等级分布：无证据=5383；强证据=738；辅助证据=429
- 正向 Top1：2025-01-06 广和通《2025年第一次临时股东大会决议公告》，20日客观市值变化 141.017 亿元，证据=无证据
- 负向 Top1：2016-01-01 高新兴《关于公司董事、董事会秘书辞职的公告》，20日客观市值变化 -103.1151 亿元，证据=无证据
- 有证据正向 Top1：2019-01-30 高新兴《略增 预计净利润52500-59000万》，20日客观市值变化 70.4033 亿元，证据=辅助证据
- 有证据负向 Top1：2021-04-20 移远通信《:2020年年度报告》，20日客观市值变化 -82.9732 亿元，证据=辅助证据

## 输出文件

- `data/processed/cfo_event_evidence_chain.csv`：全量中文主表，CAR 放在辅助列。
- `data/processed/cfo_event_evidence_chain_top_positive.csv`：20日客观市值变化正向 Top100。
- `data/processed/cfo_event_evidence_chain_top_negative.csv`：20日客观市值变化负向 Top100。
- `data/processed/cfo_event_evidence_chain_top_positive_with_evidence.csv`：有证据的 20日客观市值变化正向 Top100。
- `data/processed/cfo_event_evidence_chain_top_negative_with_evidence.csv`：有证据的 20日客观市值变化负向 Top100。
- `data/processed/cfo_event_evidence_chain_priority_top.csv`：按客观变化绝对值、事件优先级和证据等级综合排序 Top100。

## 口径

- 客观市值变化使用事件窗口后的总市值变化，单位为亿元。
- 相对竞品变化 = 事件公司市值收益率 - 同期竞品平均市值收益率，并按事件前市值换算为亿元。
- CAR 和异常市值影响只作为辅助列，不作为主排序口径。
- 证据等级保留强证据、辅助证据、弱证据、无证据；弱证据不应直接写入结论。

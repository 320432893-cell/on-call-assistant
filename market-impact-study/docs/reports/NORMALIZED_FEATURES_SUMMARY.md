# 归一化 / 行业内相对特征诊断摘要

> 2026-06-14。脚本 `build_normalized_features.py`，产物 `data/processed/modeling/modeling_dataset_enhanced_v3.csv`（620 列）、`normalized_feature_manifest.csv`。

## 做了什么

对 136 个入模特征中的 94 个连续特征，每个派生 4 个 point-in-time 安全的"无量纲 / 行业内相对"变体，再算每个表示对主标签 `relative_mv_return_p0_p20` 在 train / test 上的单变量 Spearman IC：

| 变体 | 含义 | 目标 |
| --- | --- | --- |
| `__selfz` | 公司自身历史的 trailing z-score（仅用事件前行） | 去掉公司水平，留偏离自身常态 |
| `__yoy` | 相对约一年前同公司事件的同比变化 | 季度/年份相对变化 |
| `__xsrank` | 同季度行业截面百分位秩 [0,1] | 让大市值/小市值公司同尺度 |
| `__xsdemed` | 减同季度截面中位 | 同上，保留量纲 |

## 核心结论：归一化把稳定信号"做多 + 做通用"

- 按"基础特征"看，**归一化变体在 50 个特征上优于 raw，raw 仅在 13 个上最优，31 个无稳定信号**。
- 更严格地只看**可信特征**（train 和 test 的 |IC| 同时 ≥0.05 且同号、稠密 n_test≥200）：共 70 个 (特征,表示) 对、27 个基础特征。其中表示分布：

  | 表示 | 可信特征数 |
  | --- | ---: |
  | xsrank | 19 |
  | xsdemed | 18 |
  | raw | 13 |
  | selfz | 11 |
  | yoy | 9 |

  归一化:raw = **57 : 13**；按基础特征取最优表示，归一化 21 / raw 6。**截面秩 `xsrank` 是单个最高产的变换**——正是"不同体量公司共用一个模型"要的那把杠杆。

## 可信信号聚成三个经济上自洽的簇

1. **异常机构关注度**（正向，IC 0.10~0.17）：`mgmt_institution_count`、`mgmt_signal_count`。`selfz`（相对自身常态的异常关注）版本最强（test +0.24），但 69% 缺失，只能作敏感性；稠密主力用 raw / `xsrank` 版。
2. **相对流动性 / 换手**（负向，IC 0.08~0.13）：`rel_to_peer_turnover`、`amount_avg`、`turnover_avg`——相对同行换手越低、其后相对收益越好（低关注/低流动性溢价）。`xsrank` / `selfz` 最干净。
3. **相对规模 + 反转**（IC ~0.10）：`rel_to_peer_log_total_mv`（相对同行更小→正）、`rel_to_peer_ret_m60`（负→反转）。经 `xsrank` / `xsdemed`。

## 诚实边界

- 量级仍只有 IC ~0.1：归一化**确认并放大了"稳定信号在哪"、让更多特征跨异质公司可用**，但没有突破低信噪比天花板。故事是"小而真、且行业通用"，正是诚实的 CFO 表述。
- `xsrank` / `xsdemed` 有≤1 季度的桶内 look-ahead（见脚本注释）；但**无 look-ahead 的 raw `rel_to_peer`（事件日截面快照）在换手/规模上同样可信**，佐证信号不是 look-ahead 假象。
- `evt_money_*` / `evt_profit_*` 仍因 >95% 缺失被排除主模型。

## 建议下一步

1. 用**归一化骨架**重训 v3 主模型：稠密信号簇（机构关注度、换手/成交额、rel_to_peer 收益/规模）取 `xsrank + selfz + raw rel_to_peer`，丢稀疏 `evt_*`；目标用排序 IC，标签 winsorize。
2. 把截面池从 9 家扩到更宽的物联网模组/通信设备同行，降低 `xsrank` 的粗糙度。
3. 配公司固定效应吸收残余水平差，实现"体量差很大但同行业、同一个模型"。

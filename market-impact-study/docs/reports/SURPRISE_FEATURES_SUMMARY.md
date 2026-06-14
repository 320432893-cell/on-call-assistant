# 预期差（surprise）特征实验摘要（null result）

> 2026-06-14。脚本 `build_surprise_features.py`，产物 `modeling_dataset_enhanced_v3s.csv`、`surprise_feature_manifest.csv`。诚实结论：**做了、测了、基本没用**——保留为有记录的 null result，主模型不纳入。

## 动机

事件研究里"预期差"通常是与异常收益最相关的变量，而项目此前完全没有。补 8 个 point-in-time 安全的 surprise 特征：
- 业绩预告结构化：`surprise_fcst_pchg_mid/abs/dir/recent`（最新 ann_date≤event_date 的预告净利变动%中点、幅度、方向、是否 100 天内）。
- 已实现盈利同比（来自利润表）：`surprise_earn_yoy`、`surprise_earn_yoy_vs_self`（当期 YoY 减自身近 4 期均值，SUE 式自归一化）。
- 上述连续量的同季度截面秩。

覆盖：预告 100 天内事件 3641，盈利 YoY 可得 6106/6398。

## 单变量 IC（train→test）

| 特征 | ic_train | ic_test | 稳定 |
| --- | ---: | ---: | --- |
| surprise_fcst_pchg_mid | +0.052 | -0.128 | ✗ 变号 |
| surprise_fcst_pchg_abs | +0.031 | -0.164 | ✗ 变号 |
| surprise_earn_yoy | +0.072 | -0.000 | ✗ test 无 |
| **surprise_earn_yoy_vs_self** | -0.065 | -0.077 | ✓ 唯一稳定（弱、负） |
| surprise_fcst_pchg_mid__xsrank | +0.097 | -0.032 | ✗ 变号 |
| surprise_earn_yoy_vs_self__xsrank | +0.016 | -0.121 | ✗ 变号 |

只有"盈利同比相对自身趋势"sign-stable，且为**负**（超预期越多→其后相对市值越弱，类似 buy-the-rumor/反转），但仅 ~0.07。

## 加入模型后（v4 + surprise）

| 模型 | test IC（无 surprise → 有 surprise） |
| --- | --- |
| LightGBM | 0.216 → **0.220**（噪声内） |
| XGBoost | 0.198 → 0.197 |

test IC 按年（有 surprise）：2024 +0.157 / 2025 +0.267 / 2026 +0.253，与不加基本一致。

## 结论与处理

- 预期差对 **20 日相对市值反应**没有稳定样本外增量——大概率因为预告在披露时已被定价，且相对（剔除行业）口径进一步消掉了共同的盈利驱动。
- **主模型保持 v4（不含 surprise）以求简洁**；surprise 作为"假设—构造—检验—证伪"的方法论记录保留。
- 这是诚实严谨定位下的正面材料：textbook 假设被严格 PIT 检验后证否，比硬塞进去更可信。

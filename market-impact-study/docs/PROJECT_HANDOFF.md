# Market Impact Study 项目交接

> 最近核对：2026-06-18。本文件以当前磁盘真实产物为准。**唯一权威连续性载体是 `docs/DECISION_LEDGER.md`(顶部「主线声明」+ INV + ADR),新 session 先读它。** 本文件是入口索引。
> ⚠️ **2026-06-18 主线已重构**:旧的"资本动作 → 20 日短期反应"事件因果线**已废弃**(短期反应 R²<0 = 纯噪声,见 INV-043),旧预测线 / 旧 8 段 ML 仪表板同属废弃。本文件描述的是**当前唯一主线 = 解释市值变动**(INV-035~043)。

## 项目目标(主线声明,2026-06-18)

唯一主线 = **解释"市值变动"** —— 为什么涨/跌、移为为什么卡、该学谁;预测只是建议层,不是主功能。研究主体 = **移为通信(300590)** + **13 家同行**。

核心方法:
1. **恒等分解**(会计级精确):Δln 市值 = Δln 营收(经营通道) + Δln(PS)(估值再定价)。
2. **价值驱动**(成长被打折 β<1、低杠杆↔高估值)经 **wild cluster bootstrap + 5 方法三角验证**(推断/设定/识别/证伪/泛化)。
3. **战略画像**(主营构成 / 海外占比·增速)。
4. **诚实天花板**(横截面估值 ~50% 是情绪/小样本不可约)。

## 当前真实进度(截至 2026-06-18)

数据底座 + 基本面面板已就绪;**主线已闭环**(估值解释 → 严谨归因 → 三角验证 → 废弃线收口 → 交付仪表板):

- **估值水平解释**(INV-035~038):`build_valuation_model.py` —— Y=超额估值(log PS 剥年度β+规模),X=基本面驱动;单调约束 GBT + SHAP + ElasticNet;嵌套 CV 机器调参 + L1 正则 + 公司固定效应辨真伪驱动;样本外/LOFO 验证。诚实天花板 ~50%(财务+非财务都榨干)。
- **市值变动归因**(INV-039):`build_mcap_attribution.py` —— 恒等分解(逐家经营 vs 估值通道)+ 战略画像(海外占比/增速)+ 再定价回归 + 红队删伪规律。
- **严谨归因**(INV-040):`build_attribution_rigorous.py` —— 定义级污染标记 + 分组 interventional SHAP + 公司层自助稳定 + 闭合瀑布。结论:唯"杠杆/流动性"组过三关。
- **三角验证**(INV-041):`verify_drivers_triangulation.py` —— 手写 wild cluster bootstrap(N=14 少簇唯一正确推断,size 自检)+ 5 方法 consilience。**H1 成长打折 5/5、H2 低杠杆 5/5、H3 盈利证伪 1/5。**
- **废弃事件线收口**(INV-043):`verify_event_dml_robust.py` —— 机器调 nuisance(按预测准、不碰 ATE)自证手调没作弊;三动作全 null,事件线正式废弃留档。
- **交付仪表板**(INV-042):`build_cfo_dashboard.py` —— 只画过三角验证的硬结论,自包含 ECharts;产物 `data/processed/cfo_dashboard.html`(~1026KB)。⚠️ **未经浏览器视觉确认**(环境无头)。

## 当前真实结论(诚实终态,详见账本 INV-039~043)

- **成长被打折**(H1):营收涨、估值倍数压缩,市值对营收弹性 β≈0.58 < 1,**三角验证 5/5 可信**(赛道商品化)。
- **低杠杆 ↔ 高估值**(H2):超额 PS ~ 资产负债率为负,**5/5 可信**,领先-滞后偏正向(削弱反向疑虑);**仍是稳健关联、非因果。**
- **盈利驱动估值**(H3):剥掉与营收的算术相关后**只过 1/5,证伪** —— "盈利驱动估值"大半是算术假象。
- **移为诊断**:纯出口型(海外占比高)但**海外增速仅 +6% vs 赢家 +50~69%** —— 方向对、份额没抢到;市值卡在营收增速没跑赢同行 + 全行业估值压缩。
- **诚实天花板**:横截面估值约 ~50% 不可约(情绪/叙事/N=14 小样本),扩样本才是真瓶颈。
- **伪规律已剔除**:成功公式 / 盈利驱动 / SHAP 裸排名均不进交付。

## 核心可用入口

| 入口 | 路径 | 用途 |
|---|---|---|
| **项目大脑** | `docs/DECISION_LEDGER.md` | 主线声明 + INV + ADR,唯一连续性权威 |
| **主线报告** | `docs/reports/MARKET_CAP_EXPLANATION.md` | 当前主线唯一权威报告(命题/分解/三条硬结论/移为诊断/天花板/局限) |
| **汇报手册** | `docs/PRESENTER_GUIDE.md` | 全流程 + 诚实故事线 + 关键数字 + 两套口径 + 问答预案 |
| **交付仪表板** | `data/processed/cfo_dashboard.html` | 6 段:移为诊断 / 逐家分解 / 战略画像 / 验证过的硬结论 / 能解释vs情绪 / 方法透明。浏览器打开 |
| 估值模型产物 | `data/processed/modeling/cate_14firm/valuation_model.json` | 超额估值解释、SHAP、OOT/LOFO、FE 真伪 |
| 市值变动归因 | `data/processed/modeling/cate_14firm/mcap_attribution.json` | 逐家分解 + 战略画像 + 弹性β + 再定价R² |
| 严谨归因 | `data/processed/modeling/cate_14firm/attribution_rigorous.json` | 分组 SHAP + 自助稳定 + 污染标记 |
| 三角验证 | `data/processed/modeling/cate_14firm/drivers_triangulation.json` | H1/H2/H3 的 5 方法 verdict |
| 可操作解释层 | `data/processed/modeling/cate_14firm/driver_explanation.json` | 反事实(估值/市值)+ 依赖形状 + 逐家叙述 + 再定价触发,带污染防火墙(INV-044) |
| 白盒证明 | `data/processed/modeling/cate_14firm/whitebox_proof.json` | 白盒线性 vs GBT 同协议 R²、公式版反事实、GBT↔白盒一致性证明(INV-045) |
| 废弃线收口 | `data/processed/modeling/cate_14firm/event_dml_robust.json` | 事件三动作机器调 ATE 全 null(留档) |
| 基本面面板 | `data/processed/modeling/fundamental_panel.csv` | 14 家 × 报告期 PIT 基本面(38 特征) |

> **已废弃(结论保留在账本,勿再扩展)**:① 事件因果线(资本动作→20日反应,INV-015~028 的 DML/因果森林/聚类自助/合成控制/功效/设定曲线,产物 `cate_14firm/cate_*`、`heterogeneity_14firm/`)= INV-043 留档,短期反应纯噪声;② 预测线 v3/v4 = INV-009/010 弱 IC~0.14;③ 旧因果"机构关注→反应" = INV-007/008/011 安慰剂证伪。`docs/reports/` 下 5 份事件线时代报告(`YIWEI_CFO_CASE`/`FIRM_PROFILES`/`PEER_COMPARISON`/`POWER_ANALYSIS`/`SPEC_CURVE`)**已于 2026-06-18 删除**(结论存账本 INV-019/021/022/024/025)。**当前主线报告 = `docs/reports/MARKET_CAP_EXPLANATION.md`**(2026-06-18 新建)。

## 运行与复现(从仓库根运行)

**一键复现(推荐,INV-047)** —— 跨双 venv 自动按序跑主线 9 步,失败即停:

```bash
.venv/bin/python market-impact-study/run_pipeline.py            # 默认:不联网采集、含事件线留档、出仪表板
# 选项:--with-collect(联网采集)  --no-event(跳废弃事件线)  --no-dashboard
```

实测全链 9/9 通过、~13.5min(慢点:严谨归因自助 346s、事件线 DML 288s、估值调参 142s)。下面是分步手动序(调试单步用):

数据底座(主 `.venv`,Tushare 2000 积分 token,已采集):

```bash
.venv/bin/python market-impact-study/collect_tushare_extended.py   # 全量采集(fina_indicator/三表/主营构成/北向…)
.venv/bin/python market-impact-study/build_fundamental_panel.py    # → fundamental_panel.csv(38 特征 PIT)
```

主线(估值解释 → 归因 → 三角验证 → 交付仪表板,主 `.venv`):

```bash
.venv/bin/python market-impact-study/build_valuation_model.py        # INV-035~038 → valuation_model.json
.venv/bin/python market-impact-study/build_mcap_attribution.py       # INV-039 → mcap_attribution.json
.venv/bin/python market-impact-study/build_attribution_rigorous.py   # INV-040 → attribution_rigorous.json(import build_valuation_model)
.venv/bin/python market-impact-study/verify_drivers_triangulation.py # INV-041 → drivers_triangulation.json
.venv/bin/python market-impact-study/build_driver_explanation.py     # INV-044 → driver_explanation.json(反事实/依赖/叙述/触发,污染防火墙)
.venv/bin/python market-impact-study/verify_whitebox_explanation.py  # INV-045 → whitebox_proof.json(白盒 vs 黑盒 R²、公式版反事实、完善证明)
.venv/bin/python market-impact-study/build_cfo_dashboard.py          # INV-042 → cfo_dashboard.html(放最后,只读 JSON,现 8 段)
```

废弃事件线收口(隔离 `.venv-causal`,econml,见 `requirements-causal.txt`,仅留档不进交付):

```bash
.venv-causal/bin/python market-impact-study/verify_event_dml_robust.py  # INV-043 → event_dml_robust.json
```

静态闸(从仓库根):`.venv/bin/python tools/check.py changed`

> ⚠️ **复现注意**:① 主线脚本用 `market-impact-study/...` 根相对路径,**必须从仓库根 `on-call-assistant-20260514/` 运行**;② 改了产生 JSON 的脚本后**务必重跑产物再 build 仪表板**(曾出现源码修了、JSON 没重跑导致仪表板显示 undefined 的漂移);③ 尚无 `run_pipeline.py` 串全链,当前需手动按上序执行。

## 已确认技术事实(INV-004)

- `daily_basic.total_mv`/`circ_mv` 为**万元**口径,输出亿元除以 10000。
- universe = `peer_universe.csv` 中 `include==1` 的 14 家纯模组/终端(移为 + 13 家);改该表即跟随(ADR-003)。
- 财务数据已派子 agent 上网核对(移为 2023 营收/归母净利/毛利率三项与公开源一致,INV-036)。

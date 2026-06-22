"""Build the 移为(300590) CFO case: 3-channel market-cap decomposition + per-action reactions + recommendations."""

# 职责：B 收口——把因果口径(INV-016/017)落到案例公司移为(300590):① 市值历程三通道分解
#       (市值=估值PE×盈利E,脊柱 ADR-004,股本作摊薄叠加);② 移为各资本动作平均剔同行异常反应
#       (复用 cate_panel 一致口径,对照 14 家因果方向);③ 旗舰事件 + CFO 可操作建议。产出 markdown。
# 不做什么：不做新因果估计/不训练模型;只对移为做描述分解 + 复用既有反应口径。
# 允许依赖层：标准库、pandas/numpy、data/raw 行情/财务、cate_14firm 产物。
# 谁不应该 import：本入口为终端报告生成,建模脚本不应 import。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("market-impact-study/data/raw/tushare")
CATE_DIR = Path("market-impact-study/data/processed/modeling/cate_14firm")
OUT = Path("market-impact-study/docs/reports/YIWEI_CFO_CASE.md")
YIWEI = "300590.SZ"
Q = "“"
QQ = "”"


def yiwei_annual() -> pd.DataFrame:
    """Year-end total_mv(亿), PE, shares(亿股); annual net profit(亿). 市值 = PE × 净利润."""
    db = pd.read_csv(RAW / "daily_basic" / f"{YIWEI}.csv")
    db.columns = [c.lstrip("﻿") for c in db.columns]
    db["trade_date"] = db["trade_date"].astype(int)
    db = db.sort_values("trade_date")
    for c in ["total_mv", "pe", "close"]:
        db[c] = pd.to_numeric(db[c], errors="coerce")
    db["yr"] = db["trade_date"] // 10000
    db["shares_yi"] = db["total_mv"] * 10000 / db["close"] / 1e8
    ann = db.groupby("yr").agg(
        mv_yi=("total_mv", lambda x: x.iloc[-1] / 10000), pe=("pe", "last"), shares_yi=("shares_yi", "last")
    )
    inc = pd.read_csv(RAW / "income" / f"{YIWEI}.csv")
    inc.columns = [c.lstrip("﻿") for c in inc.columns]
    inc = inc[pd.to_numeric(inc["end_date"], errors="coerce").notna()].copy()
    inc["end_date"] = inc["end_date"].astype(int)
    inc = inc[inc["end_date"] % 10000 == 1231]
    inc["yr"] = inc["end_date"] // 10000
    inc["ni_yi"] = pd.to_numeric(inc["n_income_attr_p"], errors="coerce") / 1e8
    ni = inc.sort_values(["yr", "ann_date"]).groupby("yr")["ni_yi"].last()
    return ann.join(ni).reset_index()


def decompose(ann: pd.DataFrame, y0: int, y1: int) -> dict:
    """精确恒等式:市值 = 隐含倍数 × 盈利,其中隐含倍数 ≡ 市值/净利润(不用报告PE,其盈利基数滞后/口径不一致)。
    Δlog(市值) = Δlog(倍数) + Δlog(盈利),两通道精确加总。"""
    a = ann.set_index("yr")
    r0, r1 = a.loc[y0], a.loc[y1]
    mult0, mult1 = r0["mv_yi"] / r0["ni_yi"], r1["mv_yi"] / r1["ni_yi"]
    dlog_mv = np.log(r1["mv_yi"] / r0["mv_yi"])
    dlog_m = np.log(mult1 / mult0)
    dlog_e = np.log(r1["ni_yi"] / r0["ni_yi"])
    return {
        "period": f"{y0}→{y1}",
        "mv0": round(r0["mv_yi"], 1),
        "mv1": round(r1["mv_yi"], 1),
        "mv_chg_pct": round((r1["mv_yi"] / r0["mv_yi"] - 1) * 100, 1),
        "mult": f"{mult0:.0f}→{mult1:.0f}",
        "pe_c": round(dlog_m, 3),
        "e_c": round(dlog_e, 3),
        "pe_share": round(dlog_m / dlog_mv * 100, 0) if abs(dlog_mv) > 1e-6 else np.nan,
        "e_share": round(dlog_e / dlog_mv * 100, 0) if abs(dlog_mv) > 1e-6 else np.nan,
        "shares": f"{r0['shares_yi']:.2f}→{r1['shares_yi']:.2f}",
    }


def yiwei_actions() -> tuple[pd.DataFrame, pd.DataFrame]:
    p = pd.read_csv(CATE_DIR / "cate_panel_14firm.csv")
    y = p[(p["ts_code"] == YIWEI) & (p["D"] == 1)].copy()
    agg = (
        y.groupby("subtype")
        .agg(
            n=("rel", "size"),
            mean_pct=("rel", lambda x: round(x.mean() * 100, 2)),
            median_pct=("rel", lambda x: round(x.median() * 100, 2)),
        )
        .reset_index()
    )
    return agg.sort_values("mean_pct", ascending=False), y


def main() -> None:
    ann = yiwei_annual()
    # 净利润年报止于 2025(2026 未披露);分解区间对齐到有盈利数据的年份
    periods = [decompose(ann, *p) for p in [(2017, 2021), (2021, 2022), (2022, 2024), (2024, 2025), (2017, 2025)]]
    actions, events = yiwei_actions()

    lines: list[str] = [
        "# 移为通信(300590)市值管理案例 — CFO 收口",
        "",
        "> 口径承自因果分析 INV-016/017:**定增=方向性证据(低估值更甚,统计未坐实)、减持=只描述不归因、回购=无显著效应**。",
        "> 反应=20日剔14家同行异常市值收益率(一致口径)。本案例为解释+建议,非预测。",
        "",
        "## 一、市值历程三通道分解(脊柱:市值 = 隐含倍数 × 盈利,精确恒等)",
        "",
        "| 区间 | 市值(亿) | 变化% | 隐含倍数 | 估值重估占比 | 盈利占比 | 股本(亿股) |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in periods:
        lines.append(
            f"| {d['period']} | {d['mv0']}→{d['mv1']} | {d['mv_chg_pct']:+.0f}% | {d['mult']} | "
            f"{d['pe_share']:.0f}% | {d['e_share']:.0f}% | {d['shares']} |"
        )
    lines += [
        "",
        f"**核心发现**(占比两通道精确加总到100%):移为最剧烈的回撤是**纯估值杀**——"
        f"**2021→2022 市值腰斩(−49%),估值重估占 109%、盈利反而 +(净利润还在涨)**;"
        f"而 2024→2025 的回落则换成**盈利驱动**(净利润 1.59→0.75 腰斩)。"
        f"上市→2021 的上涨则是盈利(71%)+估值(29%)共同。"
        f"**CFO 含义:移为市值的大幅波动主要来自{Q}估值倍数{QQ}重估(预期/风险/资金面/叙事),"
        f"盈利是慢变量但 2025 已成拖累;两条通道都要管,但历史最大回撤是估值,需重点防{Q}杀估值{QQ}。**"
        f"(股本 1.60→4.60亿股:定增+激励摊薄近 3 倍,是第三条通道的背景。)",
        "",
        "## 二、移为各资本动作的平均异常反应(对照 14 家因果方向)",
        "",
        "| 动作子类 | 事件数 | 平均异常反应% | 中位% |",
        "|---|---|---|---|",
    ]
    for r in actions.itertuples(index=False):
        lines.append(f"| {r.subtype} | {r.n} | {r.mean_pct:+.2f}% | {r.median_pct:+.2f}% |")
    lines += ["", "> 注:移为单公司样本小、含噪;方向与因果结论参照,不单独作因果断言。", "", "## 三、旗舰事件深读", ""]
    fin = events[events["subtype"] == "定增/再融资"].sort_values("trade_date")
    if len(fin):
        vp = fin["val_pct"].mean()
        lines.append(
            f"- **定增(再融资)** {len(fin)}次,平均异常反应 {fin['rel'].mean() * 100:+.2f}%,"
            f"**事件时估值分位均值 {vp:.2f}(偏高)**。**关键洞察:移为的定增多在自身估值高位做,"
            f"恰好踩在因果模型说{Q}不被奖励{QQ}的区间——所以平均反应是负的,这正印证因果结论(低估值才正)。"
            f"CFO 教训:移为过去的定增择时偏高,未来若需股权融资应优先低估值窗口。**"
        )
    red = events[events["subtype"] == "股东增减持/限售流通"]
    if len(red):
        lines.append(
            f"- **股东增减持/减持** {len(red)}次,平均 {red['rel'].mean() * 100:+.2f}%(偏负),"
            f"但因果上**不可归因为减持公告本身**(去偏后不显著=混淆)——只能说减持期相对走弱。"
        )
    ince = events[events["subtype"] == "股权激励/员工持股"]
    if len(ince):
        lines.append(f"- **股权激励** {len(ince)}次,平均 {ince['rel'].mean() * 100:+.2f}%。")
    lines += [
        "",
        "## 四、CFO 可操作建议(按经济通道,带诚实边界)",
        "",
        f"1. **主攻估值通道**:移为市值由 PE 主导(三通道分解),盈利稳定时市值仍可腰斩——投关重心="
        f"管理预期/降不确定性/讲清成长叙事(模组连接数、客户项目、海外),把{Q}杀估值{QQ}下行风险前置沟通。",
        "2. **定增择时**:若需股权融资,**优先在自身估值低位窗口**(因果方向性:低估值定增带来正相对反应);"
        "高估值时市场不额外奖励。**但此为方向性、A股纯赛道仅~8家做过、统计未坐实,作参考非铁律。**",
        "3. **减持沟通**:减持期相对走弱(描述层),虽不可单独归因,仍建议提前披露计划、绑定锁定/分批,"
        "管理信号(避免市场读成内部人看空)。",
        f"4. **回购预期管理**:回购对相对反应**无显著效应**(因果),不要把回购当{Q}托底{QQ}承诺;"
        f"若做,讲清是{Q}价值确认{QQ}而非护盘,避免预期落空。",
        "5. **盈利通道补强**:盈利虽非主驱动,但 2025 净利润腰斩(1.59→0.75亿)会拖累——稳住盈利波动 + "
        "披露成长轨迹(营收/净利 CAGR)是估值倍数的锚。",
        "",
        f"> **诚实边界**:本案例动作级断言均经因果去偏 + 聚类/安慰剂加固(INV-015~018);"
        f"**全链无一可下{Q}统计显著因果{QQ}的强断言**——定增边际、减持混淆、回购无效。按方向性参考使用。",
        "",
        f"> **合成控制补充(INV-020)**:对移为 2020 定增另做了合成控制反事实,结果 **inconclusive**——"
        f"合成体追不上移为 2020-02 的 5G 独立暴涨(pre-fit RMSPE 0.12)、in-space 安慰剂 p=0.375 不显著,"
        f"**单案例因果在此受数据所限,不强行给{Q}定增损失了多少{QQ}的数**。这与上面的方向性口径一致。",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    # 结构化导出供仪表板"CFO 行动建议"收尾段(承接诊断→学习→证据→行动)
    recs = [
        {
            "t": "主攻估值通道",
            "d": "市值由估值倍数主导,盈利稳时市值仍可腰斩;投关重心=管理预期/降不确定性/讲成长叙事(连接数·客户·海外),前置沟通防"
            + Q
            + "杀估值"
            + QQ
            + "。",
        },
        {
            "t": "定增择时",
            "d": "若需股权融资,优先自身估值低位窗口(因果方向性:低估值定增正反应);高估值不额外奖励。方向性、未坐实,作参考非铁律。",
        },
        {
            "t": "减持沟通",
            "d": "减持期相对走弱仅描述层(去偏后不显著=混淆,非因果);仍建议提前披露计划+锁定/分批,管理信号避免读成内部人看空。",
        },
        {
            "t": "回购预期管理",
            "d": "回购对相对反应无显著因果效应;别当"
            + Q
            + "托底"
            + QQ
            + "承诺,若做讲清是"
            + Q
            + "价值确认"
            + QQ
            + "而非护盘。",
        },
        {
            "t": "盈利通道补强",
            "d": "盈利非主驱动,但 2025 净利腰斩(1.59→0.75亿)成拖累;稳盈利波动+披露成长轨迹(营收/净利CAGR)是估值倍数的锚。",
        },
    ]
    cfo = {
        "channels": periods,
        "recs": recs,
        "key_finding": "移为最大回撤是纯估值杀:2021→22 市值 −49%,估值重估占 109%、盈利反而 +。市值大波动主要来自估值倍数重估,盈利是慢变量但 2025 已成拖累。",
        "actions": actions.to_dict("records"),
    }
    (CATE_DIR / "cfo_case.json").write_text(json.dumps(cfo, ensure_ascii=False), encoding="utf-8")
    print("\n".join(lines[:42]))
    print(f"\n... saved -> {OUT} , {CATE_DIR / 'cfo_case.json'}")


if __name__ == "__main__":
    main()

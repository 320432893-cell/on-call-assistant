"""Cross-peer comparison: market-cap journey channels + 定增 timing — learn from effective peers (ADR-004)."""

# 职责：把移为的分析框架(市值=隐含倍数×盈利 三通道分解 + 定增择时)横向铺到 14 家 = INV-021,
#       回答 ADR-004 的"同行重点学他们做了什么有效":谁靠真成长(盈利通道)、谁靠估值泡沫;
#       谁的定增有成长动量撑(高估值也被奖励)、谁没有(=移为的教训)。产出 markdown。
# 不做什么：不做新因果估计;复用 cate_panel 一致反应口径 + 各家行情/财务做描述对比。
# 允许依赖层：标准库、pandas/numpy、peer_universe、data/raw、cate_14firm 产物。
# 谁不应该 import：建模/主流程脚本不应 import 本入口。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
CATE = Path("market-impact-study/data/processed/modeling/cate_14firm/cate_panel_14firm.csv")
OUT = Path("market-impact-study/docs/reports/PEER_COMPARISON.md")


def firm_row(code: str, name: str, panel: pd.DataFrame) -> dict:
    db = pd.read_csv(RAW / "daily_basic" / f"{code}.csv")
    db.columns = [c.lstrip("﻿") for c in db.columns]
    db["trade_date"] = db["trade_date"].astype(int)
    db = db.sort_values("trade_date")
    mv = pd.to_numeric(db["total_mv"], errors="coerce")
    mv0, mv1 = mv.iloc[0] / 1e4, mv.iloc[-1] / 1e4
    yrs = (db["trade_date"].iloc[-1] // 10000) - (db["trade_date"].iloc[0] // 10000)

    inc = pd.read_csv(RAW / "income" / f"{code}.csv")
    inc.columns = [c.lstrip("﻿") for c in inc.columns]
    inc = inc[pd.to_numeric(inc["end_date"], errors="coerce").notna()].copy()
    inc["end_date"] = inc["end_date"].astype(int)
    inc = inc[inc["end_date"] % 10000 == 1231].copy()
    inc["yr"] = inc["end_date"] // 10000
    inc["rev"] = pd.to_numeric(inc["revenue"], errors="coerce")
    inc["ni"] = pd.to_numeric(inc["n_income_attr_p"], errors="coerce")
    ann = inc.sort_values(["yr", "ann_date"]).groupby("yr").last()
    rev = ann["rev"].dropna()
    rev_cagr = ((rev.iloc[-1] / rev.iloc[0]) ** (1 / max(len(rev) - 1, 1)) - 1) * 100 if len(rev) >= 3 else np.nan

    # market-cap channel decomposition (only if endpoint net profit > 0)
    ni = ann["ni"]
    ni_pos = ni[ni > 0]
    e_share = m_share = np.nan
    has_loss = bool((ni < 0).any())
    if len(ni_pos) >= 2 and mv0 > 0 and mv1 > 0:
        # 用每家自身年末市值 vs 该年净利润算隐含倍数;取首末有正利润且有市值的年
        yrs_pos = [int(y) for y in ni_pos.index]
        y0, y1 = yrs_pos[0], yrs_pos[-1]
        mvy = db.assign(yr=db["trade_date"] // 10000).groupby("yr")["total_mv"].last() / 1e4
        if y0 in mvy.index and y1 in mvy.index:
            m0, m1 = mvy[y0] / ni_pos.iloc[0], mvy[y1] / ni_pos.iloc[-1]
            dmv = np.log(mvy[y1] / mvy[y0])
            if abs(dmv) > 1e-6:
                m_share = round(np.log(m1 / m0) / dmv * 100, 0)
                e_share = round(np.log(ni_pos.iloc[-1] / ni_pos.iloc[0]) / dmv * 100, 0)

    f = panel[(panel["ts_code"] == code) & (panel["subtype"] == "定增/再融资")]
    return {
        "code": code,
        "name": name,
        "mv": f"{mv0:.0f}→{mv1:.0f}",
        "mult": round(mv1 / mv0, 1) if mv0 > 0 else np.nan,
        "yrs": int(yrs),
        "rev_cagr": rev_cagr,
        "has_loss": has_loss,
        "e_share": e_share,
        "m_share": m_share,
        "fin_n": len(f),
        "fin_vp": round(float(f["val_pct"].mean()), 2) if len(f) and f["val_pct"].notna().any() else np.nan,
        "fin_rel": round(float(f["rel"].mean()) * 100, 1) if len(f) else np.nan,
    }


def fmt(x, suf=""):
    return "—" if (x is None or (isinstance(x, float) and np.isnan(x))) else f"{x}{suf}"


def main() -> None:
    companies = load_companies()
    panel = pd.read_csv(CATE)
    rows = [firm_row(c["ts_code"], c["name"], panel) for c in companies]
    df = pd.DataFrame(rows).sort_values("mult", ascending=False, na_position="last")

    L = [
        "# 同行横向对比 — 学谁做得有效(ADR-004 辅助主体分析)",
        "",
        "> 框架同移为案例:市值=隐含倍数×盈利(三通道);定增择时看估值分位。反应=20日剔同行异常(一致口径)。",
        "> ⚠️ 各家上市期不同、单公司样本小,**CAGR/反应跨家不完全可比**,定性参照。",
        "",
        "## 一、14 家市值历程 + 定增择时对比",
        "",
        "| 公司 | 上市市值→现(亿) | 市值倍数 | 年数 | 营收CAGR(真成长) | 定增n | 定增估值分位 | 定增原始反应% |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in df.itertuples(index=False):
        cagr = "—" if (isinstance(r.rev_cagr, float) and np.isnan(r.rev_cagr)) else f"{r.rev_cagr:.0f}%"
        L.append(
            f"| {r.name} | {r.mv} | {fmt(r.mult, 'x')} | {r.yrs} | {cagr} | "
            f"{r.fin_n} | {fmt(r.fin_vp)} | {fmt(r.fin_rel, '%')} |"
        )
    L += [
        "",
        "> 营收CAGR=上市以来营收复合增速,作真成长代理(比当期利润稳);市值=隐含倍数×盈利的精确通道分解见移为案例(横向因正负对冲+上市期错位太噪,不入此表)。",
    ]

    L += [
        "",
        "## 二、关键洞察:谁做得有效,移为该学什么",
        "",
        "1. **真成长赢家(盈利通道为主)= 移为的榜样**:广和通(12→183亿)、移远(56→228亿)、美格(14→123亿)"
        "市值数倍增长且营收高 CAGR——**靠真成长撑估值,可持续**。移为(33→68亿、2倍)处中游,盈利 2018–2024 停滞是瓶颈。",
        "2. **定增择时的反直觉,正是因果的价值**:广和通/移远在**高估值(0.66~0.69)定增却 +8~10%**,高新兴在"
        "**低估值(0.33)定增反而 −2.8%**——表面与因果结论(低估值才好)相反。**真相=混淆**:广和通/移远定增时"
        "带着真实成长动量,正反应来自动量不是定增;DML 控掉动量后才显低估值效应(INV-016)。",
        "3. **移为的教训(最有用)**:移为高估值(0.68)定增却 −1.3%——**它学广和通在高位定增,却没有广和通的成长动量去撑**。"
        "**结论:定增要被市场奖励,需要“低估值”或“有真成长故事”二者之一;移为两样都不占,所以被罚。**"
        "移为该补的不是定增技巧,而是**先把成长动量(盈利/营收 CAGR)做实**,再谈高位融资。",
        "4. **反面教材**:日海(53→31)、映翰通(70→31)、博实结(84→68)市值缩水——上市即高点/缺成长,警示移为防“上市光环退潮”。",
        "",
        "> **诚实边界**:本对比为描述性 + 复用既有因果口径;跨家 CAGR/反应受上市期与样本所限,作定性学习参照,"
        "不对单家下因果断言。因果级结论只有 14 家合并的方向性(INV-016~018)。",
    ]

    OUT.write_text("\n".join(L), encoding="utf-8")
    recs = json.loads(df.to_json(orient="records", force_ascii=False))  # NaN→null,numpy 安全
    (CATE.parent / "peer_comparison.json").write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    print("\n".join(L))
    print(f"\nsaved -> {OUT} , {CATE.parent / 'peer_comparison.json'}")


if __name__ == "__main__":
    main()

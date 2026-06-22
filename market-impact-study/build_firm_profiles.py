"""14-firm case library + generalizable patterns — each firm a sample, the pooled model the learned rule (ADR-004)."""

# 职责：把分析框架系统铺到全 14 家 = INV-022:① 顶层"可泛化规律"(跨家动作一致性 + 合并因果口径
#       INV-016/018 + 成长质量);② 逐家案例档案(市值历程/成长质量/动作画像/择时/一句教训)。
#       回应"其他家也都做一遍、就像模型"——每家是样本,规律是从样本学到的。
# 不做什么：不做新因果估计(单家样本不足);per-firm 为描述,泛化层引用既有因果结论。
# 允许依赖层：标准库、pandas/numpy、peer_universe、data/raw、cate_14firm 产物。
# 谁不应该 import：建模/主流程脚本不应 import 本入口。
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
CATE = Path("market-impact-study/data/processed/modeling/cate_14firm/cate_panel_14firm.csv")
OUT = Path("market-impact-study/docs/reports/FIRM_PROFILES.md")
SUBS = [
    "定增/再融资",
    "股份回购(首发)",
    "股东增减持/限售流通",
    "股权激励/员工持股",
    "分红/权益分派",
    "业绩预告",
    "业绩快报",
]


def firm_stats(code: str, name: str, panel: pd.DataFrame) -> dict:
    db = pd.read_csv(RAW / "daily_basic" / f"{code}.csv")
    db.columns = [c.lstrip("﻿") for c in db.columns]
    db["trade_date"] = db["trade_date"].astype(int)
    db = db.sort_values("trade_date")
    mv = pd.to_numeric(db["total_mv"], errors="coerce")
    mv0, mv1, mvmax = mv.iloc[0] / 1e4, mv.iloc[-1] / 1e4, mv.max() / 1e4
    list_yr = db["trade_date"].iloc[0] // 10000

    inc = pd.read_csv(RAW / "income" / f"{code}.csv")
    inc.columns = [c.lstrip("﻿") for c in inc.columns]
    inc = inc[pd.to_numeric(inc["end_date"], errors="coerce").notna()].copy()
    inc["end_date"] = inc["end_date"].astype(int)
    inc = inc[inc["end_date"] % 10000 == 1231]
    rev = pd.to_numeric(inc.sort_values("end_date")["revenue"], errors="coerce").dropna()
    rev_cagr = (
        ((rev.iloc[-1] / rev.iloc[0]) ** (1 / max(len(rev) - 1, 1)) - 1) * 100
        if len(rev) >= 3 and rev.iloc[0] > 0
        else np.nan
    )

    y = panel[(panel["ts_code"] == code) & (panel["D"] == 1)]
    react = {}
    for s in SUBS:
        f = y[y["subtype"] == s]
        react[s] = (
            (
                round(f["rel"].mean() * 100, 1),
                len(f),
                round(float(f["val_pct"].mean()), 2) if f["val_pct"].notna().any() else None,
            )
            if len(f)
            else (None, 0, None)
        )

    if np.isnan(rev_cagr):
        grade = "数据不足"
    elif rev_cagr >= 20 and mv1 / mv0 >= 3:
        grade = "真成长型"
    elif rev_cagr < 8 or mv1 / mv0 < 1.2:
        grade = "停滞/缩水型"
    else:
        grade = "成长中游"
    return {
        "code": code,
        "name": name,
        "list_yr": int(list_yr),
        "mv0": mv0,
        "mv1": mv1,
        "mvmax": mvmax,
        "mult": mv1 / mv0 if mv0 > 0 else np.nan,
        "rev_cagr": rev_cagr,
        "grade": grade,
        "react": react,
    }


def lesson(s: dict) -> str:
    fin = s["react"]["定增/再融资"]
    parts = []
    if s["grade"] == "真成长型":
        parts.append(f"靠真成长(营收CAGR {s['rev_cagr']:.0f}%)撑市值={s['mult']:.1f}倍,是榜样")
    elif s["grade"] == "停滞/缩水型":
        parts.append(f"成长停滞(CAGR {s['rev_cagr']:.0f}%)、市值 {s['mult']:.1f}倍,需先做实成长")
    else:
        parts.append(f"成长中游(CAGR {s['rev_cagr']:.0f}%)")
    if s["mvmax"] / s["mv1"] > 1.6:
        parts.append(f"曾冲高 {s['mvmax']:.0f}亿、现 {s['mv1']:.0f}亿(防估值退潮)")
    if fin[1] >= 2 and fin[2] is not None:
        tag = "高位" if fin[2] > 0.6 else "低位" if fin[2] < 0.4 else "中位"
        parts.append(f"定增多在{tag}估值({fin[2]})、原始反应{fin[0]:+.1f}%")
    return ";".join(parts) + "。"


def main() -> None:
    companies = load_companies()
    panel = pd.read_csv(CATE)
    stats = [firm_stats(c["ts_code"], c["name"], panel) for c in companies]
    stats.sort(key=lambda s: -s["mult"] if not np.isnan(s["mult"]) else 0)

    # cross-firm action consistency
    cons = []
    for s in SUBS:
        vals = [st["react"][s][0] for st in stats if st["react"][s][1] >= 2 and st["react"][s][0] is not None]
        arr = np.array(vals, dtype=float)
        cons.append((s, len(arr), int((arr > 0).sum()), int((arr < 0).sum()), round(float(np.median(arr)), 1)))

    L = [
        "# 14 家资本运作案例库 + 可泛化规律",
        "",
        "> 把移为的分析框架系统铺到每一家:每家是一个样本,顶层是从 14 个样本学到的规律(就像模型)。",
        "> 反应=20日剔同行异常(一致口径)。**逐家为描述统计、含混淆;因果级结论只在合并的 14 家(INV-016~018)。**",
        "",
        "## 一、从 14 家学到的可泛化规律(模型层)",
        "",
        "**A. 跨家动作方向一致性**(每家先算自身均值,再看多少家同向;仅 n≥2 的家):",
        "",
        "| 动作 | 有效家数 | 正 | 负 | 跨家中位反应% | 普适解读 |",
        "|---|---|---|---|---|---|",
    ]
    readt = {
        "股份回购(首发)": "**普适 null**(正负各半)=回购无估值择时信号,印证因果",
        "股东增减持/限售流通": "**多数负**=减持期普遍相对走弱(但因果证为混淆,非公告本身)",
        "股权激励/员工持股": "**普遍温和正**=绑定团队,市场偏好",
        "定增/再融资": "**条件性**(正负混)=要低估值或有成长动量才正(因果 INV-016)",
        "分红/权益分派": "近 null=分红本身非市值驱动",
        "业绩预告": "**多数负**=预告以预警/低于预期居多",
        "业绩快报": "略正=快报兑现确定性",
    }
    for s, n, pos, neg, med in cons:
        L.append(f"| {s} | {n} | {pos} | {neg} | {med:+.1f}% | {readt.get(s, '')} |")
    L += [
        "",
        "**B. 合并因果模型(从全 14 家学到、已去偏+加固)**:定增=方向性(低估值/有成长更甚,聚类后边际 INV-017);"
        "减持=去偏后不显著(裸负是混淆);回购=无显著效应。策略树规则(INV-018):**自身估值底部~20% 才建议定增**。",
        "**C. 成长质量是市值的根**:真成长型(营收CAGR≥20%+市值≥3倍)= 广和通/移远/美格,可持续;"
        "停滞/缩水型靠估值泡沫,易 round-trip。**这是跨家最稳的规律:盈利成长 > 资本运作技巧。**",
        "",
        "## 二、逐家案例档案(14)",
        "",
    ]
    for s in stats:
        L.append(f"### {s['name']}（{s['code'].split('.')[0]}，{s['list_yr']}上市，{s['grade']}）")
        best = max((k for k in SUBS if s["react"][k][1] >= 2), key=lambda k: s["react"][k][0] or -99, default=None)
        worst = min((k for k in SUBS if s["react"][k][1] >= 2), key=lambda k: s["react"][k][0] or 99, default=None)
        line = (
            f"- 市值 {s['mv0']:.0f}→{s['mv1']:.0f}亿（{s['mult']:.1f}倍"
            + (f"，峰值 {s['mvmax']:.0f}" if s["mvmax"] / max(s["mv1"], 1) > 1.4 else "")
            + "）"
        )
        cagr_str = "—" if np.isnan(s["rev_cagr"]) else f"{s['rev_cagr']:.0f}%"
        line += f"，营收CAGR {cagr_str}。"
        if best:
            line += f" 最受捧动作:{best.split('/')[0]}({s['react'][best][0]:+.1f}%);最受罚:{worst.split('/')[0]}({s['react'][worst][0]:+.1f}%)。"
        L.append(line)
        L.append(f"- **教训**:{lesson(s)}")
    L += [
        "",
        "## 三、元教训(给移为 + 给同赛道 CFO)",
        "",
        "1. **成长是 1,资本运作是 0**:14 家最稳的分野是营收成长——真成长者(广和通/移远/美格)市值数倍且可持续,"
        "停滞者(金溢/利尔达/日海)靠估值泡沫终回吐。**任何资本动作都救不了成长停滞。**",
        "2. **回购别当托底**:跨家普适 null,回购无估值择时信号;承诺回购护盘=透支信用。",
        "3. **定增要资格**:低估值或有成长动量二选一才被奖励;无成长的高位定增(移为式)被罚。",
        "4. **减持重沟通**:普遍伴随相对走弱(虽混淆),提前披露/分批/绑定可降信号伤害。",
        "5. **预告管理预期**:业绩预告多数负反应=市场对预警敏感,正面预增也要讲清持续性。",
        "",
        "> 诚实边界:逐家描述含混淆、跨家受上市期/小样本所限;只有合并因果(INV-016~018)是去偏结论。本库作系统学习参照。",
    ]
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"firms={len(stats)}  saved -> {OUT}")
    print("\n".join(L[:34]))


if __name__ == "__main__":
    main()

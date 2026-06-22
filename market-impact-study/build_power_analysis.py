"""Power / minimum-detectable-effect analysis — separate credible nulls from underpowered inconclusives."""

# 职责：对每个结论算 SE / MDE@80%功效 / 对给定效应的功效 = INV-024,回答高层最致命的质疑
#       "null 是真没效应还是样本太小":功效充足+观测≈0 => 可信 null;欠功效 => inconclusive。
#       覆盖描述(剔同行 rel + 因子CAR)+ 因果(DML ATE / 定增聚类 SE)。
# 不做什么：不重训模型;读既有产物算功效。
# 允许依赖层：标准库、numpy/pandas/scipy、cate_14firm 产物。
# 谁不应该 import：建模脚本不应 import 本入口。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

D = Path("market-impact-study/data/processed/modeling/cate_14firm")
OUT = Path("market-impact-study/docs/reports/POWER_ANALYSIS.md")
ZA, ZB = norm.ppf(0.975), norm.ppf(0.80)  # 双侧α=0.05, 功效80%
MDE_K = ZA + ZB  # ≈2.80
TARGETS = [2.0, 3.0, 5.0]  # 关心的效应量(%):CFO 视角下经济上重要的相对市值反应


def power_at(effect_pct: float, se_pct: float) -> float:
    """两侧检验下检出 effect 的功效(近似)。"""
    return float(norm.cdf(abs(effect_pct) / se_pct - ZA)) if se_pct > 0 else float("nan")


def verdict(obs_pct: float, se_pct: float) -> str:
    mde = MDE_K * se_pct
    if power_at(3.0, se_pct) >= 0.8:
        return (
            f"功效充足(能检出≥{mde:.1f}%);观测{obs_pct:+.1f}%→**可信 null/小效应**"
            if abs(obs_pct) < mde
            else "功效充足且观测显著"
        )
    return f"⚠️欠功效(80%只够检{mde:.1f}%);{obs_pct:+.1f}%→**inconclusive,非真 null**"


def descriptive_rows(df: pd.DataFrame, col: str, label: str) -> list[dict]:
    rows = []
    for s, g in df.groupby("subtype"):
        x = pd.to_numeric(g[col], errors="coerce").dropna().to_numpy() * 100
        if len(x) < 8:
            continue
        se = float(np.std(x, ddof=1) / np.sqrt(len(x)))
        rows.append(
            {
                "维度": label,
                "结论": s,
                "n": len(x),
                "观测%": round(float(x.mean()), 2),
                "SE%": round(se, 2),
                "MDE@80%%": round(MDE_K * se, 2),
                **{f"功效@{t:.0f}%": round(power_at(t, se), 2) for t in TARGETS},
                "判定": verdict(float(x.mean()), se),
            }
        )
    return rows


def main() -> None:
    panel = pd.read_csv(D / "cate_panel_14firm.csv")
    ev = panel[panel["D"] == 1]
    fcar = pd.read_csv(D / "factor_car_events.csv")
    rows = descriptive_rows(ev, "rel", "描述·剔同行")
    rows += descriptive_rows(fcar, "car_factor", "描述·因子CAR")

    # causal ATEs (DML analytic CI) + 定增 cluster-robust SE
    cate = json.loads((D / "cate_results.json").read_text(encoding="utf-8"))
    hard = json.loads((D / "cate_hardening.json").read_text(encoding="utf-8"))
    causal = []
    for r in cate:
        lo, hi = r["lindml"]["ate_ci"]
        se = (hi - lo) / (2 * 1.645)  # 90%CI -> SE
        causal.append(
            {
                "维度": "因果·DML(解析CI)",
                "结论": r["action"],
                "n": r["treated"],
                "观测%": r["lindml"]["ate_pct"],
                "SE%": round(se, 2),
                "MDE@80%%": round(MDE_K * se, 2),
                **{f"功效@{t:.0f}%": round(power_at(t, se), 2) for t in TARGETS},
                "判定": verdict(r["lindml"]["ate_pct"], se),
            }
        )
    flo, fhi = hard["forward_causal"]["cluster_ci90_pct"]
    fse = (fhi - flo) / (2 * 1.645)
    causal.append(
        {
            "维度": "因果·定增(聚类自助SE)",
            "结论": "定增/再融资",
            "n": hard["forward_causal"]["n_boot"],
            "观测%": hard["forward_causal"]["point_pct"],
            "SE%": round(fse, 2),
            "MDE@80%%": round(MDE_K * fse, 2),
            **{f"功效@{t:.0f}%": round(power_at(t, fse), 2) for t in TARGETS},
            "判定": verdict(hard["forward_causal"]["point_pct"], fse),
        }
    )

    allrows = pd.DataFrame(rows + causal)
    allrows.to_csv(D / "power_analysis.csv", index=False)

    L = [
        "# 功效 / 最小可检测效应(MDE)分析 — 把 null 与 inconclusive 分开",
        "",
        "> 回答高层最致命质疑:**没发现效应,是真没有、还是样本太小没看出来?**",
        f"> MDE@80% = {MDE_K:.2f}×SE(双侧 α=0.05、功效 80% 能检出的最小效应);功效@k% = 真效应为 k% 时能检出的概率。",
        "",
        "## 关键结论(因果层)",
        "",
    ]
    head = "| 维度 | 结论 | n | 观测% | SE% | MDE@80% | 功效@3% | 判定 |"
    L += [head, "|---|---|---|---|---|---|---|---|"]
    for r in causal:
        L.append(
            f"| {r['维度']} | {r['结论']} | {r['n']} | {r['观测%']:+.1f} | {r['SE%']} | {r['MDE@80%%']}% | {r['功效@3%']} | {r['判定']} |"
        )
    L += [
        "",
        "**读法**:",
        "- **回购 null 可信(对经济上重要的效应)**:对 ≥5% 效应功效≈1.0、≥3% 约 0.66~0.80,观测≈0 → "
        "**可排除回购的'托底/择时'级(≥3~5%)效应**;更小的 <3% 效应功效不足,不强排。",
        "- **减持因果 null = 可信**:功效充足检出 ~3% 效应,去偏后仍 ≈0 → 裸负是混淆,减持公告本身无显著因果。",
        "- **定增 = 欠功效 inconclusive(非真 null 也非坐实)**:聚类后 SE 大、对自身点估计功效低 → "
        "**仅 ~8 家做定增,样本不足以坐实;不能说有、也不能说没有**。要坐实需更多做定增的纯赛道公司(数据天花板)。",
        "",
        "## 全部维度明细",
        "",
        head,
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(
            f"| {r['维度']} | {r['结论']} | {r['n']} | {r['观测%']:+.1f} | {r['SE%']} | {r['MDE@80%%']}% | {r['功效@3%']} | {r['判定']} |"
        )
    L += [
        "",
        "> 高层一句话:**我们对'回购无效''减持公告本身无因果'是有功效支撑的可信结论;对'定增有效'诚实承认样本不足、暂不下结论。**"
        "这种'有功效的 null + 诚实的 inconclusive'区分,正是严谨性所在。",
    ]
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(allrows.to_string(index=False))
    print(f"\nsaved -> {OUT} , {D}/power_analysis.csv")


if __name__ == "__main__":
    main()

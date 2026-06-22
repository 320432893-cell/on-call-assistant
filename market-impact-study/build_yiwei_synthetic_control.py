"""Synthetic control for 移为(300590) 2020 定增预案 — honest single-case counterfactual (ADR-004 ③)."""

# 职责：对移为 2020-05-22 定增预案做合成控制 = INV-020:13家同行加权造反事实移为,缺口=真实−合成,
#       in-space 安慰剂做推断。诚实落"是否可信(pre-fit)+ 是否显著(placebo)",不为出结果而调参。
# 不做什么：不做新 DML/不训练模型;只对单事件做 SCM。
# 允许依赖层：标准库、numpy/pandas/scipy、peer_universe、data/raw 行情。
# 谁不应该 import：建模/主流程脚本不应 import 本入口。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from peer_universe import load_companies
from scipy.optimize import minimize

RAW = Path("market-impact-study/data/raw/tushare/daily_basic")
OUT = Path("market-impact-study/data/processed/modeling/cate_14firm/yiwei_synthetic_control.json")
TREATED = "300590.SZ"
EVENT = 20200522  # 非公开发行A股股票预案
PRE, POST = 190, 240  # 交易日;PRE 缩到纳入移远(2019-07上市,最可比)


def load_series() -> dict[str, pd.Series]:
    out = {}
    for c in [x["ts_code"] for x in load_companies()]:
        path = RAW / f"{c}.csv"
        if not path.exists():
            continue
        d = pd.read_csv(path)
        d.columns = [x.lstrip("﻿") for x in d.columns]
        d["trade_date"] = d["trade_date"].astype(int)
        out[c] = d.sort_values("trade_date").set_index("trade_date")["total_mv"].astype(float)
    return out


def fit_weights(target_pre: np.ndarray, donor_pre: np.ndarray) -> np.ndarray:
    j = donor_pre.shape[0]
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    res = minimize(
        lambda w: float(np.sum((target_pre - w @ donor_pre) ** 2)),
        np.full(j, 1 / j),
        method="SLSQP",
        bounds=[(0, 1)] * j,
        constraints=cons,
        options={"maxiter": 500, "ftol": 1e-10},
    )
    return res.x


def rmspe(g: np.ndarray, mask: np.ndarray) -> float:
    return float(np.sqrt(np.mean(g[mask] ** 2)))


def main() -> None:
    series = load_series()
    names = {x["ts_code"]: x["name"] for x in load_companies()}
    ax = series[TREATED].index.to_numpy()
    pos = int(np.searchsorted(ax, EVENT))
    win = ax[max(0, pos - PRE) : pos + POST]
    t0 = win[0]
    pre_mask = win < EVENT

    def index_on(c: str) -> np.ndarray | None:
        s = series[c].reindex(win)
        if s.isna().any() or s.loc[t0] <= 0:
            return None
        return (s / s.loc[t0]).to_numpy()

    ytr = index_on(TREATED)
    donors = {c: v for c in series if c != TREATED and (v := index_on(c)) is not None}
    codes_d = list(donors)
    big_d = np.array([donors[c] for c in codes_d])

    w = fit_weights(ytr[pre_mask], big_d[:, pre_mask])
    synth = w @ big_d
    gap = ytr - synth
    pre_r, post_r = rmspe(gap, pre_mask), rmspe(gap, ~pre_mask)

    ratios = {TREATED: post_r / pre_r if pre_r > 1e-9 else np.inf}
    placebo_gaps = []
    for i, c in enumerate(codes_d):
        others = np.delete(big_d, i, axis=0)
        wp = fit_weights(big_d[i][pre_mask], others[:, pre_mask])
        gp = big_d[i] - wp @ others
        placebo_gaps.append([round(float(v) * 100, 2) for v in gp])
        pr = rmspe(gp, pre_mask)
        if pr > 1e-6:
            ratios[c] = rmspe(gp, ~pre_mask) / pr
    rank = sorted(ratios.values(), reverse=True)
    placebo_p = (rank.index(ratios[TREATED]) + 1) / len(rank)

    npre = int(pre_mask.sum())
    gaps = {
        f"gap_+{h}d_pct": round(float(gap[npre + h - 1]) * 100, 1)
        for h in (20, 60, 120, 240)
        if npre + h - 1 < len(gap)
    }
    credible = pre_r < 0.06  # SCM 经验阈:pre-fit RMSPE 太大则合成体不可信
    verdict = "inconclusive:pre-fit差+placebo不显著" if (not credible or placebo_p > 0.1) else "可信且显著"
    result = {
        "event": EVENT,
        "pre": int(pre_mask.sum()),
        "post": int((~pre_mask).sum()),
        "donors": [names[c] for c in codes_d],
        "weights": {names[c]: round(float(wi), 3) for c, wi in zip(codes_d, w, strict=False) if wi > 0.02},
        "pre_fit_rmspe": round(pre_r, 4),
        "post_rmspe": round(post_r, 4),
        "gaps": gaps,
        "placebo_p": round(placebo_p, 3),
        "credible_prefit": credible,
        "verdict": verdict,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # 路径导出供仪表板"合成控制过程"图:真实 vs 合成逐日轨迹 + 安慰剂云
    xrel = list(range(-npre, len(win) - npre))
    path = {
        "event": EVENT,
        "x_rel_days": xrel,
        "treated_index": [round(float(v), 3) for v in ytr],
        "synth_index": [round(float(v), 3) for v in synth],
        "gap_pct": [round(float(v) * 100, 2) for v in gap],
        "placebo_gaps_pct": placebo_gaps,
        "pre_fit_rmspe": round(pre_r, 4),
        "placebo_p": round(placebo_p, 3),
    }
    (OUT.parent / "sc_path.json").write_text(json.dumps(path, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "\n诚实判读:pre-fit RMSPE",
        result["pre_fit_rmspe"],
        "(>0.06=合成体追不上移为2020 5G暴涨,缺口不可信);placebo p",
        result["placebo_p"],
        "(>0.1=移为偏离不比安慰剂极端)→",
        verdict,
    )


if __name__ == "__main__":
    main()

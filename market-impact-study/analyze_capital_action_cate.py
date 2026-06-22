# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Estimate heterogeneous causal effects of capital actions via Double ML + Causal Forest."""

# 职责：对每个资本动作 k(vs 无动作对照),用 DML(LinearDML)+ 因果森林(CausalForestDML)估
#       异质处理效应 CATE(效应如何随公司内估值/规模/成长变化),配因果刹车(overlap/置换安慰剂/E-value)。
#       这是 ADR-004 ② 的兑现 = INV-016;取代 INV-015 纯描述统计对"动作有效性"的因果级解读。
# 不做什么：不训练预测模型/不建特征宽表;基准沿用 calculate_event_car 口径(剔自身 universe 均值)。
# 运行环境：需隔离 venv `.venv-causal`(econml 0.16 + sklearn<1.7,与主 .venv 的 sklearn 1.8 隔离,
#           见 requirements-causal.txt);用 `.venv-causal/bin/python market-impact-study/analyze_capital_action_cate.py` 从仓库根运行。
# 允许依赖层：标准库、numpy/pandas、lightgbm、econml、sklearn、peer_universe(口径/基准)、data/raw 行情、data/processed 9 家公告分类宽表。
# 谁不应该 import：建模/特征/主流程脚本不应 import 本入口(它依赖隔离 venv);它们读本脚本产物。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from econml.dml import CausalForestDML, LinearDML
from lightgbm import LGBMClassifier, LGBMRegressor
from peer_universe import load_companies
from sklearn.linear_model import LogisticRegression

RAW = Path("market-impact-study/data/raw/tushare")
PROCESSED = Path("market-impact-study/data/processed")
V3_WIDE = PROCESSED / "modeling" / "modeling_dataset_enhanced_v3.csv"
FUND_PANEL = PROCESSED / "modeling" / "fundamental_panel.csv"
OUT_DIR = PROCESSED / "modeling" / "cate_14firm"

RNG = 0
HORIZON = 20
REPO_INIT = ("预案", "股东大会", "提议", "方案", "报告书")
# PIT 基本面特征(build_fundamental_panel.py 产),merge_asof 接进任意 firm-day
FUND_COLS = [
    "f_roe",
    "f_roa",
    "f_gross_margin",
    "f_net_margin",
    "f_op_margin",
    "f_rd_intensity",
    "f_ocf_to_rev",
    "f_ocf_to_assets",
    "f_fcf_to_rev",
    "f_cash_to_assets",
    "f_debt_to_assets",
    "f_current_ratio",
    "f_equity_mult",
    "f_asset_turn",
    "f_bps",
    "f_rev_yoy",
    "f_ni_yoy",
    "f_rev_cagr2",
    "f_rev_cagr3",
    "f_rev_growth",
]
# 混淆控制 W = 价格技术 + 基本面(盈利/质量/杠杆/效率/成长);把"早算好却没接进因果"的基本面正式喂进去
TECH = ["log_mv", "mom20", "mom60", "vol20", "turn20"]
FUND_W = [
    "f_roe",
    "f_roa",
    "f_gross_margin",
    "f_net_margin",
    "f_op_margin",
    "f_debt_to_assets",
    "f_current_ratio",
    "f_equity_mult",
    "f_asset_turn",
    "f_rd_intensity",
    "f_ocf_to_rev",
    "f_fcf_to_rev",
    "f_cash_to_assets",
    "f_ni_yoy",
]
WCOLS = [*TECH, *FUND_W, "rev_cagr2", "rev_cagr3"]
# 因果森林效应修饰 X = 六维(看动作效果在什么条件下不同),配中文名供 var_importance
XCF_COLS = ["val_pct", "log_mv", "f_roe", "f_debt_to_assets", "f_rd_intensity", "rev_cagr3"]
XCF_NAMES = ["估值分位", "规模", "ROE", "杠杆", "研发强度", "成长"]
HEADLINE_ACTIONS = ["定增/再融资", "股东增减持/限售流通", "股份回购(首发)"]
STRUCTURED = [
    ("repurchase", "股份回购(首发)", REPO_INIT),
    ("dividend", "分红/权益分派", None),
    ("forecast", "业绩预告", None),
    ("express", "业绩快报", None),
]
ANNOUNCEMENT_ONLY = ["定增/再融资", "股东增减持/限售流通", "股权激励/员工持股"]


def annual_revenue(code: str) -> pd.DataFrame | None:
    path = RAW / "income" / f"{code}.csv"
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    frame.columns = [c.lstrip("﻿") for c in frame.columns]
    frame = frame[pd.to_numeric(frame["end_date"], errors="coerce").notna()].copy()
    frame["end_date"] = frame["end_date"].astype(int)
    frame["ann_date"] = pd.to_numeric(frame["ann_date"], errors="coerce")
    frame = frame[(frame["end_date"] % 10000 == 1231)].dropna(subset=["ann_date"])
    frame["fy"] = frame["end_date"] // 10000
    frame["revenue"] = pd.to_numeric(frame["revenue"], errors="coerce")
    frame = frame.sort_values(["fy", "ann_date"]).groupby("fy").last().reset_index()
    return frame[["fy", "ann_date", "revenue"]]


def cagr_asof(series: pd.DataFrame | None, ann_date: int) -> tuple[float, float]:
    if series is None:
        return (np.nan, np.nan)
    avail = series[series["ann_date"] <= ann_date]
    rev = avail["revenue"].to_numpy()
    if len(rev) < 3:
        return (np.nan, np.nan)
    r0 = rev[-1]

    def cagr(r_then: float, years: int) -> float:
        if np.isnan(r_then) or r_then <= 0 or r0 <= 0:
            return np.nan
        return (r0 / r_then) ** (1 / years) - 1

    c2 = cagr(rev[-3], 2)
    c3 = cagr(rev[-4], 3) if len(rev) >= 4 else np.nan
    return (c2, c3)


def build_firmday_panels(codes: list[str]) -> dict[str, pd.DataFrame]:
    panels: dict[str, pd.DataFrame] = {}
    for code in codes:
        path = RAW / "daily_basic" / f"{code}.csv"
        if not path.exists():
            continue
        d = pd.read_csv(path)
        d.columns = [c.lstrip("﻿") for c in d.columns]
        d = d[["trade_date", "total_mv", "pe", "pb", "ps", "turnover_rate"]].copy()
        d["trade_date"] = d["trade_date"].astype(int)
        d = d.sort_values("trade_date").reset_index(drop=True)
        for col in ["total_mv", "pe", "pb", "ps", "turnover_rate"]:
            d[col] = pd.to_numeric(d[col], errors="coerce")
        n = len(d)
        mv = d["total_mv"].to_numpy()
        pre = np.array([mv[max(0, i - 1)] for i in range(n)])
        end = np.array([mv[min(n - 1, i + HORIZON)] for i in range(n)])
        with np.errstate(invalid="ignore", divide="ignore"):
            d["mv_ret20"] = np.where((pre > 0) & ~np.isnan(end), end / pre - 1, np.nan)
            d["dret"] = mv / np.concatenate([[np.nan], mv[:-1]]) - 1
            d["mom20"] = mv / np.concatenate([[np.nan] * 20, mv[:-20]]) - 1 if n > 20 else np.nan
            d["mom60"] = mv / np.concatenate([[np.nan] * 60, mv[:-60]]) - 1 if n > 60 else np.nan
        # 以下 shift(1) 均为"用前一日值"的滞后特征(防泄漏,非未来泄漏),PIT 安全,豁免时序负移规则
        d["vol20"] = d["dret"].rolling(20).std().shift(1)  # nosemgrep: timeseries-negative-shift-with-modeling-call
        turn_ma = d["turnover_rate"].rolling(20).mean()
        d["turn20"] = turn_ma.shift(1)  # nosemgrep: timeseries-negative-shift-with-modeling-call
        d["log_mv"] = np.log(d["total_mv"].clip(lower=1))
        d["pe_pre"] = d["pe"].shift(1)  # nosemgrep: timeseries-negative-shift-with-modeling-call
        d["pb_pre"] = d["pb"].shift(1)  # nosemgrep: timeseries-negative-shift-with-modeling-call
        d["ps_pre"] = d["ps"].shift(1)  # nosemgrep: timeseries-negative-shift-with-modeling-call
        panels[code] = d
    return panels


def peer_relative(panels: dict[str, pd.DataFrame]) -> dict[tuple[str, int], float]:
    long = pd.concat(
        [p[["trade_date", "mv_ret20"]].assign(ts_code=c) for c, p in panels.items()], ignore_index=True
    ).dropna(subset=["mv_ret20"])
    grp = long.groupby("trade_date")["mv_ret20"]
    long["tot"] = grp.transform("sum")
    long["cnt"] = grp.transform("count")
    long = long[long["cnt"] >= 2].copy()
    long["rel"] = long["mv_ret20"] - (long["tot"] - long["mv_ret20"]) / (long["cnt"] - 1)
    return {(r.ts_code, int(r.trade_date)): float(r.rel) for r in long.itertuples(index=False)}


def action_dates(codes: set[str]) -> dict[str, dict[str, list[int]]]:
    out: dict[str, dict[str, list[int]]] = {}
    for folder, subtype, init in STRUCTURED:
        dd: dict[str, list[int]] = {}
        for path in (RAW / folder).glob("*.csv"):
            code = path.stem
            if code not in codes or path.stat().st_size == 0:
                continue
            d = pd.read_csv(path)
            d.columns = [c.lstrip("﻿") for c in d.columns]
            if "ann_date" not in d.columns or len(d) == 0:
                continue
            d["ann_date"] = pd.to_numeric(d["ann_date"], errors="coerce")
            d = d.dropna(subset=["ann_date"])
            if init and "proc" in d.columns:
                d = d[d["proc"].astype(str).apply(lambda p, keys=init: any(k in p for k in keys))]
            dd.setdefault(code, []).extend(d["ann_date"].astype(int).tolist())
        out[subtype] = dd
    wide = pd.read_csv(V3_WIDE, low_memory=False)
    datecol = next(c for c in ("event_date", "trade_date", "anchor_date") if c in wide.columns)
    for subtype in ANNOUNCEMENT_ONLY:
        sub = wide[wide["capital_action_subtype"] == subtype].copy()
        sub["ad"] = pd.to_datetime(sub[datecol], errors="coerce").dt.strftime("%Y%m%d")
        sub = sub.dropna(subset=["ad"])
        dd = {}
        for row in sub.itertuples(index=False):
            dd.setdefault(row.ts_code, []).append(int(row.ad))
        out[subtype] = dd
    return out


def build_panel() -> pd.DataFrame:
    companies = load_companies()
    codes = [c["ts_code"] for c in companies]
    names = {c["ts_code"]: c["name"] for c in companies}
    panels = build_firmday_panels(codes)
    rel = peer_relative(panels)
    revenue = {c: annual_revenue(c) for c in codes}

    def _base(col: str) -> dict[str, np.ndarray]:
        return {c: np.sort(p.loc[p[col] > 0, col].to_numpy()) for c, p in panels.items()}

    bases = {"pe_pre": _base("pe_pre"), "pb_pre": _base("pb_pre"), "ps_pre": _base("ps_pre")}

    def _pct(base: np.ndarray | None, v: float) -> float:
        if base is None or len(base) < 20 or pd.isna(v) or v <= 0:
            return np.nan
        return float(np.searchsorted(base, v, side="right") / len(base))

    def valpct(code: str, row: pd.Series) -> float:
        # 估值分位:PE 优先,PE 无效(早期/未算)依次用 PB、PS 兜底,各在该公司自身历史内取分位
        for col in ("pe_pre", "pb_pre", "ps_pre"):
            p = _pct(bases[col].get(code), row[col])
            if not pd.isna(p):
                return p
        return np.nan

    def to_td(code: str, ann: int) -> int | None:
        arr = panels[code]["trade_date"].to_numpy() if code in panels else None
        if arr is None:
            return None
        i = int(np.searchsorted(arr, ann, side="left"))
        return int(arr[i]) if i < len(arr) else None

    def covrow(code: str, td: int) -> dict | None:
        p = panels[code]
        row = p[p["trade_date"] == td]
        reaction = rel.get((code, td))
        if len(row) == 0 or reaction is None or pd.isna(reaction):
            return None
        row = row.iloc[0]
        c2, c3 = cagr_asof(revenue.get(code), td)
        return {
            "ts_code": code,
            "firm": names[code],
            "trade_date": td,
            "rel": reaction,
            "val_pct": valpct(code, row),
            "log_mv": row["log_mv"],
            "mom20": row["mom20"],
            "mom60": row["mom60"],
            "vol20": row["vol20"],
            "turn20": row["turn20"],
            "rev_cagr2": c2,
            "rev_cagr3": c3,
        }

    acts = action_dates(set(codes))
    all_dates = {c: set() for c in codes}
    for dd in acts.values():
        for code, ds in dd.items():
            all_dates.setdefault(code, set()).update(ds)

    rows: list[dict] = []
    for subtype, dd in acts.items():
        for code, ds in dd.items():
            for ann in set(ds):
                td = to_td(code, ann)
                if td is None:
                    continue
                row = covrow(code, td)
                if row:
                    row.update({"subtype": subtype, "D": 1})
                    rows.append(dict(row))
    for code in codes:
        if code not in panels:
            continue
        acts_arr = np.array(sorted(all_dates.get(code, set())))
        eligible = []
        for td in panels[code]["trade_date"].to_numpy():
            if len(acts_arr) > 0:
                near = acts_arr[(acts_arr >= td - 400) & (acts_arr <= td + 400)]
                if len(near) > 0 and np.min(np.abs(near.astype(int) - int(td))) <= 25:
                    continue
            eligible.append(int(td))
        for j, td in enumerate(eligible):
            if j % 12 != 0:
                continue
            row = covrow(code, td)
            if row:
                row.update({"subtype": "control", "D": 0})
                rows.append(dict(row))
    return attach_fundamentals(pd.DataFrame(rows))


def attach_fundamentals(df: pd.DataFrame) -> pd.DataFrame:
    # PIT 接入:按公司 merge_asof,取事件日(trade_date)前最近一期已披露(ann_date)的基本面
    if not FUND_PANEL.exists():
        msg = f"缺 {FUND_PANEL};先跑 build_fundamental_panel.py"
        raise FileNotFoundError(msg)
    fp = pd.read_csv(FUND_PANEL)[["ts_code", "ann_date", *FUND_COLS]].sort_values("ann_date")
    df = df.sort_values("trade_date")
    merged = pd.merge_asof(df, fp, left_on="trade_date", right_on="ann_date", by="ts_code", direction="backward")
    return merged.drop(columns=["ann_date"]).reset_index(drop=True)


def nuis_y(n: int = 300) -> LGBMRegressor:
    return LGBMRegressor(
        n_estimators=n,
        num_leaves=15,
        learning_rate=0.05,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RNG,
        verbose=-1,
    )


def nuis_t(n: int = 300) -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=n,
        num_leaves=15,
        learning_rate=0.05,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RNG,
        verbose=-1,
    )


def scalar(arr) -> float:
    return float(np.ravel(arr)[0])


def estimate(df: pd.DataFrame, action: str, sdy: float) -> dict:
    sub = df[(df["subtype"] == action) | (df["D"] == 0)].copy()
    sub["D"] = (sub["subtype"] == action).astype(int)
    y, t = sub["rel"].to_numpy(), sub["D"].to_numpy()
    xv = sub[["val_pct"]].to_numpy()
    xcf = sub[XCF_COLS].to_numpy()
    w = sub[WCOLS].to_numpy()
    res: dict = {"action": action, "treated": int(t.sum()), "control": int((t == 0).sum())}

    pscols = [*WCOLS, "val_pct"]
    ps = LogisticRegression(max_iter=1000).fit(sub[pscols].to_numpy(), t).predict_proba(sub[pscols].to_numpy())[:, 1]
    lo, hi = max(ps[t == 1].min(), ps[t == 0].min()), min(ps[t == 1].max(), ps[t == 0].max())
    res["overlap_frac"] = round(float(((ps >= lo) & (ps <= hi)).mean()), 3)

    ld = LinearDML(model_y=nuis_y(), model_t=nuis_t(), discrete_treatment=True, cv=4, random_state=RNG)
    ld.fit(y, t, X=xv, W=w)
    ate = scalar(ld.ate(xv))
    ai = ld.ate_interval(xv, alpha=0.10)
    ci = ld.coef__interval(alpha=0.10)
    dstd = abs(ate) / sdy
    rr = np.exp(0.91 * dstd)
    res["lindml"] = {
        "ate_pct": round(ate * 100, 2),
        "ate_ci": [round(scalar(ai[0]) * 100, 2), round(scalar(ai[1]) * 100, 2)],
        "ate_sig": bool(scalar(ai[0]) * scalar(ai[1]) > 0),
        "cate_low_pct": round(scalar(ld.const_marginal_effect(np.array([[0.15]]))) * 100, 2),
        "cate_high_pct": round(scalar(ld.const_marginal_effect(np.array([[0.85]]))) * 100, 2),
        "valuation_slope_pct": round(scalar(ld.coef_) * 100, 2),
        "slope_ci": [round(scalar(ci[0]) * 100, 2), round(scalar(ci[1]) * 100, 2)],
        "slope_sig": bool(scalar(ci[0]) * scalar(ci[1]) > 0),
        "e_value": round(float(rr + np.sqrt(rr * (rr - 1))), 2),
    }

    cf = CausalForestDML(
        model_y=nuis_y(),
        model_t=nuis_t(),
        discrete_treatment=True,
        n_estimators=800,
        min_samples_leaf=20,
        cv=4,
        random_state=RNG,
    )
    cf.fit(y, t, X=xcf, W=w)
    med = [float(sub[c].median()) for c in XCF_COLS]
    grid = np.array([[0.15, *med[1:]], [0.85, *med[1:]]])  # 低估值 vs 高估值,其余因子取中位
    eff = cf.effect(grid)
    ei = cf.effect_interval(grid, alpha=0.10)
    res["causalforest"] = {
        "cate_low_pct": round(scalar(eff[0]) * 100, 2),
        "cate_low_ci": [round(ei[0][0] * 100, 2), round(ei[1][0] * 100, 2)],
        "cate_high_pct": round(scalar(eff[1]) * 100, 2),
        "cate_high_ci": [round(ei[0][1] * 100, 2), round(ei[1][1] * 100, 2)],
        "var_importance": {n: round(float(v), 3) for n, v in zip(XCF_NAMES, cf.feature_importances_, strict=False)},
    }

    rng = np.random.RandomState(RNG)
    null = []
    for _ in range(60):
        try:
            lp = LinearDML(model_y=nuis_y(120), model_t=nuis_t(120), discrete_treatment=True, cv=2, random_state=RNG)
            lp.fit(y, rng.permutation(t), X=xv, W=w)
            null.append(scalar(lp.ate(xv)))
        except Exception:  # noqa: BLE001, S112 - permutation fold may degenerate; skip that draw
            continue
    arr = np.array(null)
    res["placebo_perm_p"] = round(float((np.abs(arr) >= abs(ate)).mean()), 3) if len(arr) else None
    return res


def main() -> None:
    df = build_panel()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "cate_panel_14firm.csv", index=False)
    fit = df[df["val_pct"].notna()].copy()
    fit["rel"] = fit["rel"].clip(fit["rel"].quantile(0.01), fit["rel"].quantile(0.99))
    for col in sorted({*WCOLS, *XCF_COLS, "val_pct"}):
        fit[col] = pd.to_numeric(fit[col], errors="coerce").fillna(fit[col].median())
    sdy = float(fit["rel"].std())
    results = [estimate(fit, action, sdy) for action in HEADLINE_ACTIONS]
    (OUT_DIR / "cate_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    print(f"\npanel rows: {len(df)} | saved -> {OUT_DIR}/")


if __name__ == "__main__":
    main()

"""Tier2 causal panel (22 firms): does abnormal pre-event external ATTENTION
*causally* lift the post-event relative market-cap reaction — on a CLEAN long panel?

Standalone companion to build_causal_event_study.py (the 9-firm engine). The 9-firm
study reads the SSOT feature wide table (modeling_dataset_enhanced_v3.csv), which only
exists for 9 firms; rebuilding that pipeline for 22 firms is blocked. So this builds the
panel DIRECTLY from raw Tushare + Eastmoney data and reuses ONLY the engine's statistical
primitives (ols / cluster_vcov / wcb_p / design) so S3/S4 are computed identically.

WHY a new treatment (see DECISION_LEDGER INV-006): the 9-firm treatment used IR/institution
survey counts, but that IR data only exists for 2025-06+ (both 9 and 22 firms). Built as a
2017-2026 attention panel it is a coverage artifact (raw level jumps ~160x in 2025). So this
script switches to attention proxies with TRUE full-panel coverage:
  primary    = analyst research-report intensity (Eastmoney research reports, 2017-2026)
  robustness = abnormal pre-event turnover (daily_basic.turnover_rate, 100% covered)

Frozen caliber (mirrors the 9-firm design, see docs/reports/CAUSAL_DESIGN.md):
  events    = financial announcements (forecast/express/dividend/repurchase ann_date)
              — distinct from the attention treatment to avoid mechanical circularity
  label y   = own 20-trading-day market-cap return minus the ex-self equal-weight
              peer-basket return over the same calendar window (relative reaction)
  treatment = pre-event 90-calendar-day attention, within-firm selfz (expanding,
              prior-events-only, >=3 priors) -> continuous + binary 1[selfz>0]
  controls  = size / liquidity / valuation(pe,pb) / recent volatility / 60d reversal
              (all strictly <= event_date-1, point-in-time safe)

Deliberate deviation from the 9-firm code, noted in CAUSAL_RESULTS: the peer benchmark
uses the FULL ex-self universe over the same calendar window, not only firms with an
event on the same day. The announcement-only event set is too sparse for same-day peers.

Outputs under data/processed/modeling/causal_22/:
  causal_panel_22.csv        the frozen regression table (treatment+controls+y)
  pit_audit_22.csv           point-in-time provenance of every regressor
  s3_coef_movement_22.csv    M0 naive -> +firm FE -> +year FE -> +controls (primary treat)
  s4_robust_22.csv           cluster-robust SE + WCB p (primary + turnover robustness)
  causal_summary_22.json     headline numbers for the report

Run from repo root:
  .venv/bin/python market-impact-study/build_causal_panel_22.py
"""
# 职责：从原始 Tushare+研报/换手数据建 22 家干净长面板因果(事件/标签/全覆盖注意力处理/控制)，复用 9 家引擎统计原语跑 S3/S4，落盘 causal_22。
# 不做什么：不采集数据/不改 SSOT 或 9 家产物/不做样本外预测；只读 data/raw 与口径表，只写 causal_22 目录。
# 允许依赖层：标准库、numpy/pandas、peer_universe(口径)、build_causal_event_study(只用其纯统计函数)。
# 谁不应该 import：采集/SSOT/建模脚本不应 import 本分析入口；它是下游只读消费者。

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from build_causal_event_study import cluster_vcov, design, ols, wcb_p, winsorize, zscore
from peer_universe import load_companies

HERE = Path(__file__).resolve().parent
TU = HERE / "data" / "raw" / "tushare"
RESEARCH_DIR = HERE / "data" / "raw" / "akshare" / "eastmoney_research_report"
OUT = HERE / "data" / "processed" / "modeling" / "causal_22"
OUT.mkdir(parents=True, exist_ok=True)

COMPANY = "ts_code"  # must match build_causal_event_study.COMPANY for design()
EVENT_DATE = "event_date"
ANN_SOURCES = ["forecast", "express", "dividend", "repurchase"]
FWD_WIN = 20  # post-event trading days for the reaction window
ATT_WIN_DAYS = 90  # pre-event calendar days for the attention treatment
MIN_PEERS = 5  # require this many ex-self peers for a defined relative reaction
MIN_PRIOR = 3  # selfz needs at least this many prior own events
CONTROLS = [
    "log_total_mv_pre",  # size
    "turnover_avg_m20_m1",  # liquidity
    "pe_pre",  # valuation
    "pb_pre",  # valuation
    "volatility_m20_m1",  # recent risk
    "ret_m60_m1",  # reversal / momentum
]


# ------------------------------ per-firm market data ------------------------------
def load_market(ts_code: str) -> pd.DataFrame | None:
    """Merge daily + adj_factor + daily_basic into one trade-date-sorted frame."""
    dp = TU / "daily" / f"{ts_code}.csv"
    bp = TU / "daily_basic" / f"{ts_code}.csv"
    ap = TU / "adj_factor" / f"{ts_code}.csv"
    if not (dp.exists() and bp.exists()):
        return None
    daily = pd.read_csv(dp, dtype={"trade_date": str})
    basic = pd.read_csv(bp, dtype={"trade_date": str})
    md = daily.merge(basic, on=["ts_code", "trade_date"], how="inner", suffixes=("", "_b"))
    if ap.exists():
        adj = pd.read_csv(ap, dtype={"trade_date": str})
        md = md.merge(adj, on=["ts_code", "trade_date"], how="left")
    else:
        md["adj_factor"] = 1.0
    md["dt"] = pd.to_datetime(md["trade_date"], format="%Y%m%d", errors="coerce")
    md = md.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)
    for col in ("close", "pct_chg", "total_mv", "turnover_rate", "pe", "pb", "adj_factor"):
        if col in md.columns:
            md[col] = pd.to_numeric(md[col], errors="coerce")
    md["adj_close"] = md["close"] * md["adj_factor"].fillna(1.0)
    return md[["dt", "total_mv", "turnover_rate", "pe", "pb", "pct_chg", "adj_close"]]


def load_research(symbol: str) -> pd.DataFrame:
    """Analyst research-report activity: one row per report, dated by 日期 (full 2017-2026
    coverage). Each report counts 1 toward pre-event attention intensity."""
    fp = RESEARCH_DIR / f"{symbol}.csv"
    if not fp.exists():
        return pd.DataFrame(columns=["dt", "cnt"])
    rr = pd.read_csv(fp, dtype=str)
    if "日期" not in rr.columns:
        return pd.DataFrame(columns=["dt", "cnt"])
    dt = pd.to_datetime(rr["日期"], errors="coerce")
    out = pd.DataFrame({"dt": dt, "cnt": 1.0}).dropna(subset=["dt"]).sort_values("dt")
    return out.reset_index(drop=True)


def load_events(ts_code: str) -> list[tuple[pd.Timestamp, str]]:
    """Financial-announcement events: (ann_date, category) from the 4 sources."""
    evs: list[tuple[pd.Timestamp, str]] = []
    for src in ANN_SOURCES:
        fp = TU / src / f"{ts_code}.csv"
        if not fp.exists():
            continue
        df = pd.read_csv(fp, dtype={"ann_date": str})
        if "ann_date" not in df.columns:
            continue
        for d in pd.to_datetime(df["ann_date"], format="%Y%m%d", errors="coerce").dropna():
            evs.append((d, src))
    return evs


# ------------------------------ window helpers ------------------------------
def pos_on_or_after(dts: np.ndarray, t: np.datetime64) -> int | None:
    i = int(np.searchsorted(dts, t, side="left"))
    return i if i < len(dts) else None


def fwd_return(mv: np.ndarray, p0: int, win: int) -> float | None:
    end = p0 + win
    if end >= len(mv) or not np.isfinite(mv[p0]) or mv[p0] == 0 or not np.isfinite(mv[end]):
        return None
    return float(mv[end] / mv[p0] - 1.0)


def peer_basket_mean(t0, code, usable, dts, mv) -> float | None:
    """Ex-self equal-weight peer 20td return over the same calendar window (None if <MIN_PEERS)."""
    rets = []
    for pcode in usable:
        if pcode == code:
            continue
        pj = pos_on_or_after(dts[pcode], np.datetime64(t0))
        if pj is None:
            continue
        r = fwd_return(mv[pcode], pj, FWD_WIN)
        if r is not None:
            rets.append(r)
    return float(np.mean(rets)) if len(rets) >= MIN_PEERS else None


def research_count(research_dt: np.ndarray, t0) -> float:
    """Analyst report count in [t0-ATT_WIN_DAYS, t0-1]."""
    lo = np.datetime64(t0) - np.timedelta64(ATT_WIN_DAYS, "D")
    return float(((research_dt >= lo) & (research_dt < np.datetime64(t0))).sum())


def event_controls(md: pd.DataFrame, pre: int) -> dict:
    """PIT-safe pre-event controls + abnormal turnover, all computed at/<= pre (= t0-1)."""
    tov = md["turnover_rate"].to_numpy()
    pe, pb = md["pe"].to_numpy(), md["pb"].to_numpy()
    pct, adj = md["pct_chg"].to_numpy(), md["adj_close"].to_numpy()
    size = md["total_mv"].to_numpy()[pre]
    lo20 = max(0, pre - 19)
    lo5, base_lo = max(0, pre - 4), max(0, pre - 59)
    t_short = np.nanmean(tov[lo5 : pre + 1]) if pre + 1 > lo5 else np.nan
    t_base = np.nanmean(tov[base_lo : pre - 4]) if pre - 4 > base_lo else np.nan
    turn_abn = (
        float(np.log(t_short / t_base))
        if np.isfinite(t_short) and np.isfinite(t_base) and t_short > 0 and t_base > 0
        else np.nan
    )
    return {
        "turn_abn": turn_abn,
        "log_total_mv_pre": float(np.log(size)) if np.isfinite(size) and size > 0 else np.nan,
        "turnover_avg_m20_m1": float(np.nanmean(tov[lo20 : pre + 1])) if pre + 1 > lo20 else np.nan,
        "pe_pre": float(pe[pre]) if np.isfinite(pe[pre]) else np.nan,
        "pb_pre": float(pb[pre]) if np.isfinite(pb[pre]) else np.nan,
        "volatility_m20_m1": float(np.nanstd(pct[lo20 : pre + 1])) if pre + 1 - lo20 >= 5 else np.nan,
        "ret_m60_m1": (
            float(adj[pre] / adj[pre - 59] - 1.0)
            if pre - 59 >= 0 and np.isfinite(adj[pre - 59]) and adj[pre - 59] != 0
            else np.nan
        ),
    }


def within_firm_selfz(panel: pd.DataFrame, col: str) -> pd.Series:
    """Trailing within-firm z-score using prior events only (>=MIN_PRIOR priors)."""
    out = pd.Series(np.nan, index=panel.index)
    for idx in panel.groupby(COMPANY).groups.values():
        s = panel.loc[idx, col]
        mean_prior = s.expanding().mean().shift(1)
        std_prior = s.expanding().std().shift(1)
        cnt_prior = s.expanding().count().shift(1)
        z = (s - mean_prior) / std_prior.replace(0, np.nan)
        z[cnt_prior < MIN_PRIOR] = np.nan
        out.loc[idx] = z
    return out


def firm_events(code: str, md: pd.DataFrame, d: np.ndarray) -> list[tuple]:
    """Dedup financial-announcement events to one (aligned t0, category) per firm."""
    seen, out = set(), []
    for ann_dt, cat in sorted(load_events(code)):
        p0 = pos_on_or_after(d, np.datetime64(ann_dt))
        if p0 is None:
            continue
        t0 = md.at[p0, "dt"]
        if (t0, cat) in seen:
            continue
        seen.add((t0, cat))
        out.append((t0, p0, cat))
    return out


# ------------------------------ build the panel ------------------------------
def build_panel():
    companies = load_companies()
    firms = {c["ts_code"]: c["symbol"] for c in companies}
    market: dict[str, pd.DataFrame] = {}
    dts: dict[str, np.ndarray] = {}
    mv: dict[str, np.ndarray] = {}
    for code in firms:
        md = load_market(code)
        if md is None or md.empty:
            continue
        market[code] = md
        dts[code] = md["dt"].to_numpy()
        mv[code] = md["total_mv"].to_numpy()
    usable = list(market)
    diag = {"firms_with_market": len(usable)}

    rows = []
    drop = {"no_label": 0, "few_peers": 0, "no_controls": 0}
    for code in usable:
        md = market[code]
        research = load_research(firms[code])
        rdt = research["dt"].to_numpy() if not research.empty else np.array([], dtype="datetime64[ns]")
        for t0, p0, cat in firm_events(code, md, dts[code]):
            own = fwd_return(mv[code], p0, FWD_WIN)
            if own is None:
                drop["no_label"] += 1
                continue
            peer_mean = peer_basket_mean(t0, code, usable, dts, mv)
            if peer_mean is None:
                drop["few_peers"] += 1
                continue
            pre = p0 - 1  # PIT: all controls strictly before the event day
            if pre < 0:
                drop["no_controls"] += 1
                continue
            rows.append(
                {
                    COMPANY: code,
                    EVENT_DATE: t0,
                    "year": t0.year,
                    "primary_category": cat,
                    "y_raw": own - peer_mean,
                    "research_cnt": research_count(rdt, t0),
                    **event_controls(md, pre),
                }
            )

    panel = pd.DataFrame(rows).sort_values([COMPANY, EVENT_DATE]).reset_index(drop=True)
    diag["events_kept"] = len(panel)
    diag["drops"] = drop
    panel["research_selfz"] = within_firm_selfz(panel, "research_cnt")
    panel["turn_selfz"] = within_firm_selfz(panel, "turn_abn")
    return panel, diag


def process_sample(panel: pd.DataFrame):
    """Mirror build_causal_event_study.build_sample winsorize/zscore recipe.
    Primary treatment = analyst research-report attention selfz; turn_selfz kept for the
    turnover robustness spec in robust()."""
    samp = panel[panel["research_selfz"].notna() & panel["y_raw"].notna()].copy().reset_index(drop=True)
    samp["y"] = winsorize(samp["y_raw"])
    samp["treat"] = zscore(winsorize(samp["research_selfz"]))  # 1 SD of abnormal attention
    samp["treat_bin"] = (samp["research_selfz"] > 0).astype(float)
    for c in CONTROLS:
        med = samp[c].median()
        samp[c] = zscore(winsorize(samp[c].fillna(med)))
    cat = pd.get_dummies(samp["primary_category"], prefix="category").astype(float)
    cat_cols = list(cat.columns)
    samp = pd.concat([samp, cat], axis=1)
    return samp, cat_cols


# ------------------------------ S3 / S4 (reuse engine primitives) ------------------------------
def layered_fe(samp: pd.DataFrame, cat_cols: list[str]) -> pd.DataFrame:
    specs = [
        ("M0_naive", False, False, []),
        ("M1_firmFE", True, False, []),
        ("M2_firmFE_yearFE", True, True, []),
        ("M3_full_controls", True, True, CONTROLS + cat_cols),
    ]
    clusters = samp[COMPANY].to_numpy()
    y = samp["y"].to_numpy()
    rows = []
    for name, firm, yr, ctrls in specs:
        X, _, jt = design(samp, "treat", ctrls, use_firm_fe=firm, use_year_fe=yr)
        beta, resid, r2 = ols(X, y)
        V = cluster_vcov(X, resid, clusters)
        se = float(np.sqrt(V[jt, jt]))
        rows.append(
            {
                "model": name,
                "treat_coef": round(float(beta[jt]), 5),
                "cluster_robust_se": round(se, 5),
                "t_stat": round(float(beta[jt] / se), 3),
                "r2": round(r2, 4),
                "n": len(y),
                "k_params": X.shape[1],
            }
        )
    mv_df = pd.DataFrame(rows)
    base = mv_df.loc[mv_df.model == "M0_naive", "treat_coef"].iloc[0]
    mv_df["pct_of_naive"] = (mv_df["treat_coef"] / base * 100).round(1) if base else np.nan
    mv_df.to_csv(OUT / "s3_coef_movement_22.csv", index=False, encoding="utf-8-sig")
    return mv_df


def robust(samp: pd.DataFrame, cat_cols: list[str]) -> pd.DataFrame:
    y = samp["y"].to_numpy()
    n_firm = samp[COMPANY].nunique()
    out = []
    for tname in ("treat", "treat_bin"):
        X, _, jt = design(
            samp.assign(treat=samp[tname]), "treat", CONTROLS + cat_cols, use_firm_fe=True, use_year_fe=True
        )
        t_obs, p = wcb_p(X, y, samp[COMPANY].to_numpy(), jt)
        beta, resid, _ = ols(X, y)
        V = cluster_vcov(X, resid, samp[COMPANY].to_numpy())
        out.append(
            {
                "spec": "M3",
                "treatment": tname,
                "cluster": f"firm({n_firm})",
                "coef": round(float(beta[jt]), 5),
                "se": round(float(np.sqrt(V[jt, jt])), 5),
                "t_stat": round(t_obs, 3),
                "wcb_p": round(p, 4),
                "n": len(y),
            }
        )
    X, _, jt = design(samp, "treat", CONTROLS + cat_cols, use_firm_fe=True, use_year_fe=True)
    beta, resid, _ = ols(X, y)
    for clab, cvec in (
        ("firm-year", (samp[COMPANY].astype(str) + "_" + samp["year"].astype(str)).to_numpy()),
        ("month", samp[EVENT_DATE].dt.to_period("M").astype(str).to_numpy()),
    ):
        V = cluster_vcov(X, resid, cvec)
        out.append(
            {
                "spec": "M3",
                "treatment": "treat",
                "cluster": f"{clab}({len(np.unique(cvec))})",
                "coef": round(float(beta[jt]), 5),
                "se": round(float(np.sqrt(V[jt, jt])), 5),
                "t_stat": round(float(beta[jt] / np.sqrt(V[jt, jt])), 3),
                "wcb_p": np.nan,
                "n": len(y),
            }
        )

    # robustness: market-based attention (abnormal pre-event turnover selfz), M3 spec
    sub = samp[samp["turn_selfz"].notna()].copy().reset_index(drop=True)
    if sub[COMPANY].nunique() >= 5 and len(sub) > 40:
        sub["treat"] = zscore(winsorize(sub["turn_selfz"]))
        ysub = sub["y"].to_numpy()
        scat = [c for c in cat_cols if c in sub.columns and sub[c].nunique() > 1]
        X, _, jt = design(sub, "treat", CONTROLS + scat, use_firm_fe=True, use_year_fe=True)
        t_obs, p = wcb_p(X, ysub, sub[COMPANY].to_numpy(), jt)
        beta, resid, _ = ols(X, ysub)
        V = cluster_vcov(X, resid, sub[COMPANY].to_numpy())
        out.append(
            {
                "spec": "M3_robustness",
                "treatment": "turnover_abn_selfz",
                "cluster": f"firm({sub[COMPANY].nunique()})",
                "coef": round(float(beta[jt]), 5),
                "se": round(float(np.sqrt(V[jt, jt])), 5),
                "t_stat": round(t_obs, 3),
                "wcb_p": round(p, 4),
                "n": len(sub),
            }
        )

    df = pd.DataFrame(out)
    df.to_csv(OUT / "s4_robust_22.csv", index=False, encoding="utf-8-sig")
    return df


def write_pit_audit():
    rows = [
        {
            "regressor": "treat (primary)",
            "source": "analyst research-report count [t0-90d, t0-1] within-firm selfz",
            "as_of": "<= event_date-1",
            "pit_safe": True,
        },
        {"regressor": "treat_bin", "source": "1[research_selfz>0]", "as_of": "<= event_date-1", "pit_safe": True},
        {
            "regressor": "turnover_abn_selfz (robustness)",
            "source": "log(turnover[t0-5,t0-1]/turnover[t0-60,t0-6]) within-firm selfz",
            "as_of": "<= event_date-1",
            "pit_safe": True,
        },
        {
            "regressor": "log_total_mv_pre",
            "source": "daily_basic.total_mv at t0-1",
            "as_of": "<= event_date-1",
            "pit_safe": True,
        },
        {
            "regressor": "turnover_avg_m20_m1",
            "source": "daily_basic.turnover_rate mean [t0-20,t0-1]",
            "as_of": "<= event_date-1",
            "pit_safe": True,
        },
        {
            "regressor": "pe_pre / pb_pre",
            "source": "daily_basic.pe/pb at t0-1",
            "as_of": "<= event_date-1",
            "pit_safe": True,
        },
        {
            "regressor": "volatility_m20_m1",
            "source": "daily.pct_chg std [t0-20,t0-1]",
            "as_of": "<= event_date-1",
            "pit_safe": True,
        },
        {
            "regressor": "ret_m60_m1",
            "source": "adj_close[t0-1]/adj_close[t0-60]-1",
            "as_of": "<= event_date-1",
            "pit_safe": True,
        },
        {
            "regressor": "y (outcome)",
            "source": "own minus ex-self peer 20td total_mv return",
            "as_of": "t0 .. t0+20 (post-event, intended)",
            "pit_safe": True,
        },
    ]
    pd.DataFrame(rows).to_csv(OUT / "pit_audit_22.csv", index=False, encoding="utf-8-sig")


def main():
    print("building 22-firm causal panel from raw ...")
    panel, diag = build_panel()
    panel.to_csv(OUT / "causal_panel_22.csv", index=False, encoding="utf-8-sig")
    print(
        f"  raw events kept={diag['events_kept']} firms_with_market={diag['firms_with_market']} drops={diag['drops']}"
    )

    samp, cat_cols = process_sample(panel)
    assert (samp["treat"].notna() & samp["y"].notna()).all(), "PIT/NaN leak in analysis sample"
    print(
        f"  analysis sample n={len(samp)}, firms={samp[COMPANY].nunique()}, "
        f"years={samp['year'].min()}-{samp['year'].max()}, attn-selfz firms={samp[COMPANY].nunique()}, "
        f"event-type dummies={len(cat_cols)}"
    )
    write_pit_audit()

    print("\nS3: layered fixed-effects coefficient movement ...")
    mv_df = layered_fe(samp, cat_cols)
    print(mv_df.to_string(index=False))

    print("\nS4: cluster-robust SE + Wild Cluster Bootstrap ...")
    rb = robust(samp, cat_cols)
    print(rb.to_string(index=False))

    m0 = float(mv_df[mv_df.model == "M0_naive"].treat_coef.iloc[0])
    m3 = mv_df[mv_df.model == "M3_full_controls"].iloc[0]
    m3w = rb[(rb.spec == "M3") & (rb.treatment == "treat")].iloc[0]
    m3wb = rb[(rb.spec == "M3") & (rb.treatment == "treat_bin")].iloc[0]
    turn_rows = rb[rb.treatment == "turnover_abn_selfz"]
    summary = {
        "n": len(samp),
        "firms": int(samp[COMPANY].nunique()),
        "years": f"{int(samp['year'].min())}-{int(samp['year'].max())}",
        "events_source": "forecast/express/dividend/repurchase ann_date",
        "treatment_primary": "analyst research-report attention (90d count, within-firm selfz)",
        "naive_coef_M0": m0,
        "fully_controlled_coef_M3": float(m3.treat_coef),
        "coef_pct_of_naive_M3": float(m3.pct_of_naive),
        "M3_continuous_wcb_p": float(m3w.wcb_p),
        "M3_binary_coef": float(m3wb.coef),
        "M3_binary_wcb_p": float(m3wb.wcb_p),
        "robustness_turnover_coef": float(turn_rows.coef.iloc[0]) if len(turn_rows) else None,
        "robustness_turnover_wcb_p": float(turn_rows.wcb_p.iloc[0]) if len(turn_rows) else None,
        "robustness_turnover_n": int(turn_rows.n.iloc[0]) if len(turn_rows) else None,
    }
    (OUT / "causal_summary_22.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote 22-firm causal artifacts to", OUT)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

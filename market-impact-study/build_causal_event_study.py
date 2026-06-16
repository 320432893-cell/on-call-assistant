"""Causal extension (S2-S6): does abnormal pre-event institutional attention
*causally* lift the post-event relative market-cap reaction?

This is the causal companion to the v3/v4 predictive models. It does NOT try to
predict out-of-sample; it runs in-sample fixed-effects inference on the full
labeled panel and stress-tests the causal reading with placebos and a sensitivity
bound, per docs/reports/CAUSAL_DESIGN.md.

Default frozen caliber (see CAUSAL_DESIGN.md "待你定稿"):
  A window   = m90
  B treatment= continuous selfz (primary) + binary 1[selfz>0] (robustness)
  C time FE  = year
  D sample   = treatment-non-missing rows only

Pipeline:
  S2  build treatment + PIT-safe control set; assert point-in-time; write reg table
  S3  layered FE OLS  M0 naive -> +firm FE -> +year FE -> +controls; coef movement
  S4  cluster-robust SE (by firm) + Wild Cluster Bootstrap p; cluster sensitivity
  S5  placebos: timing (post-event attention), outcome (pre-event return),
      leave-one-firm, permutation-of-treatment
  S6  Oster delta* (selection on unobservables) + approximate E-value

Outputs under data/processed/modeling/causal/:
  causal_analysis_sample.csv     the frozen regression table (treatment+controls+y)
  pit_audit.csv                  point-in-time provenance of every regressor
  s3_coef_movement.csv           M0->M3 treatment coefficient + R2 movement
  s4_robust_inference.csv        cluster-robust SE + WCB p (+ cluster variants)
  s5_placebos.csv                four placebo tests
  s6_sensitivity.csv             Oster delta* and E-value
  causal_summary.json            headline numbers for the report

Run from repo root:
  .venv/bin/python market-impact-study/build_causal_event_study.py
"""
# 职责：在面板上做事件研究的因果推断——构样本+PIT审计、逐层FE系数移动(S3)、聚类稳健/WCB(S4)、安慰剂(S5)、敏感性(S6)，落盘 data/processed/modeling/causal。
# 不做什么：不做样本外预测/不训练 ML 模型；不采集/不改 SSOT 标签口径(只读宽表+台账)。
# 允许依赖层：标准库、pandas/numpy/statsmodels、data/processed 下宽表与管理层台账。
# 谁不应该 import：采集/SSOT 脚本不应 import 本分析入口；它是下游只读消费者。

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
MODELING = HERE / "data" / "processed" / "modeling"
WIDE = MODELING / "modeling_dataset_enhanced_v3.csv"
LEDGER = HERE / "data" / "processed" / "management" / "management_signal_ledger.csv"
OUT = MODELING / "causal"
OUT.mkdir(parents=True, exist_ok=True)

COMPANY = "ts_code"
EVENT_DATE = "event_date"
TARGET = "relative_mv_return_p0_p20"

# --- frozen caliber (S1) ---
TREAT_RAW = "mgmt_institution_count_sum_m90__selfz"  # abnormal attention vs own history
CONTROLS = [
    "log_total_mv_pre",  # size
    "turnover_avg_m20_m1",  # liquidity
    "pe_pre",  # valuation
    "pb_pre",  # valuation
    "volatility_m20_m1",  # recent risk
    "ret_m60_m1",  # reversal / momentum
]
CATEGORY_DUMMIES_PREFIX = "category_"  # event-type fixed part, known at event date
PLACEBO_OUTCOME = "rel_to_peer_ret_m60_m1"  # pre-event relative return (no post-event info)

RNG = np.random.default_rng(0)
WCB_B = 999
WINSOR = (0.01, 0.99)


# ----------------------------- linear algebra helpers -----------------------------
def ols(x: np.ndarray, y: np.ndarray):
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return beta, resid, r2


def cluster_vcov(x: np.ndarray, resid: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    xtx_inv = np.linalg.inv(x.T @ x)
    k = x.shape[1]
    meat = np.zeros((k, k))
    uniq = np.unique(clusters)
    for g in uniq:
        xg = x[clusters == g]
        sg = xg.T @ resid[clusters == g]
        meat += np.outer(sg, sg)
    n_g, n = len(uniq), x.shape[0]
    adj = (n_g / (n_g - 1)) * ((n - 1) / (n - k))
    return adj * xtx_inv @ meat @ xtx_inv


def wcb_p(x, y, clusters, j, b=WCB_B):
    """Restricted Wild Cluster Bootstrap p-value for H0: beta_j = 0 (Rademacher)."""
    beta, resid, _ = ols(x, y)
    v_cov = cluster_vcov(x, resid, clusters)
    t_obs = beta[j] / np.sqrt(v_cov[j, j])
    keep = [c for c in range(x.shape[1]) if c != j]
    xr = x[:, keep]
    beta_r, resid_r, _ = ols(xr, y)
    fitted_r = xr @ beta_r
    uniq = np.unique(clusters)
    count = 0
    for _ in range(b):
        w = RNG.choice([-1.0, 1.0], size=len(uniq))
        wmap = dict(zip(uniq, w, strict=True))
        wv = np.array([wmap[c] for c in clusters])
        y_star = fitted_r + resid_r * wv
        b_s, r_s, _ = ols(x, y_star)
        v_s = cluster_vcov(x, r_s, clusters)
        t_s = b_s[j] / np.sqrt(v_s[j, j])
        if abs(t_s) >= abs(t_obs):
            count += 1
    return float(t_obs), count / b


def drop_collinear(xdf: pd.DataFrame, tol=1e-8) -> pd.DataFrame:
    """Greedily keep columns (in order) that raise the design's rank. Because
    const+treat come first they are always retained; redundant dummies (e.g. an
    exhaustive one-hot collinear with the intercept, or a category absent in a
    leave-one-firm subsample) are dropped."""
    mat = xdf.to_numpy(dtype=float)
    kept: list[int] = []
    for i in range(mat.shape[1]):
        v = mat[:, i]
        if kept:
            a = mat[:, kept]
            coef, *_ = np.linalg.lstsq(a, v, rcond=None)
            r = v - a @ coef
        else:
            r = v
        if np.linalg.norm(r) > tol * (np.linalg.norm(v) + 1e-12):
            kept.append(i)
    return xdf.iloc[:, kept]


def design(frame: pd.DataFrame, treat_col: str, controls, *, use_firm_fe, use_year_fe):
    """Assemble [const, treat, controls?, firmFE?, yearFE?] -> (X, colnames, treat_idx).
    Collinear columns are dropped; const + treat are guaranteed kept."""
    parts = [pd.Series(1.0, index=frame.index, name="const"), frame[treat_col].rename("treat")]
    if controls:
        parts.append(frame[controls])
    if use_firm_fe:
        parts.append(pd.get_dummies(frame[COMPANY], prefix="firm", drop_first=True).astype(float))
    if use_year_fe:
        parts.append(pd.get_dummies(frame["year"], prefix="yr", drop_first=True).astype(float))
    X = drop_collinear(pd.concat(parts, axis=1))
    colnames = list(X.columns)
    return X.to_numpy(dtype=float), colnames, colnames.index("treat")


# --------------------------------- S2: build sample ---------------------------------
def winsorize(s: pd.Series, lo=WINSOR[0], hi=WINSOR[1]) -> pd.Series:
    ql, qh = s.quantile(lo), s.quantile(hi)
    return s.clip(ql, qh)


def zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / (sd if sd else 1.0)


def build_forward_attention(panel: pd.DataFrame) -> pd.Series:
    """Timing-placebo treatment: institutional attention in the 90d AFTER the event,
    selfz'd the same way. Post-event attention cannot cause the already-realized
    reaction, so it must NOT survive as a 'predictor'."""
    led = pd.read_csv(LEDGER, low_memory=False)
    led = led[led["source_type"] == "institution_survey"].copy()
    led[EVENT_DATE] = pd.to_datetime(led[EVENT_DATE], errors="coerce")
    led["cnt"] = pd.to_numeric(led["institution_count"], errors="coerce").fillna(1.0)
    led = led.dropna(subset=[EVENT_DATE, COMPANY])
    fwd = pd.Series(np.nan, index=panel.index)
    for code, sub in led.groupby(COMPANY):
        dates = sub[EVENT_DATE].to_numpy()
        cnts = sub["cnt"].to_numpy()
        pidx = panel.index[panel[COMPANY] == code]
        for i in pidx:
            t = panel.at[i, EVENT_DATE]
            hi = t + np.timedelta64(90, "D")
            mask = (dates > np.datetime64(t)) & (dates <= np.datetime64(hi))
            fwd.at[i] = float(cnts[mask].sum())
    # selfz forward attention within firm using prior events only (same recipe as selfz)
    out = pd.Series(np.nan, index=panel.index)
    for idx in panel.groupby(COMPANY).groups.values():
        sub = fwd.loc[idx]
        mean_prior = sub.expanding().mean().shift(1)
        std_prior = sub.expanding().std().shift(1)
        cnt_prior = sub.expanding().count().shift(1)
        z = (sub - mean_prior) / std_prior.replace(0, np.nan)
        z[cnt_prior < 3] = np.nan
        out.loc[idx] = z
    return out


def build_sample():
    df = pd.read_csv(WIDE, low_memory=False)
    df[EVENT_DATE] = pd.to_datetime(df[EVENT_DATE], errors="coerce")
    df = df.sort_values([COMPANY, EVENT_DATE]).reset_index(drop=True)
    df["year"] = df[EVENT_DATE].dt.year

    needed = [TREAT_RAW, TARGET, *CONTROLS, PLACEBO_OUTCOME]
    for c in needed:
        if c not in df.columns:
            raise SystemExit(f"missing required column: {c}")
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # forward attention (timing placebo) on full panel BEFORE subsetting
    df["fwd_attention_selfz"] = build_forward_attention(df)

    # analysis sample = treatment & outcome both present (D = treatment-non-missing)
    samp = df[df[TREAT_RAW].notna() & df[TARGET].notna()].copy().reset_index(drop=True)

    # winsorize outcome (heavy tails) and standardize continuous regressors
    samp["y"] = winsorize(samp[TARGET])
    samp["treat"] = zscore(winsorize(samp[TREAT_RAW]))  # 1 SD of abnormal attention
    samp["treat_bin"] = (samp[TREAT_RAW] > 0).astype(float)  # robustness: above own norm
    for c in CONTROLS:
        med = samp[c].median()
        samp[c] = zscore(winsorize(samp[c].fillna(med)))
    # event-type dummies present in wide table
    cat_cols = [c for c in samp.columns if c.startswith(CATEGORY_DUMMIES_PREFIX)]
    for c in cat_cols:
        samp[c] = pd.to_numeric(samp[c], errors="coerce").fillna(0.0)
    samp["placebo_y"] = winsorize(samp[PLACEBO_OUTCOME].fillna(samp[PLACEBO_OUTCOME].median()))
    samp["fwd_attention_selfz_z"] = np.where(
        samp["fwd_attention_selfz"].notna(),
        zscore(winsorize(samp["fwd_attention_selfz"].fillna(samp["fwd_attention_selfz"].median()))),
        np.nan,
    )

    keep = [
        COMPANY,
        EVENT_DATE,
        "year",
        "primary_category",
        "y",
        "treat",
        "treat_bin",
        "placebo_y",
        "fwd_attention_selfz_z",
        TREAT_RAW,
        TARGET,
        *CONTROLS,
        *cat_cols,
    ]
    samp[keep].to_csv(OUT / "causal_analysis_sample.csv", index=False, encoding="utf-8-sig")

    # PIT audit: provenance of each regressor
    pit_rows = [
        {
            "regressor": "treat",
            "source": TREAT_RAW,
            "window": "event-90d..event-1, prior-events-only selfz",
            "as_of": "<= event_date",
            "pit_safe": True,
        },
        {
            "regressor": "treat_bin",
            "source": f"1[{TREAT_RAW}>0]",
            "window": "same",
            "as_of": "<= event_date",
            "pit_safe": True,
        },
    ]
    for c in CONTROLS:
        pit_rows.append(
            {
                "regressor": c,
                "source": c,
                "window": "pre-event (_pre / _m{N}_m1)",
                "as_of": "<= event_date",
                "pit_safe": True,
            }
        )
    for c in cat_cols:
        pit_rows.append(
            {"regressor": c, "source": c, "window": "event metadata", "as_of": "= event_date", "pit_safe": True}
        )
    pit_rows.append(
        {
            "regressor": "fwd_attention_selfz_z (PLACEBO ONLY)",
            "source": "ledger institution_survey",
            "window": "event+1..event+90 (POST-EVENT, intentionally leaky)",
            "as_of": "> event_date",
            "pit_safe": False,
        }
    )
    pd.DataFrame(pit_rows).to_csv(OUT / "pit_audit.csv", index=False, encoding="utf-8-sig")

    return samp, cat_cols


# --------------------------------- S3: layered FE ---------------------------------
def layered_fe(samp, cat_cols):
    specs = [
        ("M0_naive", False, False, []),
        ("M1_firmFE", True, False, []),
        ("M2_firmFE_yearFE", True, True, []),
        ("M3_full_controls", True, True, CONTROLS + cat_cols),
    ]
    rows = []
    clusters = samp[COMPANY].to_numpy()
    y = samp["y"].to_numpy()
    fits = {}
    for name, firm, yr, ctrls in specs:
        X, colnames, jt = design(samp, "treat", ctrls, use_firm_fe=firm, use_year_fe=yr)
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
        fits[name] = {"X": X, "colnames": colnames, "jt": jt, "beta": beta, "r2": r2}
    mv = pd.DataFrame(rows)
    # coefficient retention vs naive
    base = mv.loc[mv.model == "M0_naive", "treat_coef"].iloc[0]
    mv["pct_of_naive"] = (mv["treat_coef"] / base * 100).round(1)
    mv.to_csv(OUT / "s3_coef_movement.csv", index=False, encoding="utf-8-sig")
    return mv, fits


# --------------------------------- S4: robust inference ---------------------------------
def robust(samp, cat_cols):
    out = []
    y = samp["y"].to_numpy()
    # primary: full M3 spec, both continuous and binary treatment
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
                "cluster": "firm(9)",
                "coef": round(float(beta[jt]), 5),
                "se": round(float(np.sqrt(V[jt, jt])), 5),
                "t_stat": round(t_obs, 3),
                "wcb_p": round(p, 4),
                "n": len(y),
            }
        )
    # cluster sensitivity: firm-year and month clusters (continuous treat, M3)
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
    df = pd.DataFrame(out)
    df.to_csv(OUT / "s4_robust_inference.csv", index=False, encoding="utf-8-sig")
    return df


# --------------------------------- S5: placebos ---------------------------------
def placebos(samp, cat_cols):
    rows = []

    def m3_coef(frame, treat_col, ycol):
        X, _, jt = design(frame, treat_col, CONTROLS + cat_cols, use_firm_fe=True, use_year_fe=True)
        yv = frame[ycol].to_numpy()
        beta, resid, _ = ols(X, yv)
        V = cluster_vcov(X, resid, frame[COMPANY].to_numpy())
        se = float(np.sqrt(V[jt, jt]))
        t_obs, p = wcb_p(X, yv, frame[COMPANY].to_numpy(), jt)
        return float(beta[jt]), se, t_obs, p

    # 1. timing placebo: POST-event attention -> reaction (subset w/ fwd attn)
    sub = samp[samp["fwd_attention_selfz_z"].notna()].copy()
    if len(sub) > 60:
        c, se, t, p = m3_coef(sub.assign(treat=sub["fwd_attention_selfz_z"]), "treat", "y")
        rows.append(
            {
                "placebo": "timing_post_event_attention",
                "expectation": "near 0 / n.s.",
                "coef": round(c, 5),
                "se": round(se, 5),
                "t_stat": round(t, 3),
                "wcb_p": round(p, 4),
                "n": len(sub),
            }
        )

    # 2. outcome placebo: treatment -> pre-event (no-info) relative return
    c, se, t, p = m3_coef(samp, "treat", "placebo_y")
    rows.append(
        {
            "placebo": "outcome_pre_event_return",
            "expectation": "near 0 / n.s.",
            "coef": round(c, 5),
            "se": round(se, 5),
            "t_stat": round(t, 3),
            "wcb_p": round(p, 4),
            "n": len(samp),
        }
    )

    # 3. leave-one-firm: M3 treat coef dropping each firm
    y = samp["y"].to_numpy()
    for code in sorted(samp[COMPANY].unique()):
        sub = samp[samp[COMPANY] != code]
        X, _, jt = design(sub, "treat", CONTROLS + cat_cols, use_firm_fe=True, use_year_fe=True)
        beta, resid, _ = ols(X, sub["y"].to_numpy())
        V = cluster_vcov(X, resid, sub[COMPANY].to_numpy())
        rows.append(
            {
                "placebo": f"leave_out_{code}",
                "expectation": "effect persists",
                "coef": round(float(beta[jt]), 5),
                "se": round(float(np.sqrt(V[jt, jt])), 5),
                "t_stat": round(float(beta[jt] / np.sqrt(V[jt, jt])), 3),
                "wcb_p": np.nan,
                "n": len(sub),
            }
        )

    # 4. permutation placebo: shuffle treatment within firm, M3 coef distribution
    X_base, _, jt = design(samp, "treat", CONTROLS + cat_cols, use_firm_fe=True, use_year_fe=True)
    obs_beta, _, _ = ols(X_base, y)
    obs = float(obs_beta[jt])
    perm_betas = []
    treat = samp["treat"].to_numpy()
    firmcodes = samp[COMPANY].to_numpy()
    for _ in range(500):
        permuted = treat.copy()
        for code in np.unique(firmcodes):
            m = firmcodes == code
            permuted[m] = RNG.permutation(permuted[m])
        Xp = X_base.copy()
        Xp[:, jt] = permuted
        bp, _, _ = ols(Xp, y)
        perm_betas.append(float(bp[jt]))
    perm_betas = np.array(perm_betas)
    pval = float((np.abs(perm_betas) >= abs(obs)).mean())
    rows.append(
        {
            "placebo": "permutation_within_firm",
            "expectation": "obs in tail (p small)",
            "coef": round(obs, 5),
            "se": round(float(perm_betas.std()), 5),
            "t_stat": np.nan,
            "wcb_p": round(pval, 4),
            "n": len(samp),
        }
    )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "s5_placebos.csv", index=False, encoding="utf-8-sig")
    return df


# --------------------------------- S6: sensitivity ---------------------------------
def oster_delta(beta_s, r_s, beta_l, r_l, r_max):
    """Oster (2019) delta* that drives the bias-adjusted treatment effect to 0.
    short = +FE only (M2), long = +controls (M3). delta>1 => unobserved selection
    would have to exceed observed selection to nullify -> robust."""
    denom = (beta_s - beta_l) * (r_max - r_l)
    if denom == 0:
        return np.nan
    return (beta_l * (r_l - r_s)) / denom


def evalue_from_smd(d):
    """Approximate E-value for a standardized mean difference d (binary treatment,
    continuous outcome). Chinn approx RR = exp(0.91*d); VanderWeele E-value."""
    rr = float(np.exp(0.91 * abs(d)))
    if rr < 1:
        rr = 1 / rr
    ev = rr + np.sqrt(rr * (rr - 1))
    return rr, float(ev)


def sensitivity(samp, fits, cat_cols):
    beta_s = fits["M2_firmFE_yearFE"]["beta"][fits["M2_firmFE_yearFE"]["jt"]]
    r_s = fits["M2_firmFE_yearFE"]["r2"]
    beta_l = fits["M3_full_controls"]["beta"][fits["M3_full_controls"]["jt"]]
    r_l = fits["M3_full_controls"]["r2"]
    rows = []
    for label, r_max in (("Rmax=1.0", 1.0), ("Rmax=1.3*Rl", min(1.3 * r_l, 1.0)), ("Rmax=2.0*Rl", min(2.0 * r_l, 1.0))):
        d = oster_delta(float(beta_s), float(r_s), float(beta_l), float(r_l), float(r_max))
        rows.append(
            {
                "method": "oster_delta_star",
                "assumption": label,
                "beta_short_M2": round(float(beta_s), 5),
                "beta_long_M3": round(float(beta_l), 5),
                "r_short": round(float(r_s), 4),
                "r_long": round(float(r_l), 4),
                "r_max": round(float(r_max), 4),
                "delta_star": round(float(d), 3),
            }
        )
    # E-value on binary treatment (M3-adjusted standardized diff approximated by coef on treat_bin)
    X, _, jt = design(samp, "treat_bin", CONTROLS + cat_cols, use_firm_fe=True, use_year_fe=True)
    beta_b, _, _ = ols(X, samp["y"].to_numpy())
    smd = float(beta_b[jt]) / samp["y"].std(ddof=0)  # coef in outcome-SD units
    rr, ev = evalue_from_smd(smd)
    rows.append(
        {
            "method": "e_value_approx",
            "assumption": "binary treat, Chinn RR approx",
            "beta_short_M2": np.nan,
            "beta_long_M3": round(float(beta_b[jt]), 5),
            "r_short": np.nan,
            "r_long": np.nan,
            "r_max": round(rr, 3),
            "delta_star": round(ev, 3),
        }
    )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "s6_sensitivity.csv", index=False, encoding="utf-8-sig")
    return df


def main():
    print("S2: building analysis sample ...")
    samp, cat_cols = build_sample()
    print(
        f"  analysis sample n={len(samp)}, firms={samp[COMPANY].nunique()}, "
        f"years={samp['year'].min()}-{samp['year'].max()}, event-type dummies={len(cat_cols)}"
    )

    print("S3: layered fixed-effects coefficient movement ...")
    mv, fits = layered_fe(samp, cat_cols)
    print(mv.to_string(index=False))

    print("\nS4: cluster-robust SE + Wild Cluster Bootstrap ...")
    rb = robust(samp, cat_cols)
    print(rb.to_string(index=False))

    print("\nS5: placebos ...")
    pb = placebos(samp, cat_cols)
    print(pb.to_string(index=False))

    print("\nS6: sensitivity to unobserved confounding ...")
    sens = sensitivity(samp, fits, cat_cols)
    print(sens.to_string(index=False))

    m3 = mv[mv.model == "M3_full_controls"].iloc[0]
    m3_wcb = rb[(rb.spec == "M3") & (rb.treatment == "treat")].iloc[0]
    summary = {
        "n": len(samp),
        "firms": int(samp[COMPANY].nunique()),
        "treatment": TREAT_RAW,
        "outcome": TARGET,
        "naive_coef": float(mv[mv.model == "M0_naive"].treat_coef.iloc[0]),
        "fully_controlled_coef_M3": float(m3.treat_coef),
        "coef_pct_of_naive_M3": float(m3.pct_of_naive),
        "M3_wcb_p": float(m3_wcb.wcb_p),
        "oster_delta_star_Rmax_1.3Rl": float(
            sens[(sens.method == "oster_delta_star") & (sens.assumption == "Rmax=1.3*Rl")].delta_star.iloc[0]
        ),
        "e_value_approx": float(sens[sens.method == "e_value_approx"].delta_star.iloc[0]),
    }
    (OUT / "causal_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote causal artifacts to", OUT)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Interpretability layer for the v3 normalized model.

Only runs once a model actually has out-of-sample signal (v3 test IC ~0.16-0.19);
explaining a zero-signal model would be explaining noise.

Produces (data/processed/modeling/v3_models/explain/):
  permutation_importance.csv   model-agnostic: drop in TEST Spearman IC when each
                               feature is shuffled (avg over repeats). What the tree
                               actually leans on.
  group_ablation_ic.csv        add-one-group: TEST IC of a model trained on each
                               economic feature group alone vs the full set.
  ridge_fe_coefficients.csv    standardized linear (ridge + company FE) coefficients
                               = direction + magnitude of each signal (interpretable
                               companion to the tree).
  robust_inference.csv         fixed-effects OLS on a small a-priori signal set +
                               company & year FE; cluster-robust (by company) SE and
                               Wild Cluster Bootstrap p-values (Rademacher, 9 clusters,
                               restricted null) — the right tool when clusters are few.
  event_waterfall_examples.csv per-event linear contribution decomposition for the
                               10 highest- and 10 lowest-predicted test events:
                               contribution_k = standardized_x_k * coef_k.
  grouped_ic.csv               test IC by year / company / category.

Run from repo root:
  .venv/bin/python market-impact-study/explain_v3_models.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

HERE = Path(__file__).resolve().parent
MODELING = HERE / "data" / "processed" / "modeling"
WIDE = MODELING / "modeling_dataset_enhanced_v3.csv"
SELECTED = MODELING / "v3_models" / "v3_selected.json"
OUT = MODELING / "v3_models" / "explain"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = "relative_mv_return_p0_p20"
COMPANY = "ts_code"
EVENT_DATE = "event_date"
SPLIT = "split"
RNG = np.random.default_rng(0)
WCB_B = 999

# a-priori interpretable signal cluster for robust inference (from the IC diagnostic)
SIGNAL_FEATURES = [
    "mgmt_institution_count_sum_m90",            # pre-event institutional attention (level)
    "mgmt_institution_count_sum_m90__selfz",     # abnormal attention vs own history
    "rel_to_peer_turnover_avg_m20_m1__xsrank",   # relative liquidity (industry rank)
    "rel_to_peer_log_total_mv_pre__xsrank",      # relative size (industry rank)
    "rel_to_peer_ret_m60_m1__xsrank",            # 60d relative reversal (industry rank)
    "volatility_m20_m1",                         # recent volatility
]

GROUP_PREFIX = {
    "management": ("mgmt_",),
    "trading_liquidity": ("turnover_", "amount_", "volume_", "volatility_"),
    "valuation": ("pe_", "pb_", "ps_"),
    "peer_relative": ("rel_to_peer_", "peer_avg_"),
    "financial": ("fin_", "bal_", "cf_", "inc_"),
    "event_text": ("text_", "evt_", "keyword_", "signal_", "source_"),
    "category": ("category_",),
}


def spearman_ic(a, b) -> float:
    m = pd.notna(a) & pd.notna(b)
    if m.sum() < 10 or pd.Series(b[m]).nunique() < 3:
        return float("nan")
    return float(spearmanr(np.asarray(a)[m], np.asarray(b)[m])[0])


def load() -> tuple[pd.DataFrame, list[str]]:
    sel = json.loads(SELECTED.read_text(encoding="utf-8"))
    feats = [f for f in sel["features"]]
    df = pd.read_csv(WIDE, low_memory=False)
    df[EVENT_DATE] = pd.to_datetime(df[EVENT_DATE], errors="coerce")
    df = df[df[TARGET].notna() & df[SPLIT].isin(["train", "valid", "test"])].copy().reset_index(drop=True)
    df["year"] = df[EVENT_DATE].dt.year
    cols = sorted(set(feats) | set(SIGNAL_FEATURES))
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
    return df, feats


def make_design(df, feats, tr_mask):
    med = df.loc[tr_mask, feats].median()
    lo = df.loc[tr_mask, feats].quantile(0.01)
    hi = df.loc[tr_mask, feats].quantile(0.99)
    base = df[feats].clip(lo, hi, axis=1).fillna(med).fillna(0.0)
    mu = base[tr_mask].mean()
    sd = base[tr_mask].std().replace(0, 1.0)
    return base, mu, sd


def main() -> None:
    df, feats = load()
    tr = df[SPLIT] == "train"
    te = df[SPLIT] == "test"
    y = df[TARGET]
    qlo, qhi = y[tr].quantile(0.01), y[tr].quantile(0.99)
    y_fit = y.clip(qlo, qhi)

    base, mu, sd = make_design(df, feats, tr)
    Xtr_tree, Xte_tree = base[tr].to_numpy(), base[te].to_numpy()
    tree = HistGradientBoostingRegressor(learning_rate=0.05, max_depth=3, max_iter=300,
                                         min_samples_leaf=30, l2_regularization=1.0, random_state=0)
    tree.fit(Xtr_tree, y_fit[tr])
    pred_te = tree.predict(Xte_tree)
    base_ic = spearman_ic(y[te].to_numpy(), pred_te)
    print(f"tree test IC (reproduced): {base_ic:.4f}")

    # ---- 1. permutation importance (test IC drop), manual, IC-based ----
    Xte_df = base[te].reset_index(drop=True)
    yte = y[te].to_numpy()
    rows = []
    for j, f in enumerate(feats):
        drops = []
        for _ in range(5):
            Xp = Xte_df.copy()
            Xp[f] = RNG.permutation(Xp[f].to_numpy())
            drops.append(base_ic - spearman_ic(yte, tree.predict(Xp.to_numpy())))
        rows.append({"feature": f, "ic_drop_mean": float(np.mean(drops)), "ic_drop_std": float(np.std(drops))})
    perm = pd.DataFrame(rows).sort_values("ic_drop_mean", ascending=False)
    perm.to_csv(OUT / "permutation_importance.csv", index=False, encoding="utf-8-sig")
    print("\ntop 12 permutation importance (test IC drop):")
    print(perm.head(12).to_string(index=False))

    # ---- 2. group ablation: tree trained on each economic group alone ----
    grp_rows = []
    for gname, prefixes in GROUP_PREFIX.items():
        gfeats = [f for f in feats if f.startswith(prefixes) or f.replace("__xsrank", "").replace("__selfz", "").startswith(prefixes)]
        if not gfeats:
            continue
        gt = HistGradientBoostingRegressor(learning_rate=0.05, max_depth=3, max_iter=300,
                                           min_samples_leaf=30, l2_regularization=1.0, random_state=0)
        gt.fit(base[tr][gfeats].to_numpy(), y_fit[tr])
        gic = spearman_ic(yte, gt.predict(base[te][gfeats].to_numpy()))
        grp_rows.append({"group": gname, "n_features": len(gfeats), "test_ic_group_only": gic})
    grp = pd.DataFrame(grp_rows).sort_values("test_ic_group_only", ascending=False)
    grp.loc[len(grp)] = {"group": "ALL", "n_features": len(feats), "test_ic_group_only": base_ic}
    grp.to_csv(OUT / "group_ablation_ic.csv", index=False, encoding="utf-8-sig")
    print("\ngroup-only test IC:")
    print(grp.to_string(index=False))

    # ---- 3. ridge + company FE standardized coefficients ----
    Xstd = (base - mu) / sd
    comp = pd.get_dummies(df[COMPANY], prefix="fe").astype(float)
    Xlin = pd.concat([Xstd, comp], axis=1)
    ridge = Ridge(alpha=10.0).fit(Xlin[tr.values].to_numpy(), y_fit[tr])
    coef = pd.DataFrame({"feature": Xlin.columns, "coef_std": ridge.coef_})
    coef = coef[~coef.feature.str.startswith("fe_")].copy()
    coef["abs"] = coef.coef_std.abs()
    coef = coef.sort_values("abs", ascending=False).drop(columns="abs")
    coef.to_csv(OUT / "ridge_fe_coefficients.csv", index=False, encoding="utf-8-sig")
    print("\ntop 12 ridge+FE standardized coefficients:")
    print(coef.head(12).to_string(index=False))

    # ---- 4. fixed-effects OLS + cluster-robust SE + Wild Cluster Bootstrap ----
    robust = robust_inference(df, y_fit)
    robust.to_csv(OUT / "robust_inference.csv", index=False, encoding="utf-8-sig")
    print("\nfixed-effects OLS + cluster-robust SE + WCB p (clusters=9 companies):")
    print(robust.to_string(index=False))

    # ---- 5. per-event linear waterfall for extreme test predictions ----
    contrib = Xstd[te].reset_index(drop=True) * ridge.coef_[: len(feats)]
    meta = df[te][["analysis_group_id", COMPANY, EVENT_DATE, "primary_category", "title", TARGET]].reset_index(drop=True)
    meta["y_pred_tree"] = pred_te
    order = np.argsort(pred_te)
    picks = list(order[:10]) + list(order[-10:])
    wf_rows = []
    for i in picks:
        c = contrib.iloc[i]
        top = c.reindex(c.abs().sort_values(ascending=False).index).head(5)
        wf_rows.append({
            **meta.iloc[i].to_dict(),
            "top_contributions": "; ".join(f"{k}={v:+.4f}" for k, v in top.items()),
        })
    pd.DataFrame(wf_rows).to_csv(OUT / "event_waterfall_examples.csv", index=False, encoding="utf-8-sig")

    # ---- 6. grouped IC ----
    gic_rows = []
    tedf = meta.copy()
    for key in ("year_bucket", COMPANY, "primary_category"):
        col = pd.to_datetime(tedf[EVENT_DATE]).dt.year if key == "year_bucket" else tedf[key]
        for val, idx in col.groupby(col).groups.items():
            sub = tedf.loc[idx]
            if len(sub) >= 25:
                gic_rows.append({"dimension": key, "value": str(val), "n": len(sub),
                                 "test_ic": spearman_ic(sub[TARGET].to_numpy(), sub["y_pred_tree"].to_numpy())})
    pd.DataFrame(gic_rows).to_csv(OUT / "grouped_ic.csv", index=False, encoding="utf-8-sig")
    print("\nwrote explain artifacts to", OUT)


def ols(X, yv):
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    return beta, yv - X @ beta


def cluster_vcov(X, resid, clusters):
    XtX_inv = np.linalg.inv(X.T @ X)
    k = X.shape[1]
    meat = np.zeros((k, k))
    uniq = np.unique(clusters)
    for g in uniq:
        Xg = X[clusters == g]
        sg = Xg.T @ resid[clusters == g]
        meat += np.outer(sg, sg)
    G, n = len(uniq), X.shape[0]
    adj = (G / (G - 1)) * ((n - 1) / (n - k))
    return adj * XtX_inv @ meat @ XtX_inv


def robust_inference(df: pd.DataFrame, y_fit: pd.Series) -> pd.DataFrame:
    feats = [f for f in SIGNAL_FEATURES if f in df.columns]
    use = df[feats + [COMPANY, "year"]].copy()
    # standardize signal features (full labeled panel; inference, not OOS)
    Xs = (use[feats] - use[feats].mean()) / use[feats].std(ddof=0)
    Xs = Xs.fillna(0.0)
    comp = pd.get_dummies(use[COMPANY], prefix="c", drop_first=True).astype(float)
    yr = pd.get_dummies(use["year"], prefix="y", drop_first=True).astype(float)
    intercept = pd.Series(1.0, index=use.index, name="const")
    X = pd.concat([intercept, Xs, comp, yr], axis=1)
    cols = list(X.columns)
    Xm = X.to_numpy()
    yv = y_fit.loc[use.index].to_numpy()
    clusters = use[COMPANY].to_numpy()

    beta, resid = ols(Xm, yv)
    V = cluster_vcov(Xm, resid, clusters)
    se = np.sqrt(np.diag(V))

    out = []
    uniq = np.unique(clusters)
    for f in feats:
        j = cols.index(f)
        t_obs = beta[j] / se[j]
        # restricted WCB: impose beta_j = 0 by dropping column j
        keep = [c for c in range(len(cols)) if c != j]
        Xr = Xm[:, keep]
        beta_r, resid_r = ols(Xr, yv)
        fitted_r = Xr @ beta_r
        count = 0
        for _ in range(WCB_B):
            w = RNG.choice([-1.0, 1.0], size=len(uniq))
            wmap = dict(zip(uniq, w))
            wv = np.array([wmap[c] for c in clusters])
            y_star = fitted_r + resid_r * wv
            b_s, r_s = ols(Xm, y_star)
            V_s = cluster_vcov(Xm, r_s, clusters)
            t_s = b_s[j] / np.sqrt(V_s[j, j])
            if abs(t_s) >= abs(t_obs):
                count += 1
        out.append({
            "feature": f,
            "coef": round(float(beta[j]), 5),
            "cluster_robust_se": round(float(se[j]), 5),
            "t_stat": round(float(t_obs), 3),
            "wcb_p_value": round(count / WCB_B, 4),
            "n": int(len(yv)),
            "clusters": int(len(uniq)),
        })
    return pd.DataFrame(out)


if __name__ == "__main__":
    main()

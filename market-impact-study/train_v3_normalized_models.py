"""Retrain on the normalized / industry-relative feature backbone (v3) and test
whether the cross-sectional representation lifts out-of-sample signal IN A MODEL
(not just univariate IC), on the FULL labeled sample.

Design choices (each defensible, no test peeking):
- Sample: ALL labeled rows (target non-null, split in train/valid/test), i.e. the
  full ~3900/620/1620, with overlap intensity carried as features (not filtered to
  the n=300 main subset). This tests the "use 10x more data + overlap flag" lever.
- Target: winsorized at train 1%/99% for FITTING ONLY; evaluated on the true target.
- Feature sets (representation chosen by RULE, never by test IC):
    raw_full              continuous raw levels + flags + overlap
    xsrank                every continuous feature -> its same-quarter cross-sectional
                          rank [0,1]  (the "make different-size firms comparable" thesis)
    xsrank_selfz_mgmt     xsrank + self-vs-own-history z-score of management-attention
                          features (a-priori: "abnormal attention", strongest univariate)
  All sets drop the >95%-missing mirage features (evt_money_*, evt_profit_*,
  evt_percent_max/mean) and keep flags/one-hots/overlap as raw.
- Models: dummy_mean, ridge, ridge_fe (+ company fixed-effect dummies), hist_gbm.
- Primary metric: Spearman IC on test (relative MV reaction is a ranking problem);
  MAE/RMSE/R2/directional accuracy reported alongside; IC also broken out by year.

Outputs (data/processed/modeling/v3_models/):
  v3_metrics.csv            every (feature_set, model, split) row
  v3_ic_by_year.csv         test IC by event year for the selected model
  v3_predictions.csv        per-row y_true/y_pred for the selected model
  v3_selected.json          which (feature_set, model) won on valid IC + its features

Run from repo root:
  .venv/bin/python market-impact-study/train_v3_normalized_models.py
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
REGISTRY = MODELING / "baseline_models" / "baseline_registry.json"
OUT = MODELING / "v3_models"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = "relative_mv_return_p0_p20"
COMPANY = "ts_code"
EVENT_DATE = "event_date"
SPLIT = "split"
SPARSE_DROP_PREFIX = ("evt_money_", "evt_profit_")
SPARSE_DROP_EXACT = {"evt_percent_max_abs", "evt_percent_mean"}
OVERLAP_FEATS = [
    "overlap_event_count_p0_p20",
    "overlap_category_count_p0_p20",
    "is_subject_company",
]


def base_features() -> list[str]:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    return list(reg["features"])


def is_continuous(s: pd.Series) -> bool:
    s = s.dropna()
    return (not s.empty) and s.nunique() > 5


def drop_sparse(feats: list[str]) -> list[str]:
    return [
        f
        for f in feats
        if not f.startswith(SPARSE_DROP_PREFIX) and f not in SPARSE_DROP_EXACT
    ]


def spearman_ic(y_true: pd.Series, y_pred: np.ndarray) -> float:
    m = y_true.notna()
    if m.sum() < 10:
        return float("nan")
    rho, _ = spearmanr(y_true[m], y_pred[m])
    return float(rho)


def directional_acc(y_true: pd.Series, y_pred: np.ndarray) -> float:
    m = y_true.notna()
    return float((np.sign(y_true[m]) == np.sign(y_pred[m])).mean())


def metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    m = y_true.notna()
    yt, yp = y_true[m].to_numpy(), y_pred[m]
    err = yt - yp
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    return {
        "n": int(m.sum()),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        "spearman_ic": spearman_ic(y_true, y_pred),
        "directional_accuracy": directional_acc(y_true, y_pred),
    }


def build_feature_sets(df: pd.DataFrame) -> dict[str, list[str]]:
    base = [f for f in base_features() if f in df.columns]
    cont = [f for f in base if is_continuous(df[f])]
    flags = [f for f in base if f not in cont]
    overlap = [f for f in OVERLAP_FEATS if f in df.columns]

    raw_full = drop_sparse(base) + overlap

    xsrank_cont = []
    for f in cont:
        rk = f"{f}__xsrank"
        xsrank_cont.append(rk if rk in df.columns else f)
    xsrank = drop_sparse(xsrank_cont + flags) + overlap

    mgmt_selfz = [
        f"{f}__selfz"
        for f in cont
        if f.startswith("mgmt_") and f"{f}__selfz" in df.columns
    ]
    xsrank_plus = list(dict.fromkeys(xsrank + mgmt_selfz))

    return {
        "raw_full": list(dict.fromkeys(raw_full)),
        "xsrank": list(dict.fromkeys(xsrank)),
        "xsrank_selfz_mgmt": xsrank_plus,
    }


def prep_matrix(
    frame: pd.DataFrame,
    feats: list[str],
    medians: pd.Series,
    clip_lo: pd.Series,
    clip_hi: pd.Series,
    standardize: tuple[pd.Series, pd.Series] | None,
    company_dummies: pd.DataFrame | None,
) -> np.ndarray:
    X = frame[feats].apply(pd.to_numeric, errors="coerce")
    X = X.clip(lower=clip_lo, upper=clip_hi, axis=1)
    X = X.fillna(medians).fillna(0.0)
    if standardize is not None:
        mu, sd = standardize
        X = (X - mu) / sd
    X = X.fillna(0.0)
    mat = X.to_numpy(dtype=float)
    if company_dummies is not None:
        mat = np.hstack([mat, company_dummies.loc[frame.index].to_numpy(dtype=float)])
    return mat


def main() -> None:
    df = pd.read_csv(WIDE)
    df[EVENT_DATE] = pd.to_datetime(df[EVENT_DATE], errors="coerce")
    df = df[df[TARGET].notna() & df[SPLIT].isin(["train", "valid", "test"])].copy()
    df = df.reset_index(drop=True)
    df["year"] = df[EVENT_DATE].dt.year

    sets = build_feature_sets(df)
    all_feats = sorted({f for fs in sets.values() for f in fs})
    df[all_feats] = df[all_feats].apply(pd.to_numeric, errors="coerce")
    print("sample:", {s: int((df[SPLIT] == s).sum()) for s in ["train", "valid", "test"]})
    for name, fs in sets.items():
        print(f"  feature_set {name}: {len(fs)} features")

    tr = df[SPLIT] == "train"
    va = df[SPLIT] == "valid"
    te = df[SPLIT] == "test"
    y = df[TARGET]
    # winsorize target on train quantiles, FIT only
    qlo, qhi = y[tr].quantile(0.01), y[tr].quantile(0.99)
    y_fit = y.clip(qlo, qhi)

    # company dummies (fixed effects) built from full frame, columns frozen
    comp_dum = pd.get_dummies(df[COMPANY], prefix="fe")

    rows = []
    fitted_store: dict[tuple[str, str], dict] = {}

    for set_name, feats in sets.items():
        medians = df.loc[tr, feats].median(numeric_only=True)
        clip_lo = df.loc[tr, feats].quantile(0.01)
        clip_hi = df.loc[tr, feats].quantile(0.99)
        mu = df.loc[tr, feats].clip(clip_lo, clip_hi, axis=1).fillna(medians).mean()
        sd = df.loc[tr, feats].clip(clip_lo, clip_hi, axis=1).fillna(medians).std().replace(0, 1.0)

        def make_X(mask, standardize, fe):
            return prep_matrix(
                df[mask], feats, medians, clip_lo, clip_hi,
                (mu, sd) if standardize else None,
                comp_dum if fe else None,
            )

        model_specs = [
            ("dummy_mean", None, False, False),
            ("ridge", Ridge(alpha=10.0), True, False),
            ("ridge_fe", Ridge(alpha=10.0), True, True),
            ("hist_gbm", HistGradientBoostingRegressor(
                learning_rate=0.05, max_depth=3, max_iter=300,
                min_samples_leaf=30, l2_regularization=1.0, random_state=0), False, False),
        ]

        for model_name, est, standardize, fe in model_specs:
            masks = {"train": tr, "valid": va, "test": te}
            if model_name == "dummy_mean":
                pred_const = float(y_fit[tr].mean())
                preds = {k: np.full(int(m.sum()), pred_const) for k, m in masks.items()}
                fitted = None
            else:
                Xtr = make_X(tr, standardize, fe)
                fitted = est.fit(Xtr, y_fit[tr])
                preds = {k: fitted.predict(make_X(m, standardize, fe)) for k, m in masks.items()}

            for split_name, mask in masks.items():
                mt = metrics(y[mask], preds[split_name])
                rows.append({"feature_set": set_name, "model_name": model_name,
                             "n_features": len(feats), "split": split_name, **mt})
            fitted_store[(set_name, model_name)] = {
                "fitted": fitted, "feats": feats, "standardize": standardize, "fe": fe,
                "make_X": make_X, "test_pred": preds["test"],
            }

    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(OUT / "v3_metrics.csv", index=False, encoding="utf-8-sig")

    # ---- select model: highest valid Spearman IC among non-dummy ----
    valid_rows = metrics_df[(metrics_df.split == "valid") & (metrics_df.model_name != "dummy_mean")]
    sel = valid_rows.loc[valid_rows.spearman_ic.idxmax()]
    key = (sel.feature_set, sel.model_name)
    store = fitted_store[key]

    # IC by year on test for the selected model
    test_idx = df.index[te]
    yr = df.loc[test_idx, "year"]
    pred_te = pd.Series(store["test_pred"], index=test_idx)
    ic_year = []
    for year, idx in yr.groupby(yr).groups.items():
        ic_year.append({"year": int(year), "n": len(idx),
                        "test_ic": spearman_ic(y.loc[idx], pred_te.loc[idx].to_numpy())})
    pd.DataFrame(ic_year).to_csv(OUT / "v3_ic_by_year.csv", index=False, encoding="utf-8-sig")

    pred_out = df.loc[test_idx, ["analysis_group_id", COMPANY, EVENT_DATE, "primary_category", "title", TARGET]].copy()
    pred_out["y_pred"] = store["test_pred"]
    pred_out.to_csv(OUT / "v3_predictions.csv", index=False, encoding="utf-8-sig")

    (OUT / "v3_selected.json").write_text(json.dumps({
        "selected_feature_set": sel.feature_set,
        "selected_model": sel.model_name,
        "selected_on": "valid_spearman_ic",
        "valid_ic": float(sel.spearman_ic),
        "features": store["feats"],
        "n_features": len(store["feats"]),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- console summary: test IC table (feature_set x model) ----
    piv = metrics_df[metrics_df.split == "test"].pivot(index="feature_set", columns="model_name", values="spearman_ic")
    print("\n=== TEST Spearman IC (feature_set x model) ===")
    print(piv.round(4).to_string())
    print("\n=== selected:", key, "valid IC=%.4f ===" % sel.spearman_ic)
    sel_test = metrics_df[(metrics_df.feature_set == sel.feature_set) & (metrics_df.model_name == sel.model_name) & (metrics_df.split == "test")].iloc[0]
    print("selected TEST: n=%d mae=%.4f r2=%.4f IC=%.4f dir_acc=%.4f" % (
        sel_test.n, sel_test.mae, sel_test.r2, sel_test.spearman_ic, sel_test.directional_accuracy))
    print("\nTest IC by year:")
    print(pd.DataFrame(ic_year).round(4).to_string(index=False))
    print("\nreference (old): main-only n=300, selected model was dummy_mean, test IC=0.000")


if __name__ == "__main__":
    main()

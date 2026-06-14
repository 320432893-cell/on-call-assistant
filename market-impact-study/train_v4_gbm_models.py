"""v4: the main gradient-boosting models (LightGBM + XGBoost) on the v3 normalized
feature backbone, built for REPRODUCIBILITY and INTERPRETABILITY.

- Reproducible: fixed seeds, early stopping on the held-out valid split (test never
  touched), full registry (params, feature list, library versions, sample sizes,
  metric snapshot) written to disk so the run can be regenerated bit-for-bit.
- Interpretable: native SHAP (TreeExplainer) on the selected model -> global
  importance (mean |SHAP|) and per-event SHAP decomposition for the extreme test
  predictions (a real waterfall, not a linear approximation).
- Honest evaluation: primary metric is test Spearman IC (ranking task); MAE/RMSE/R2/
  directional accuracy + IC-by-year reported alongside; compared to v3 HGB (IC 0.193).

Outputs (data/processed/modeling/v4_models/):
  v4_metrics.csv            (model, split) x metrics for lgbm / xgboost / hgb_ref
  v4_registry.json          full reproducibility registry
  v4_predictions.csv        test y_true / y_pred for the selected model
  v4_ic_by_year.csv         test IC by event year
  shap/shap_importance.csv  global mean|SHAP| ranking
  shap/shap_event_examples.csv  per-event top-SHAP drivers for extreme predictions

Run from repo root:
  .venv/bin/python market-impact-study/train_v4_gbm_models.py
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import lightgbm as lgb
import shap
import sklearn
import xgboost as xgb
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
MODELING = HERE / "data" / "processed" / "modeling"
WIDE = Path(os.environ.get("MIS_WIDE", MODELING / "modeling_dataset_enhanced_v3.csv"))
SELECTED = Path(os.environ.get("MIS_SELECTED", MODELING / "v3_models" / "v3_selected.json"))
OUT = MODELING / os.environ.get("MIS_OUT", "v4_models")
SHAP_DIR = OUT / "shap"
SHAP_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "relative_mv_return_p0_p20"
COMPANY = "ts_code"
EVENT_DATE = "event_date"
SPLIT = "split"
SEED = 0


def spearman_ic(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 10 or pd.Series(b[m]).nunique() < 3:
        return float("nan")
    return float(spearmanr(a[m], b[m])[0])


def metrics(y_true, y_pred) -> dict[str, float]:
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    m = ~np.isnan(y_true)
    yt, yp = y_true[m], y_pred[m]
    err = yt - yp
    ss_res, ss_tot = float(np.sum(err**2)), float(np.sum((yt - yt.mean()) ** 2))
    return {
        "n": int(m.sum()),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        "spearman_ic": spearman_ic(yt, yp),
        "directional_accuracy": float((np.sign(yt) == np.sign(yp)).mean()),
    }


def main() -> None:
    feats = json.loads(SELECTED.read_text(encoding="utf-8"))["features"]
    df = pd.read_csv(WIDE, low_memory=False)
    df[EVENT_DATE] = pd.to_datetime(df[EVENT_DATE], errors="coerce")
    df = df[df[TARGET].notna() & df[SPLIT].isin(["train", "valid", "test"])].copy().reset_index(drop=True)
    df["year"] = df[EVENT_DATE].dt.year
    feats = [f for f in feats if f in df.columns]
    df[feats] = df[feats].apply(pd.to_numeric, errors="coerce")

    tr, va, te = (df[SPLIT] == s for s in ("train", "valid", "test"))
    tr, va, te = df[SPLIT] == "train", df[SPLIT] == "valid", df[SPLIT] == "test"
    y = df[TARGET]
    qlo, qhi = y[tr].quantile(0.01), y[tr].quantile(0.99)
    y_fit = y.clip(qlo, qhi)

    # trees handle NaN natively; clip extreme feature values on train quantiles for stability
    lo, hi = df.loc[tr, feats].quantile(0.01), df.loc[tr, feats].quantile(0.99)
    X = df[feats].clip(lo, hi, axis=1)
    Xtr, Xva, Xte = X[tr], X[va], X[te]
    ytr, yva = y_fit[tr], y_fit[va]

    lgbm = lgb.LGBMRegressor(
        objective="regression_l1", n_estimators=3000, learning_rate=0.02,
        num_leaves=15, min_child_samples=40, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.7, reg_lambda=5.0, random_state=SEED, n_jobs=-1, verbose=-1,
    )
    lgbm.fit(Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="l1",
             callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(0)])

    xgbr = xgb.XGBRegressor(
        objective="reg:absoluteerror", n_estimators=3000, learning_rate=0.02,
        max_depth=3, min_child_weight=20, subsample=0.8, colsample_bytree=0.7,
        reg_lambda=5.0, random_state=SEED, n_jobs=-1, early_stopping_rounds=80, eval_metric="mae",
    )
    xgbr.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)

    hgb = HistGradientBoostingRegressor(
        learning_rate=0.05, max_depth=3, max_iter=300, min_samples_leaf=30,
        l2_regularization=1.0, random_state=SEED).fit(Xtr.fillna(Xtr.median()), ytr)

    models = {
        "lightgbm": (lgbm, lambda M, A: M.predict(A)),
        "xgboost": (xgbr, lambda M, A: M.predict(A)),
        "hgb_ref": (hgb, lambda M, A: M.predict(A.fillna(Xtr.median()))),
    }

    rows, preds = [], {}
    for name, (mdl, pred_fn) in models.items():
        for sname, mask, Xs in (("train", tr, Xtr), ("valid", va, Xva), ("test", te, Xte)):
            mt = metrics(y[mask], pred_fn(mdl, Xs))
            rows.append({"model_name": name, "split": sname, **mt})
        preds[name] = pred_fn(mdl, Xte)
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(OUT / "v4_metrics.csv", index=False, encoding="utf-8-sig")

    # select by valid IC among lgbm/xgboost
    valid_ic = {n: spearman_ic(y[va], models[n][1](models[n][0], Xva)) for n in ("lightgbm", "xgboost")}
    best = max(valid_ic, key=valid_ic.get)
    best_model = models[best][0]

    test_idx = df.index[te]
    pred_out = df.loc[test_idx, ["analysis_group_id", COMPANY, EVENT_DATE, "primary_category", "title", TARGET]].copy()
    pred_out["y_pred"] = preds[best]
    pred_out.to_csv(OUT / "v4_predictions.csv", index=False, encoding="utf-8-sig")

    yr = df.loc[test_idx, "year"]
    ic_year = [{"year": int(v), "n": len(i), "test_ic": spearman_ic(y.loc[i], pd.Series(preds[best], index=test_idx).loc[i])}
               for v, i in yr.groupby(yr).groups.items()]
    pd.DataFrame(ic_year).to_csv(OUT / "v4_ic_by_year.csv", index=False, encoding="utf-8-sig")

    # ---- SHAP on selected model ----
    explainer = shap.TreeExplainer(best_model)
    sv = explainer.shap_values(Xte)
    shap_imp = pd.DataFrame({"feature": feats, "mean_abs_shap": np.abs(sv).mean(axis=0)}).sort_values("mean_abs_shap", ascending=False)
    shap_imp.to_csv(SHAP_DIR / "shap_importance.csv", index=False, encoding="utf-8-sig")

    sv_df = pd.DataFrame(sv, columns=feats, index=test_idx)
    order = np.argsort(preds[best])
    picks = list(order[:10]) + list(order[-10:])
    ev_rows = []
    for i in picks:
        gi = test_idx[i]
        row = sv_df.loc[gi]
        top = row.reindex(row.abs().sort_values(ascending=False).index).head(5)
        ev_rows.append({
            "analysis_group_id": df.loc[gi, "analysis_group_id"],
            "company": df.loc[gi, COMPANY], "event_date": df.loc[gi, EVENT_DATE],
            "primary_category": df.loc[gi, "primary_category"], "title": df.loc[gi, "title"],
            "y_true": df.loc[gi, TARGET], "y_pred": preds[best][i],
            "top_shap_drivers": "; ".join(f"{k}={v:+.4f}" for k, v in top.items()),
        })
    pd.DataFrame(ev_rows).to_csv(SHAP_DIR / "shap_event_examples.csv", index=False, encoding="utf-8-sig")

    # ---- reproducibility registry ----
    registry = {
        "target": TARGET, "seed": SEED,
        "input_dataset": WIDE.name,
        "feature_set": "v3_xsrank_selfz_mgmt", "n_features": len(feats), "features": feats,
        "sample": {s: int((df[SPLIT] == s).sum()) for s in ("train", "valid", "test")},
        "target_winsor_train_q": [float(qlo), float(qhi)],
        "selected_model": best, "valid_ic": valid_ic,
        "best_iteration": {
            "lightgbm": int(getattr(lgbm, "best_iteration_", -1) or -1),
            "xgboost": int(getattr(xgbr, "best_iteration", -1) or -1),
        },
        "lightgbm_params": lgbm.get_params(),
        "xgboost_params": {k: v for k, v in xgbr.get_params().items() if not callable(v)},
        "versions": {
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "sklearn": sklearn.__version__, "lightgbm": lgb.__version__,
            "xgboost": xgb.__version__, "shap": shap.__version__,
        },
        "test_metrics_selected": metrics_df[(metrics_df.model_name == best) & (metrics_df.split == "test")].iloc[0].to_dict(),
    }
    (OUT / "v4_registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # ---- console summary ----
    print("\n=== v4 metrics (test) ===")
    print(metrics_df[metrics_df.split == "test"].round(4).to_string(index=False))
    print(f"\nselected by valid IC: {best}  (valid IC={valid_ic[best]:.4f})")
    print("v3 HGB reference test IC = 0.193")
    print("\ntest IC by year:")
    print(pd.DataFrame(ic_year).round(4).to_string(index=False))
    print("\ntop 12 SHAP importance:")
    print(shap_imp.head(12).to_string(index=False))


if __name__ == "__main__":
    main()

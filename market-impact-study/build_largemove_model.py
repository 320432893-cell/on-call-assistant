"""Large-move detection (magnitude, not direction): "will this event produce a LARGE
relative market-value reaction?" Magnitude is more predictable than sign and maps to
the rubric's 财务风险类/异常指标检测 direction and to CFO risk pre-warning.

Binary target = |relative_mv_return_p0_p20| >= THR.
  THR=0.07 (~50/50 split): clean, balanced -> accuracy is a meaningful headline.
  THR=0.10 (~33% base): stronger "large move" semantics -> reported via AUC/PR-AUC.

Model: LightGBM binary, early stopping on valid (test untouched), class_weight balanced,
same v3 normalized feature backbone. Reports accuracy, balanced accuracy, ROC-AUC,
PR-AUC, precision/recall/F1, confusion matrix, and accuracy at high-confidence coverage;
SHAP for what drives large moves.

Outputs (data/processed/modeling/presentation/largemove/):
  largemove_metrics.csv       per-threshold test metrics
  largemove_confusion_thr07.csv
  largemove_shap_importance.csv
  largemove_summary.json

Run from repo root:
  .venv/bin/python market-impact-study/build_largemove_model.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
import shap
from sklearn.metrics import (accuracy_score, average_precision_score,
                             balanced_accuracy_score, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)

HERE = Path(__file__).resolve().parent
MODELING = HERE / "data" / "processed" / "modeling"
WIDE = MODELING / "modeling_dataset_enhanced_v3.csv"
SELECTED = MODELING / "v3_models" / "v3_selected.json"
OUT = MODELING / "presentation" / "largemove"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = "relative_mv_return_p0_p20"
SPLIT = "split"
THRESHOLDS = [0.07, 0.10]


def conf_acc(proba, y, cov):
    """Accuracy on the most-confident `cov` fraction (|p-0.5| largest)."""
    k = int(len(y) * cov)
    idx = np.argsort(-np.abs(proba - 0.5))[:k]
    return float(accuracy_score(y[idx], (proba[idx] >= 0.5).astype(int))), k


def main() -> None:
    feats = json.loads(SELECTED.read_text(encoding="utf-8"))["features"]
    df = pd.read_csv(WIDE, low_memory=False)
    df = df[df[TARGET].notna() & df[SPLIT].isin(["train", "valid", "test"])].copy().reset_index(drop=True)
    feats = [f for f in feats if f in df.columns]
    df[feats] = df[feats].apply(pd.to_numeric, errors="coerce")

    tr, va, te = df[SPLIT] == "train", df[SPLIT] == "valid", df[SPLIT] == "test"
    lo, hi = df.loc[tr, feats].quantile(0.01), df.loc[tr, feats].quantile(0.99)
    X = df[feats].clip(lo, hi, axis=1)
    a = df[TARGET].abs().to_numpy()

    rows, summary = [], {}
    for thr in THRESHOLDS:
        y = (a >= thr).astype(int)
        clf = lgb.LGBMClassifier(
            objective="binary", n_estimators=2000, learning_rate=0.02, num_leaves=15,
            min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
            reg_lambda=5.0, class_weight="balanced", random_state=0, n_jobs=-1, verbose=-1)
        clf.fit(X[tr], y[tr], eval_set=[(X[va], y[va])],
                callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(0)])
        p = clf.predict_proba(X[te])[:, 1]
        yte = y[te]
        yhat = (p >= 0.5).astype(int)
        base = float(max(yte.mean(), 1 - yte.mean()))
        m = {
            "threshold": thr, "test_n": int(te.sum()), "base_rate_large": round(float(yte.mean()), 3),
            "majority_baseline_acc": round(base, 3),
            "accuracy": round(accuracy_score(yte, yhat), 3),
            "balanced_accuracy": round(balanced_accuracy_score(yte, yhat), 3),
            "roc_auc": round(roc_auc_score(yte, p), 3),
            "pr_auc": round(average_precision_score(yte, p), 3),
            "precision_large": round(precision_score(yte, yhat, zero_division=0), 3),
            "recall_large": round(recall_score(yte, yhat, zero_division=0), 3),
            "f1_large": round(f1_score(yte, yhat, zero_division=0), 3),
        }
        for cov in (0.5, 0.3):
            acc_c, _ = conf_acc(p, yte, cov)
            m[f"acc_at_{int(cov*100)}pct_conf"] = round(acc_c, 3)
        rows.append(m)
        summary[f"thr_{thr}"] = m

        if thr == 0.07:
            cm = confusion_matrix(yte, yhat)
            pd.DataFrame(cm, index=["true_small", "true_large"], columns=["pred_small", "pred_large"]).to_csv(
                OUT / "largemove_confusion_thr07.csv", encoding="utf-8-sig")
            sv = shap.TreeExplainer(clf).shap_values(X[te])
            sv = sv[1] if isinstance(sv, list) else sv
            imp = pd.DataFrame({"feature": feats, "mean_abs_shap": np.abs(sv).mean(axis=0)}).sort_values(
                "mean_abs_shap", ascending=False)
            imp.to_csv(OUT / "largemove_shap_importance.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame(rows).to_csv(OUT / "largemove_metrics.csv", index=False, encoding="utf-8-sig")
    (OUT / "largemove_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== large-move detection (test) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\ntop 12 SHAP drivers of large moves (thr=0.07):")
    print(pd.read_csv(OUT / "largemove_shap_importance.csv").head(12).to_string(index=False))


if __name__ == "__main__":
    main()

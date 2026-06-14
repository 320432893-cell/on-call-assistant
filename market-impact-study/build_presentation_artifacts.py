"""Interview-legible artifacts on top of the v4 model.

1. Quantile LIFT (the 10-second headline): bucket TEST events by model rank and
   show that higher-ranked events have higher realized relative MV reaction,
   monotonically. Translates "IC 0.22" into "top-fifth events beat bottom-fifth by X".

2. 3-class CLASSIFICATION (the DA-legible framing): discretize the target into
   positive_revaluation / neutral / negative_shock and train a LightGBM classifier
   on the same backbone; report confusion matrix + per-class precision/recall/F1 +
   macro-F1 + PR-AUC for the two actionable classes (esp. negative_shock recall,
   the CFO risk-warning metric).

Outputs (data/processed/modeling/presentation/):
  lift_quantiles.csv                 tercile & quintile lift on test
  classification_report.csv          per-class precision/recall/f1/support + macro
  classification_confusion_matrix.csv
  classification_summary.json        macro-F1, neg-shock recall, PR-AUC, class dist

Run from repo root:
  .venv/bin/python market-impact-study/build_presentation_artifacts.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import (average_precision_score, classification_report,
                             confusion_matrix, f1_score)

HERE = Path(__file__).resolve().parent
MODELING = HERE / "data" / "processed" / "modeling"
WIDE = MODELING / "modeling_dataset_enhanced_v3.csv"
SELECTED = MODELING / "v3_models" / "v3_selected.json"
PREDS = MODELING / "v4_models" / "v4_predictions.csv"
OUT = MODELING / "presentation"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = "relative_mv_return_p0_p20"
SPLIT = "split"
POS_THR, NEG_THR = 0.02, -0.02


def lift_table(pred: pd.DataFrame, q: int, name: str) -> pd.DataFrame:
    d = pred.dropna(subset=["y_true_actual", "y_pred"]).copy()
    d["bucket"] = pd.qcut(d["y_pred"].rank(method="first"), q, labels=list(range(1, q + 1)))
    g = d.groupby("bucket", observed=True).agg(
        n=("y_true_actual", "size"),
        mean_actual=("y_true_actual", "mean"),
        median_actual=("y_true_actual", "median"),
        pos_share=("y_true_actual", lambda s: float((s > 0).mean())),
    ).reset_index()
    g.insert(0, "scheme", name)
    return g


def main() -> None:
    feats = json.loads(SELECTED.read_text(encoding="utf-8"))["features"]
    df = pd.read_csv(WIDE, low_memory=False)
    df = df[df[TARGET].notna() & df[SPLIT].isin(["train", "valid", "test"])].copy().reset_index(drop=True)
    feats = [f for f in feats if f in df.columns]
    df[feats] = df[feats].apply(pd.to_numeric, errors="coerce")

    # ---- 1. quantile lift from saved v4 predictions ----
    pred = pd.read_csv(PREDS)
    pred = pred.rename(columns={TARGET: "y_true_actual"})
    lifts = pd.concat([lift_table(pred, 3, "tercile"), lift_table(pred, 5, "quintile")], ignore_index=True)
    lifts.to_csv(OUT / "lift_quantiles.csv", index=False, encoding="utf-8-sig")
    print("=== quantile lift (test) ===")
    print(lifts.round(4).to_string(index=False))
    for name, q in (("tercile", 3), ("quintile", 5)):
        sub = lifts[lifts.scheme == name]
        top, bot = sub.iloc[-1]["mean_actual"], sub.iloc[0]["mean_actual"]
        mono = bool(sub["mean_actual"].is_monotonic_increasing)
        print(f"  {name}: top-bucket mean {top:+.4f} vs bottom {bot:+.4f}  spread {top-bot:+.4f}  monotonic={mono}")

    # ---- 2. 3-class classification ----
    tr, va, te = (df[SPLIT] == s for s in ("train", "valid", "test"))
    tr, va, te = df[SPLIT] == "train", df[SPLIT] == "valid", df[SPLIT] == "test"

    def to_cls(s):
        return np.where(s >= POS_THR, 2, np.where(s <= NEG_THR, 0, 1))  # 0 neg, 1 neutral, 2 pos

    y = to_cls(df[TARGET].to_numpy())
    lo, hi = df.loc[tr, feats].quantile(0.01), df.loc[tr, feats].quantile(0.99)
    X = df[feats].clip(lo, hi, axis=1)

    clf = lgb.LGBMClassifier(
        objective="multiclass", num_class=3, n_estimators=2000, learning_rate=0.02,
        num_leaves=15, min_child_samples=40, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.7, reg_lambda=5.0, class_weight="balanced",
        random_state=0, n_jobs=-1, verbose=-1)
    clf.fit(X[tr], y[tr], eval_set=[(X[va], y[va])],
            callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(0)])

    proba = clf.predict_proba(X[te])
    yhat = proba.argmax(axis=1)
    yte = y[te]
    labels = ["negative_shock", "neutral", "positive_revaluation"]

    rep = classification_report(yte, yhat, target_names=labels, output_dict=True, zero_division=0)
    rep_df = pd.DataFrame(rep).T.reset_index().rename(columns={"index": "class"})
    rep_df.to_csv(OUT / "classification_report.csv", index=False, encoding="utf-8-sig")

    cm = confusion_matrix(yte, yhat)
    pd.DataFrame(cm, index=[f"true_{l}" for l in labels], columns=[f"pred_{l}" for l in labels]).to_csv(
        OUT / "classification_confusion_matrix.csv", encoding="utf-8-sig")

    summary = {
        "thresholds": {"positive": POS_THR, "negative": NEG_THR},
        "test_n": int(te.sum()),
        "class_distribution_test": {labels[k]: int((yte == k).sum()) for k in range(3)},
        "macro_f1": round(float(f1_score(yte, yhat, average="macro")), 4),
        "negative_shock_recall": round(float(rep["negative_shock"]["recall"]), 4),
        "positive_reval_recall": round(float(rep["positive_revaluation"]["recall"]), 4),
        "pr_auc_negative_shock": round(float(average_precision_score((yte == 0).astype(int), proba[:, 0])), 4),
        "pr_auc_positive_reval": round(float(average_precision_score((yte == 2).astype(int), proba[:, 2])), 4),
    }
    (OUT / "classification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 3-class classification (test) ===")
    print("class distribution:", summary["class_distribution_test"])
    print("confusion matrix (rows=true, cols=pred):")
    print(pd.DataFrame(cm, index=labels, columns=labels).to_string())
    print(f"macro-F1={summary['macro_f1']}  neg_shock recall={summary['negative_shock_recall']} "
          f"(PR-AUC {summary['pr_auc_negative_shock']})  pos_reval recall={summary['positive_reval_recall']} "
          f"(PR-AUC {summary['pr_auc_positive_reval']})")
    # base rates for PR-AUC comparison
    print("PR-AUC baselines (class prevalence): neg=%.3f pos=%.3f" % (
        (yte == 0).mean(), (yte == 2).mean()))


if __name__ == "__main__":
    main()

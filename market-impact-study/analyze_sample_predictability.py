"""诊断事件类别与 clean-only 样本的可预测性。

唯一职责：输出标签分布、类别均值基线和 clean-only 敏感性训练结果。
不做什么：不新增特征；不修改主模型注册表；不把 clean-only 小样本结果作为主模型结论。
允许依赖的层：读取 enhanced v2 建模宽表、特征字典和增强特征 manifest。
谁不应 import：生产训练入口不应依赖本诊断脚本。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import train_baseline_models as baseline

MODELING_DIR = Path("market-impact-study/data/processed/modeling")
OUTPUT_DIR = MODELING_DIR / "sample_diagnostics"
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

CATEGORY_DIAGNOSTICS_PATH = OUTPUT_DIR / "category_label_diagnostics.csv"
CATEGORY_MEAN_BASELINE_PATH = OUTPUT_DIR / "category_mean_baseline_metrics.csv"
CLEAN_ONLY_METRICS_PATH = OUTPUT_DIR / "clean_only_model_metrics.csv"
REPORT_PATH = DOC_REPORTS_DIR / "SAMPLE_PREDICTABILITY_DIAGNOSTICS.md"

TARGET = baseline.TARGET
NEUTRAL_BAND = 0.02
MIN_CATEGORY_TRAIN = 20
MIN_CATEGORY_VALID = 5
MIN_CATEGORY_TEST = 10


def label_bucket(value: object, neutral_band: float = NEUTRAL_BAND) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "missing"
    if number > neutral_band:
        return "positive"
    if number < -neutral_band:
        return "negative"
    return "neutral"


def category_column(dataset: pd.DataFrame) -> str:
    return "reviewed_primary_category" if "reviewed_primary_category" in dataset.columns else "primary_category"


def build_model_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    frame = baseline.build_frame(dataset)
    frame[category_column(frame)] = frame[category_column(frame)].fillna("未知")
    frame[TARGET] = pd.to_numeric(frame[TARGET], errors="coerce")
    frame["label_bucket"] = frame[TARGET].map(label_bucket)
    return frame


def category_label_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    cat_col = category_column(frame)
    rows: list[dict[str, object]] = []
    for category, group in frame.groupby(cat_col, dropna=False):
        values = pd.to_numeric(group[TARGET], errors="coerce").dropna()
        split_counts = group.groupby("split").size()
        bucket_share = group["label_bucket"].value_counts(normalize=True)
        clean_rows = int(group["reviewed_modeling_scope"].eq("clean_sensitivity").sum())
        train_n = int(split_counts.get("train", 0))
        valid_n = int(split_counts.get("valid", 0))
        test_n = int(split_counts.get("test", 0))
        rows.append(
            {
                "category": category,
                "rows": len(group),
                "train_rows": train_n,
                "valid_rows": valid_n,
                "test_rows": test_n,
                "clean_rows": clean_rows,
                "target_mean": float(values.mean()) if not values.empty else np.nan,
                "target_median": float(values.median()) if not values.empty else np.nan,
                "target_std": float(values.std()) if len(values) > 1 else np.nan,
                "target_abs_mean": float(values.abs().mean()) if not values.empty else np.nan,
                "positive_share": float(bucket_share.get("positive", 0.0)),
                "neutral_share": float(bucket_share.get("neutral", 0.0)),
                "negative_share": float(bucket_share.get("negative", 0.0)),
                "category_model_ready": int(
                    train_n >= MIN_CATEGORY_TRAIN and valid_n >= MIN_CATEGORY_VALID and test_n >= MIN_CATEGORY_TEST
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["category_model_ready", "rows"], ascending=[False, False])


def category_mean_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    cat_col = category_column(frame)
    train = frame[frame["split"] == "train"].copy()
    category_means = train.groupby(cat_col)[TARGET].mean()
    global_mean = float(train[TARGET].mean())
    rows: list[dict[str, object]] = []
    for split in ["valid", "test"]:
        subset = frame[frame["split"] == split].copy()
        if subset.empty:
            continue
        y_true = subset[TARGET]
        global_pred = pd.Series(global_mean, index=subset.index)
        category_pred = subset[cat_col].map(category_means).fillna(global_mean)
        rows.append({"baseline": "global_train_mean", "split": split, **baseline.compute_metrics(y_true, global_pred)})
        rows.append({"baseline": "category_train_mean", "split": split, **baseline.compute_metrics(y_true, category_pred)})
    return pd.DataFrame(rows)


def clean_only_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["reviewed_modeling_scope"].eq("clean_sensitivity")].copy()


def clean_only_model_metrics(
    frame: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    specs: list[tuple[str, object, list[dict[str, object]], bool]],
) -> pd.DataFrame:
    clean = clean_only_frame(frame)
    rows = []
    for feature_set_name in ["base_only", baseline.FEATURE_SET_FULL_SAFE]:
        features = feature_sets.get(feature_set_name, [])
        if not features:
            continue
        metrics = baseline.train_ablation_models(clean, {feature_set_name: features}, specs)
        metrics.insert(0, "sample_scope", "clean_sensitivity_only")
        rows.append(metrics)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *rows])


def best_clean_models(clean_metrics: pd.DataFrame) -> pd.DataFrame:
    valid = clean_metrics[clean_metrics["split"] == "valid"].copy()
    if valid.empty:
        return pd.DataFrame()
    best = valid.loc[valid.groupby(["sample_scope", "feature_set"])["mae"].idxmin()].copy()
    test = clean_metrics[clean_metrics["split"] == "test"].copy()
    return best.merge(
        test[["sample_scope", "feature_set", "model_name", "mae", "spearman_ic", "directional_accuracy"]],
        on=["sample_scope", "feature_set", "model_name"],
        how="left",
        suffixes=("_valid", "_test"),
    )


def write_report(
    diagnostics: pd.DataFrame,
    category_baselines: pd.DataFrame,
    clean_metrics: pd.DataFrame,
    frame: pd.DataFrame,
) -> None:
    split_scope_counts = frame.groupby(["split", "reviewed_modeling_scope"]).size().reset_index(name="rows")
    ready_categories = diagnostics[diagnostics["category_model_ready"].eq(1)].copy()
    clean_best = best_clean_models(clean_metrics)
    lines = [
        "# 样本可预测性诊断",
        "",
        "## 结论",
        "",
        f"- reviewed 入模样本 {len(frame)} 条；clean-only 样本 {len(clean_only_frame(frame))} 条。",
        "- clean-only 仅有 train=25、valid=7、test=22，适合作为敏感性分析，不适合作为主模型结论。",
        f"- 满足分类别训练最低样本门槛的类别数：{len(ready_categories)}。",
        "- 类别均值基线用于判断“类别本身是否有稳定解释力”，不是最终模型。",
        "",
        "## 样本范围",
        "",
        markdown_table(split_scope_counts),
        "",
        "## 可单独分析的类别",
        "",
        markdown_table(
            ready_categories[
                [
                    "category",
                    "rows",
                    "train_rows",
                    "valid_rows",
                    "test_rows",
                    "target_mean",
                    "target_std",
                    "positive_share",
                    "negative_share",
                ]
            ]
        )
        if not ready_categories.empty
        else "无",
        "",
        "## 类别均值基线",
        "",
        markdown_table(category_baselines),
        "",
        "## clean-only 敏感性模型",
        "",
        markdown_table(
            clean_best[
                [
                    "sample_scope",
                    "feature_set",
                    "model_name",
                    "feature_count",
                    "mae_valid",
                    "mae_test",
                    "spearman_ic_test",
                    "directional_accuracy_test",
                ]
            ]
        )
        if not clean_best.empty
        else "无",
        "",
        "## 输出产物",
        "",
        "| 产物 | 路径 |",
        "| --- | --- |",
        f"| 类别标签诊断 | `{CATEGORY_DIAGNOSTICS_PATH}` |",
        f"| 类别均值基线 | `{CATEGORY_MEAN_BASELINE_PATH}` |",
        f"| clean-only 模型指标 | `{CLEAN_ONLY_METRICS_PATH}` |",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    dataset = baseline.read_csv(baseline.input_path())
    dictionary = baseline.read_csv(baseline.DICTIONARY_PATH)
    manifest_path = baseline.manifest_path()
    manifest = baseline.read_csv(manifest_path) if manifest_path.exists() else None
    frame = build_model_frame(dataset)
    feature_cols = baseline.feature_columns(frame, dictionary, manifest)
    feature_set_map = baseline.feature_sets(feature_cols, manifest)
    specs = baseline.candidate_specs(*baseline.model_grids())

    diagnostics = category_label_diagnostics(frame)
    category_baselines = category_mean_predictions(frame)
    clean_metrics = clean_only_model_metrics(frame, feature_set_map, specs)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(CATEGORY_DIAGNOSTICS_PATH, index=False, encoding="utf-8-sig")
    category_baselines.to_csv(CATEGORY_MEAN_BASELINE_PATH, index=False, encoding="utf-8-sig")
    clean_metrics.to_csv(CLEAN_ONLY_METRICS_PATH, index=False, encoding="utf-8-sig")
    write_report(diagnostics, category_baselines, clean_metrics, frame)

    sys.stdout.write(
        json.dumps(
            {
                "rows": len(frame),
                "clean_only_rows": len(clean_only_frame(frame)),
                "model_ready_categories": int(diagnostics["category_model_ready"].sum()),
                "category_diagnostics": str(CATEGORY_DIAGNOSTICS_PATH),
                "clean_only_metrics": str(CLEAN_ONLY_METRICS_PATH),
                "report": str(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

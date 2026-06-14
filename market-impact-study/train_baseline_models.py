"""训练第一版基线模型。

唯一职责：基于 reviewed 建模宽表训练回归基线、选择简单非线性模型，并输出指标与预测摘要。
不做什么：不修改 SSOT；不新增特征；不做复杂调参或自动化集成。
允许依赖的层：只读取 reviewed 建模宽表和 ML SSOT 字典。
谁不应 import：业务模型训练脚本不应依赖本入口作为运行时逻辑。
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MODELING_DIR = Path("market-impact-study/data/processed/modeling")
ML_DATASET_DIR = Path("market-impact-study/data/processed/ml_dataset")
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

REVIEWED_INPUT_PATH = MODELING_DIR / "modeling_dataset_reviewed_v1.csv"
ENHANCED_INPUT_PATH = MODELING_DIR / "modeling_dataset_enhanced_v1.csv"
ENHANCED_V2_INPUT_PATH = MODELING_DIR / "modeling_dataset_enhanced_v2.csv"
ENHANCED_MANIFEST_PATH = MODELING_DIR / "enhanced_feature_manifest.csv"
ENHANCED_V2_MANIFEST_PATH = MODELING_DIR / "enhanced_feature_manifest_v2.csv"
DICTIONARY_PATH = ML_DATASET_DIR / "data_dictionary.csv"
OUTPUT_DIR = MODELING_DIR / "baseline_models"
PREDICTION_PATH = OUTPUT_DIR / "baseline_predictions.csv"
METRICS_PATH = OUTPUT_DIR / "baseline_metrics.csv"
REGISTRY_PATH = OUTPUT_DIR / "baseline_registry.json"
ERRORS_PATH = OUTPUT_DIR / "baseline_test_errors_top20.csv"
ABLATION_METRICS_PATH = OUTPUT_DIR / "ablation_metrics.csv"
REPORT_PATH = DOC_REPORTS_DIR / "BASELINE_MODEL_SUMMARY.md"

TARGET = "relative_mv_return_p0_p20"
VALID_SPLITS = ("train", "valid", "test")
MODEL_SELECTION_SPLIT = "valid"
FEATURE_SET_FULL_SAFE = "full_safe"

RAW_SCALE_FEATURES = {
    "bal_total_assets",
    "bal_total_cur_assets",
    "bal_total_cur_liab",
    "bal_total_hldr_eqy_inc_min_int",
    "bal_total_liab",
    "cf_c_cash_equ_end_period",
    "cf_n_cashflow_act",
    "inc_n_income_attr_p",
    "inc_total_revenue",
    "total_mv_pre",
    "circ_mv_pre",
}

FEATURE_SET_GROUPS = {
    "base_only": ("base",),
    "base_plus_trading": ("base", "trading_pre_event"),
    "base_plus_peer_market": ("base", "trading_pre_event", "peer_market"),
    "base_plus_financial_quality": ("base", "financial_quality"),
    "base_plus_management": ("base", "management_rolling"),
    "base_plus_event_intensity": ("base", "event_intensity"),
    FEATURE_SET_FULL_SAFE: (
        "base",
        "trading_pre_event",
        "peer_market",
        "financial_quality",
        "management_rolling",
        "event_intensity",
    ),
}


class QuantileClipper(BaseEstimator, TransformerMixin):
    """Clip columns by train-set quantiles inside an sklearn pipeline."""

    def __init__(self, lower: float = 0.01, upper: float = 0.99) -> None:
        self.lower = lower
        self.upper = upper

    def fit(self, x: object, _y: object | None = None) -> QuantileClipper:
        values = np.asarray(x, dtype=float)
        self.lower_bounds_ = np.nanquantile(values, self.lower, axis=0)
        self.upper_bounds_ = np.nanquantile(values, self.upper, axis=0)
        return self

    def transform(self, x: object) -> np.ndarray:
        values = np.asarray(x, dtype=float)
        return np.clip(values, self.lower_bounds_, self.upper_bounds_)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少输入文件：{path}")
    return pd.read_csv(path)


def input_path() -> Path:
    if ENHANCED_V2_INPUT_PATH.exists():
        return ENHANCED_V2_INPUT_PATH
    return ENHANCED_INPUT_PATH if ENHANCED_INPUT_PATH.exists() else REVIEWED_INPUT_PATH


def manifest_path() -> Path:
    return ENHANCED_V2_MANIFEST_PATH if ENHANCED_V2_MANIFEST_PATH.exists() else ENHANCED_MANIFEST_PATH


def feature_columns(
    dataset: pd.DataFrame,
    dictionary: pd.DataFrame,
    enhanced_manifest: pd.DataFrame | None = None,
) -> list[str]:
    feature_dict = dictionary[dictionary["table"] == "feature_master"].copy()
    feature_dict = feature_dict[~feature_dict["leakage_risk"].isin(["target", "target_or_post_event"])]
    base_features = [
        column
        for column in feature_dict["column"].astype(str).tolist()
        if column in dataset.columns and column not in {"analysis_group_id", "event_date", "as_of_date"}
    ]
    if enhanced_manifest is None or enhanced_manifest.empty:
        return base_features

    enhanced_features = [
        column
        for column in enhanced_manifest[enhanced_manifest["leakage_risk"] == "low"]["feature"].astype(str).tolist()
        if column in dataset.columns and pd.api.types.is_numeric_dtype(dataset[column]) and column not in RAW_SCALE_FEATURES
    ]
    seen: set[str] = set()
    return [column for column in [*base_features, *enhanced_features] if not (column in seen or seen.add(column))]


def model_feature_group(column: str, enhanced_manifest: pd.DataFrame | None) -> str:
    if enhanced_manifest is None or enhanced_manifest.empty:
        return "base"
    manifest = enhanced_manifest.set_index("feature")
    if column not in manifest.index:
        return "base"
    source_group = str(manifest.loc[column, "source_group"])
    if source_group == "management_rolling":
        return source_group
    if source_group == "financial":
        return "financial_quality"
    if source_group == "event_intensity":
        return "event_intensity"
    if column.startswith(("peer_avg_", "rel_to_peer_", "mkt_")):
        return "peer_market"
    if source_group in {"trading_valuation_peer", "other"}:
        return "trading_pre_event"
    return source_group


def feature_sets(feature_cols: list[str], enhanced_manifest: pd.DataFrame | None) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for column in feature_cols:
        grouped.setdefault(model_feature_group(column, enhanced_manifest), []).append(column)
    output = {}
    for feature_set, groups in FEATURE_SET_GROUPS.items():
        columns = []
        for group in groups:
            columns.extend(grouped.get(group, []))
        output[feature_set] = [column for column in feature_cols if column in set(columns)]
    return output


def build_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    frame = dataset[dataset["reviewed_keep_for_training"].eq(1)].copy()
    frame = frame[frame["split"].isin(VALID_SPLITS)].copy()
    frame[TARGET] = pd.to_numeric(frame[TARGET], errors="coerce")
    return frame.dropna(subset=[TARGET])


def safe_spearman(y_true: pd.Series, y_pred: pd.Series) -> float:
    if len(y_true) < 2:
        return float("nan")
    if y_true.nunique(dropna=True) < 2 or y_pred.nunique(dropna=True) < 2:
        return 0.0
    value = spearmanr(y_true, y_pred, nan_policy="omit").correlation
    return float(value) if value is not None else float("nan")


def directional_accuracy(y_true: pd.Series, y_pred: pd.Series) -> float:
    if len(y_true) == 0:
        return float("nan")
    return float((np.sign(y_true.to_numpy()) == np.sign(y_pred.to_numpy())).mean())


def compute_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    return {
        "n": float(len(y_true)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "r2": float(r2_score(y_true, y_pred)),
        "spearman_ic": safe_spearman(y_true, y_pred),
        "directional_accuracy": directional_accuracy(y_true, y_pred),
    }


def make_linear_pipeline(model: object) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("clipper", QuantileClipper(lower=0.01, upper=0.99)),
            ("scaler", StandardScaler()),
            ("model", model),
        ]
    )


def make_tree_pipeline(model: object) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("clipper", QuantileClipper(lower=0.01, upper=0.99)),
            ("model", model),
        ]
    )


def fit_and_score(model_name: str, pipeline: Pipeline, frame: pd.DataFrame, feature_cols: list[str]) -> tuple[Pipeline, pd.DataFrame, dict[str, dict[str, float]], dict[str, object]]:
    X_train = frame[frame["split"] == "train"][feature_cols]
    y_train = frame[frame["split"] == "train"][TARGET]

    fitted = pipeline.fit(X_train, y_train)
    best_model = fitted
    metrics_by_split = {}
    prediction_rows: list[pd.DataFrame] = []
    for split in VALID_SPLITS:
        subset = frame[frame["split"] == split].copy()
        y_true = subset[TARGET]
        y_pred = pd.Series(fitted.predict(subset[feature_cols]), index=subset.index)
        metrics_by_split[split] = compute_metrics(y_true, y_pred)
        prediction_rows.append(
            pd.DataFrame(
                {
                    "analysis_group_id": subset["analysis_group_id"].astype(str),
                    "split": split,
                    "model_name": model_name,
                    "y_true": y_true.to_numpy(),
                    "y_pred": y_pred.to_numpy(),
                    "abs_error": np.abs(y_true.to_numpy() - y_pred.to_numpy()),
                    "primary_category": subset["primary_category"].astype(str).to_numpy(),
                    "company": subset["company"].astype(str).to_numpy(),
                    "symbol": subset["symbol"].astype(str).to_numpy(),
                    "event_date": subset["event_date"].astype(str).to_numpy(),
                    "title": subset["title"].astype(str).to_numpy(),
                }
            )
        )

    params = {
        "model_name": model_name,
        "selected_on": MODEL_SELECTION_SPLIT,
        "feature_count": len(feature_cols),
    }
    return best_model, pd.concat(prediction_rows, ignore_index=True), metrics_by_split, params


def grid_search_linear(
    model_name: str,
    model_factory: Callable[..., object],
    param_grid: list[dict[str, object]],
    frame: pd.DataFrame,
    feature_cols: list[str],
    *,
    use_scaler: bool,
) -> tuple[Pipeline, pd.DataFrame, dict[str, dict[str, float]], dict[str, object]]:
    best = None
    best_valid_mae = float("inf")
    best_result = None
    for params in param_grid:
        model = model_factory(**params)
        pipeline = make_linear_pipeline(model) if use_scaler else make_tree_pipeline(model)
        fitted = pipeline.fit(frame[frame["split"] == "train"][feature_cols], frame[frame["split"] == "train"][TARGET])
        valid_subset = frame[frame["split"] == "valid"]
        valid_pred = fitted.predict(valid_subset[feature_cols])
        valid_mae = mean_absolute_error(valid_subset[TARGET], valid_pred)
        if valid_mae < best_valid_mae:
            best_valid_mae = float(valid_mae)
            best = pipeline
            best_result = params

    assert best is not None
    assert best_result is not None
    fitted, predictions, metrics_by_split, _ = fit_and_score(model_name, best, frame, feature_cols)
    params_summary = {
        "model_name": model_name,
        "selected_on": MODEL_SELECTION_SPLIT,
        "feature_count": len(feature_cols),
        "best_params": best_result,
        "best_valid_mae": best_valid_mae,
    }
    return fitted, predictions, metrics_by_split, params_summary


def model_grids() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    ridge_grid = [{"alpha": alpha} for alpha in [0.1, 1.0, 3.0, 10.0, 30.0, 100.0]]
    elastic_grid = [
        {"alpha": alpha, "l1_ratio": l1_ratio}
        for alpha in [0.0005, 0.001, 0.005, 0.01, 0.05]
        for l1_ratio in [0.1, 0.5, 0.9]
    ]
    tree_grid = [
        {"learning_rate": lr, "max_depth": depth, "max_iter": max_iter, "min_samples_leaf": leaf}
        for lr in [0.03, 0.05]
        for depth in [2, 3]
        for max_iter in [200]
        for leaf in [10, 20]
    ]
    return ridge_grid, elastic_grid, tree_grid


def candidate_specs(
    ridge_grid: list[dict[str, object]],
    elastic_grid: list[dict[str, object]],
    tree_grid: list[dict[str, object]],
) -> list[tuple[str, Callable[..., object], list[dict[str, object]], bool]]:
    return [
        ("dummy_mean", lambda **_: DummyRegressor(strategy="mean"), [{}], False),
        ("ridge", lambda **kwargs: Ridge(random_state=42, **kwargs), ridge_grid, True),
        ("elasticnet", lambda **kwargs: ElasticNet(random_state=42, max_iter=20000, **kwargs), elastic_grid, True),
        (
            "hist_gradient_boosting",
            lambda **kwargs: HistGradientBoostingRegressor(random_state=42, **kwargs),
            tree_grid,
            False,
        ),
    ]


def score_candidate(
    model_name: str,
    model_factory: Callable[..., object],
    grid: list[dict[str, object]],
    frame: pd.DataFrame,
    feature_cols: list[str],
    *,
    use_scaler: bool,
) -> tuple[pd.DataFrame, dict[str, dict[str, float]], dict[str, object]]:
    if model_name == "dummy_mean":
        _, predictions, metrics_by_split, summary = fit_and_score(
            model_name,
            make_tree_pipeline(DummyRegressor(strategy="mean")),
            frame,
            feature_cols,
        )
        return predictions, metrics_by_split, summary

    _, predictions, metrics_by_split, summary = grid_search_linear(
        model_name,
        model_factory,
        grid,
        frame,
        feature_cols,
        use_scaler=use_scaler,
    )
    return predictions, metrics_by_split, summary


def train_primary_models(
    frame: pd.DataFrame,
    feature_cols: list[str],
    specs: list[tuple[str, Callable[..., object], list[dict[str, object]], bool]],
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    result_rows: list[dict[str, object]] = []
    prediction_rows: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []

    for model_name, model_factory, grid, use_scaler in specs:
        predictions, metrics_by_split, summary = score_candidate(
            model_name,
            model_factory,
            grid,
            frame,
            feature_cols,
            use_scaler=use_scaler,
        )
        summaries.append(summary)
        prediction_rows.append(predictions)
        for split, metrics in metrics_by_split.items():
            result_rows.append({"model_name": model_name, "split": split, **metrics})

    return pd.DataFrame(result_rows), pd.concat(prediction_rows, ignore_index=True), summaries


def train_ablation_models(
    frame: pd.DataFrame,
    feature_set_map: dict[str, list[str]],
    specs: list[tuple[str, Callable[..., object], list[dict[str, object]], bool]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for feature_set, selected_features in feature_set_map.items():
        if not selected_features:
            continue
        for model_name, model_factory, grid, use_scaler in specs:
            _, metrics_by_split, _ = score_candidate(
                model_name,
                model_factory,
                grid,
                frame,
                selected_features,
                use_scaler=use_scaler,
            )
            for split, metrics in metrics_by_split.items():
                rows.append(
                    {
                        "feature_set": feature_set,
                        "feature_count": len(selected_features),
                        "model_name": model_name,
                        "split": split,
                        **metrics,
                    }
                )
    return pd.DataFrame(rows)


def build_registry(feature_cols: list[str], model_summaries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "target": TARGET,
        "input_dataset": str(input_path()),
        "selection_split": MODEL_SELECTION_SPLIT,
        "training_splits": list(VALID_SPLITS),
        "feature_count": len(feature_cols),
        "features": feature_cols,
        "excluded_raw_scale_features": sorted(RAW_SCALE_FEATURES),
        "models": model_summaries,
    }


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_report(
    metrics: pd.DataFrame,
    errors: pd.DataFrame,
    ablation_metrics: pd.DataFrame,
    registry: dict[str, object],
    frame: pd.DataFrame,
) -> None:
    valid_metrics = metrics[metrics["split"] == "valid"].copy()
    test_metrics = metrics[metrics["split"] == "test"].copy()
    selected_model = valid_metrics.sort_values("mae").iloc[0]["model_name"]
    selected_test = test_metrics[test_metrics["model_name"] == selected_model].iloc[0]
    split_counts = frame.groupby("split").size().reset_index(name="rows")
    ablation_valid = ablation_metrics[ablation_metrics["split"] == "valid"].copy()
    ablation_best = ablation_valid.loc[ablation_valid.groupby("feature_set")["mae"].idxmin()].copy()
    ablation_test = ablation_metrics[ablation_metrics["split"] == "test"].copy()
    ablation_best = ablation_best.merge(
        ablation_test[["feature_set", "model_name", "mae", "spearman_ic", "directional_accuracy"]],
        on=["feature_set", "model_name"],
        how="left",
        suffixes=("_valid", "_test"),
    )
    ablation_best = ablation_best[
        ["feature_set", "model_name", "feature_count", "mae_valid", "mae_test", "spearman_ic_test", "directional_accuracy_test"]
    ].sort_values("mae_valid")
    lines = [
        "# 第一版基线模型摘要",
        "",
        "## 结论",
        "",
        f"- 已在 reviewed 建模表上训练 {len(test_metrics)} 个候选模型。",
        f"- 按验证集选择的模型：`{selected_model}`，test MAE = {selected_test['mae']:.4f}，Spearman IC = {selected_test['spearman_ic']:.4f}。",
        "- 训练只使用 `reviewed_keep_for_training=1` 的主模型/clean 样本，未引入手工复核字段作为特征。",
        f"- 本次训练入口：`{registry['input_dataset']}`，入模特征 {registry['feature_count']} 个。",
        "- 对线性/树模型均使用训练集 1%/99% 分位数截尾；原始财务规模列默认不入主模型，避免尺度和极端值污染。",
        "",
        "## 数据规模",
        "",
        markdown_table(split_counts),
        "",
        "## 测试集模型对比",
        "",
        markdown_table(test_metrics[["model_name", "n", "mae", "rmse", "r2", "spearman_ic", "directional_accuracy"]]),
        "",
        "## 特征组消融",
        "",
        markdown_table(ablation_best),
        "",
        "## 误差较大的测试样本",
        "",
        markdown_table(errors.head(20)[["model_name", "analysis_group_id", "split", "y_true", "y_pred", "abs_error", "primary_category", "title"]]),
        "",
        "## 模型注册表",
        "",
        "```json",
        json.dumps(registry, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 使用边界",
        "",
        "- 这是一版可解释 baseline，不代表最终最优结果。",
        "- 树模型使用 sklearn 原生实现，不依赖额外安装的 LightGBM/XGBoost。",
        "- 模型选择只看验证集；测试集仅用于最终外推评估。",
        "- 如果后续补充文本 embedding 或更强树模型，需重新做时间外评估。",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    dataset = read_csv(input_path())
    dictionary = read_csv(DICTIONARY_PATH)
    selected_manifest_path = manifest_path()
    enhanced_manifest = read_csv(selected_manifest_path) if selected_manifest_path.exists() else None
    frame = build_frame(dataset)
    feature_cols = feature_columns(frame, dictionary, enhanced_manifest)
    if not feature_cols:
        raise RuntimeError("未找到可用于建模的特征列")

    feature_set_map = feature_sets(feature_cols, enhanced_manifest)
    primary_feature_cols = feature_set_map[FEATURE_SET_FULL_SAFE]
    specs = candidate_specs(*model_grids())
    metrics_frame, predictions_frame, summaries = train_primary_models(frame, primary_feature_cols, specs)
    ablation_frame = train_ablation_models(frame, feature_set_map, specs)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metrics_frame.to_csv(METRICS_PATH, index=False, encoding="utf-8-sig")
    predictions_frame.to_csv(PREDICTION_PATH, index=False, encoding="utf-8-sig")
    ablation_frame.to_csv(ABLATION_METRICS_PATH, index=False, encoding="utf-8-sig")

    test_errors = predictions_frame[predictions_frame["split"] == "test"].copy()
    test_errors = test_errors.sort_values("abs_error", ascending=False).head(20)
    test_errors.to_csv(ERRORS_PATH, index=False, encoding="utf-8-sig")

    registry = build_registry(primary_feature_cols, summaries)
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(metrics_frame, test_errors, ablation_frame, registry, frame)

    chosen = metrics_frame[metrics_frame["split"] == "valid"].sort_values("mae").iloc[0]
    chosen_test = metrics_frame[
        (metrics_frame["split"] == "test") & (metrics_frame["model_name"] == chosen["model_name"])
    ].iloc[0]
    sys.stdout.write(
        json.dumps(
            {
                "rows": len(frame),
                "features": len(primary_feature_cols),
                "best_model_on_valid": chosen["model_name"],
                "best_valid_mae": float(chosen["mae"]),
                "selected_test_mae": float(chosen_test["mae"]),
                "selected_test_ic": float(chosen_test["spearman_ic"]),
                "metrics_path": str(METRICS_PATH),
                "ablation_metrics_path": str(ABLATION_METRICS_PATH),
                "report_path": str(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""校验机器学习 SSOT 建模数据集。

唯一职责：检查 ml_dataset 下主表的键、标签、切分、point-in-time 和特征泄露风险。
不做什么：不生成新特征；不训练模型；不修改上游事件组或行情数据。
允许依赖的层：只读取 market-impact-study/data/processed/ml_dataset。
谁不应 import：模型训练脚本不应依赖本入口脚本的校验实现作为运行时逻辑。
"""
# 职责：检查 ml_dataset 下主表的键、标签、切分、point-in-time 和特征泄露风险。
# 不做什么：不生成新特征；不训练模型；不修改上游事件组或行情数据。
# 允许依赖层：只读取 market-impact-study/data/processed/ml_dataset。
# 谁不应该 import：模型训练脚本不应依赖本入口脚本的校验实现作为运行时逻辑。

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

DATASET_DIR = Path("market-impact-study/data/processed/ml_dataset")
VALIDATION_DIR = DATASET_DIR / "validation"
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

TABLE_FILES = {
    "event_master": DATASET_DIR / "event_master.csv",
    "label_master": DATASET_DIR / "label_master.csv",
    "feature_master": DATASET_DIR / "feature_master.csv",
    "split_master": DATASET_DIR / "split_master.csv",
    "data_dictionary": DATASET_DIR / "data_dictionary.csv",
}

TARGET_LEAKAGE_PATTERN = re.compile(
    r"(car_|actual_mv_|abnormal_mv_|peer_avg_mv_|end_trade_date|window_coverage|relative_mv_return|ret_p0_|ret_m1_)"
)

REQUIRED_COLUMNS = {
    "event_master": ["analysis_group_id", "event_date", "company", "ts_code", "primary_category", "car_status"],
    "label_master": ["analysis_group_id", "relative_mv_return_p0_p20", "relative_mv_reaction_label_p0_p20"],
    "feature_master": ["analysis_group_id", "event_date", "as_of_date"],
    "split_master": ["analysis_group_id", "split", "has_main_label", "is_default_training_candidate"],
    "data_dictionary": ["table", "column", "dtype", "source", "business_meaning", "leakage_risk"],
}


def load_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for name, path in TABLE_FILES.items():
        if not path.exists():
            raise FileNotFoundError(f"缺少 SSOT 表：{path}")
        tables[name] = pd.read_csv(path)
    return tables


def add_check(rows: list[dict[str, object]], name: str, *, passed: bool, detail: str) -> None:
    rows.append({"check": name, "status": "pass" if passed else "fail", "detail": detail})


def validate_required_columns(tables: dict[str, pd.DataFrame], checks: list[dict[str, object]]) -> None:
    for table, columns in REQUIRED_COLUMNS.items():
        missing = [column for column in columns if column not in tables[table].columns]
        add_check(checks, f"{table} 必要字段", passed=not missing, detail=f"missing={missing}")


def validate_primary_keys(tables: dict[str, pd.DataFrame], checks: list[dict[str, object]]) -> None:
    key_sets: dict[str, set[str]] = {}
    for table in ["event_master", "label_master", "feature_master", "split_master"]:
        frame = tables[table]
        duplicated = int(frame["analysis_group_id"].duplicated().sum()) if "analysis_group_id" in frame.columns else -1
        add_check(
            checks, f"{table} 主键唯一", passed=duplicated == 0, detail=f"duplicated={duplicated}, rows={len(frame)}"
        )
        key_sets[table] = set(frame["analysis_group_id"].astype(str)) if "analysis_group_id" in frame.columns else set()

    base = key_sets["event_master"]
    for table in ["label_master", "feature_master", "split_master"]:
        diff = base.symmetric_difference(key_sets[table])
        add_check(checks, f"{table} 与 event_master 键集合一致", passed=not diff, detail=f"symmetric_diff={len(diff)}")


def validate_point_in_time(tables: dict[str, pd.DataFrame], checks: list[dict[str, object]]) -> None:
    features = tables["feature_master"]
    event_dates = pd.to_datetime(features["event_date"], errors="coerce")
    as_of_dates = pd.to_datetime(features["as_of_date"], errors="coerce")
    invalid = int((as_of_dates > event_dates).sum())
    bad_dates = int(event_dates.isna().sum() + as_of_dates.isna().sum())
    add_check(
        checks, "feature_master point-in-time", passed=invalid == 0, detail=f"as_of_date>event_date rows={invalid}"
    )
    add_check(checks, "feature_master 日期可解析", passed=bad_dates == 0, detail=f"bad_date_cells={bad_dates}")


def validate_split_policy(tables: dict[str, pd.DataFrame], checks: list[dict[str, object]]) -> None:
    split = tables["split_master"].copy()
    split["event_dt"] = pd.to_datetime(split["event_date"], errors="coerce")
    valid_values = {"train", "valid", "test", "excluded_unlabeled", "excluded_bad_date"}
    invalid_values = sorted(set(split["split"].astype(str)) - valid_values)
    add_check(checks, "split 取值合法", passed=not invalid_values, detail=f"invalid={invalid_values}")

    leaks = split[
        ((split["split"] == "train") & (split["event_dt"] > pd.Timestamp("2022-12-31")))
        | (
            (split["split"] == "valid")
            & ~split["event_dt"].between(pd.Timestamp("2023-01-01"), pd.Timestamp("2023-12-31"))
        )
        | ((split["split"] == "test") & (split["event_dt"] < pd.Timestamp("2024-01-01")))
    ]
    add_check(checks, "时间切分无穿越", passed=leaks.empty, detail=f"violating_rows={len(leaks)}")

    counts = split.groupby("split", dropna=False).size().to_dict()
    add_check(
        checks,
        "训练/验证/测试均有样本",
        passed=all(counts.get(v, 0) > 0 for v in ["train", "valid", "test"]),
        detail=str(counts),
    )


def validate_label_alignment(tables: dict[str, pd.DataFrame], checks: list[dict[str, object]]) -> None:
    labels = tables["label_master"]
    split = tables["split_master"]
    merged = split.merge(labels[["analysis_group_id", "relative_mv_return_p0_p20"]], on="analysis_group_id", how="left")
    active = merged["split"].isin(["train", "valid", "test"])
    missing_main_label = int(merged.loc[active, "relative_mv_return_p0_p20"].isna().sum())
    add_check(checks, "默认切分样本主标签完整", passed=missing_main_label == 0, detail=f"missing={missing_main_label}")


def validate_feature_leakage(tables: dict[str, pd.DataFrame], checks: list[dict[str, object]]) -> None:
    feature_columns = list(tables["feature_master"].columns)
    allowed = {"analysis_group_id", "event_date", "as_of_date"}
    leakage_columns = [
        column for column in feature_columns if column not in allowed and TARGET_LEAKAGE_PATTERN.search(column)
    ]
    add_check(
        checks, "feature_master 无目标泄露字段", passed=not leakage_columns, detail=f"columns={leakage_columns[:20]}"
    )

    dictionary = tables["data_dictionary"]
    feature_dict = dictionary[dictionary["table"] == "feature_master"]
    high_risk = feature_dict[feature_dict["leakage_risk"].isin(["target", "target_or_post_event"])]
    add_check(checks, "字段字典未将特征标为目标泄露", passed=high_risk.empty, detail=f"rows={len(high_risk)}")


def build_missingness_report(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for table, frame in tables.items():
        if table == "data_dictionary":
            continue
        for column in frame.columns:
            missing = int(frame[column].isna().sum())
            rows.append(
                {
                    "table": table,
                    "column": column,
                    "rows": len(frame),
                    "missing": missing,
                    "missing_rate": missing / len(frame) if len(frame) else 0,
                }
            )
    return pd.DataFrame(rows).sort_values(["table", "missing_rate"], ascending=[True, False])


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *body])


def write_summary(checks: pd.DataFrame, missingness: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> None:
    passed = int((checks["status"] == "pass").sum())
    failed = int((checks["status"] == "fail").sum())
    table_counts = pd.DataFrame(
        [
            {"table": table, "rows": len(frame), "columns": len(frame.columns)}
            for table, frame in tables.items()
            if table != "data_dictionary"
        ]
    )
    top_missing = missingness[missingness["missing"] > 0].head(15)
    lines = [
        "# ML SSOT 校验报告",
        "",
        "## 结论",
        "",
        f"- SSOT 校验：{passed} 项通过，{failed} 项失败。",
        "- 当前校验覆盖主键、表间对齐、时间切分、point-in-time 和目标泄露字段。",
        "",
        "## 主表规模",
        "",
        markdown_table(table_counts),
        "",
        "## 校验明细",
        "",
        markdown_table(checks),
        "",
        "## 缺失率最高字段",
        "",
        markdown_table(top_missing) if not top_missing.empty else "无缺失字段。",
    ]
    DOC_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (DOC_REPORTS_DIR / "ML_SSOT_VALIDATION_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    tables = load_tables()
    checks: list[dict[str, object]] = []
    validate_required_columns(tables, checks)
    validate_primary_keys(tables, checks)
    validate_point_in_time(tables, checks)
    validate_split_policy(tables, checks)
    validate_label_alignment(tables, checks)
    validate_feature_leakage(tables, checks)

    checks_frame = pd.DataFrame(checks)
    missingness = build_missingness_report(tables)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    checks_frame.to_csv(VALIDATION_DIR / "ssot_validation_report.csv", index=False, encoding="utf-8-sig")
    missingness.to_csv(VALIDATION_DIR / "ssot_missingness_report.csv", index=False, encoding="utf-8-sig")
    write_summary(checks_frame, missingness, tables)

    failed = int((checks_frame["status"] == "fail").sum())
    sys.stdout.write(f"ssot_checks_passed={len(checks_frame) - failed} failed={failed}\n")
    sys.stdout.write(checks_frame.to_string(index=False))
    sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

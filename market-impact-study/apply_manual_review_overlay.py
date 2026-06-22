"""应用人工复核数字表，生成 reviewed overlay 和建模宽表。

唯一职责：校验人工填写的数字复核结果，并把结果翻译为可审计字段。
不做什么：不修改 ML SSOT；不训练模型；不把所有人工保留样本强行升入主模型。
允许依赖的层：只读取 data_governance 的人工复核表和 modeling_dataset_v1.csv。
谁不应 import：训练脚本不应 import 本脚本；应直接读取输出的 reviewed 数据集。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

GOVERNANCE_DIR = Path("market-impact-study/data/processed/data_governance")
MODELING_DIR = Path("market-impact-study/data/processed/modeling")
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

INPUT_PATH = GOVERNANCE_DIR / "manual_review_numeric_template_filled.csv"
MODELING_INPUT_PATH = MODELING_DIR / "modeling_dataset_v1.csv"

OVERLAY_OUTPUT_PATH = GOVERNANCE_DIR / "manual_review_overlay_reviewed.csv"
SUMMARY_OUTPUT_PATH = GOVERNANCE_DIR / "manual_review_numeric_summary.csv"
MODELING_OUTPUT_PATH = MODELING_DIR / "modeling_dataset_reviewed_v1.csv"
REPORT_OUTPUT_PATH = DOC_REPORTS_DIR / "MANUAL_REVIEW_SUMMARY.md"

CODE_COLUMNS = ["keep_code", "noise_code", "category_code", "confidence_code", "note_code"]

CATEGORY_MAP = {
    1: "业绩信号",
    2: "资本动作",
    3: "管理层/投关信号",
    4: "产品/技术创新",
    5: "客户/订单",
    6: "政策/行业",
    7: "风险事件",
    8: "交易机制/IPO",
    9: "纯流程/其他",
}

CONFIDENCE_MAP = {
    1: "很确定",
    2: "大致确定",
    3: "不确定，后续需要再看原文",
}

NOTE_MAP = {
    0: "无特殊备注",
    1: "极端标签但事件本身可信",
    2: "同窗多事件，难以单独归因",
    3: "标题像流程公告，但可能包含重大事项",
    4: "建议作为报告案例，不进入模型",
}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少输入文件：{path}")
    return pd.read_csv(path)


def normalize_code_columns(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in [*CODE_COLUMNS, "analysis_group_id"] if column not in frame.columns]
    if missing:
        raise ValueError(f"人工复核表缺少必要字段：{missing}")

    output = frame.copy()
    for column in CODE_COLUMNS:
        output[column] = pd.to_numeric(output[column], errors="coerce")

    bad_rows = output[CODE_COLUMNS].isna().any(axis=1)
    if bad_rows.any():
        ranks = output.loc[bad_rows, "review_rank"].tolist()
        raise ValueError(f"以下 review_rank 的数字字段未填或不可解析：{ranks[:20]}")

    for column in CODE_COLUMNS:
        output[column] = output[column].astype(int)

    allowed = {
        "keep_code": {0, 1},
        "noise_code": {0, 1},
        "category_code": set(CATEGORY_MAP),
        "confidence_code": set(CONFIDENCE_MAP),
        "note_code": set(NOTE_MAP),
    }
    invalid_messages: list[str] = []
    for column, valid_values in allowed.items():
        invalid = sorted(set(output[column]) - valid_values)
        if invalid:
            invalid_messages.append(f"{column} invalid={invalid}")
    if invalid_messages:
        raise ValueError("; ".join(invalid_messages))

    duplicated = output["analysis_group_id"].astype(str).duplicated(keep=False)
    if duplicated.any():
        ids = output.loc[duplicated, "analysis_group_id"].astype(str).unique().tolist()
        raise ValueError(f"人工复核表 analysis_group_id 重复：{ids[:20]}")

    return output


def review_status(row: pd.Series) -> str:
    if int(row["noise_code"]) == 1:
        return "noise"
    if int(row["keep_code"]) == 0:
        return "case_only"
    corrected = CATEGORY_MAP[int(row["category_code"])]
    if corrected != str(row.get("primary_category", "")):
        return "reclassified"
    return "confirmed"


def build_overlay(review: pd.DataFrame) -> pd.DataFrame:
    overlay = review.copy()
    overlay["manual_review_status"] = overlay.apply(review_status, axis=1)
    overlay["manual_keep_for_model"] = overlay["keep_code"].astype(int)
    overlay["manual_is_noise"] = overlay["noise_code"].astype(int)
    overlay["manual_corrected_category"] = overlay["category_code"].map(CATEGORY_MAP)
    overlay["manual_confidence"] = overlay["confidence_code"].map(CONFIDENCE_MAP)
    overlay["manual_note_label"] = overlay["note_code"].map(NOTE_MAP)
    overlay["manual_reviewer"] = "user_numeric_review"
    overlay["manual_review_date"] = "2026-06-14"

    columns = [
        "review_rank",
        "analysis_group_id",
        "company",
        "symbol",
        "event_date",
        "title",
        "primary_category",
        "manual_review_status",
        "manual_keep_for_model",
        "manual_is_noise",
        "manual_corrected_category",
        "manual_confidence",
        "manual_note_label",
        "manual_reviewer",
        "manual_review_date",
        "keep_code",
        "noise_code",
        "category_code",
        "confidence_code",
        "note_code",
        "review_reason",
        "suggested_action",
    ]
    return overlay[[column for column in columns if column in overlay.columns]]


def reviewed_scope(row: pd.Series) -> tuple[str, str]:
    if pd.isna(row.get("manual_keep_for_model")):
        return str(row.get("modeling_scope", "")), "未人工复核，沿用原始样本策略"
    if int(row["manual_is_noise"]) == 1:
        return "case_or_audit_only", "人工复核标记为噪声/流程事件"
    if int(row["manual_keep_for_model"]) == 0:
        return "case_or_audit_only", "人工复核标记为不进入主模型"
    original_scope = str(row.get("modeling_scope", ""))
    if original_scope in {"main", "clean_sensitivity"}:
        return original_scope, "人工确认可保留，沿用原始主模型/clean 策略"
    if original_scope == "robustness_or_case":
        return "robustness_or_case", "人工确认有经济含义，但原始样本仍存在重叠污染"
    if original_scope == "case_or_audit_only":
        return "case_or_audit_only", "人工确认有经济含义，但原始结构性限制不自动解除"
    return original_scope, "人工确认可保留，沿用原始样本策略"


def build_reviewed_modeling_dataset(modeling: pd.DataFrame, overlay: pd.DataFrame) -> pd.DataFrame:
    manual_columns = [
        "analysis_group_id",
        "manual_review_status",
        "manual_keep_for_model",
        "manual_is_noise",
        "manual_corrected_category",
        "manual_confidence",
        "manual_note_label",
        "manual_reviewer",
        "manual_review_date",
    ]
    dataset = modeling.merge(overlay[manual_columns], on="analysis_group_id", how="left")
    dataset["reviewed_primary_category"] = dataset["manual_corrected_category"].fillna(dataset["primary_category"])
    dataset["is_manually_reviewed"] = dataset["manual_review_status"].notna().astype(int)
    decisions = dataset.apply(reviewed_scope, axis=1)
    dataset["reviewed_modeling_scope"] = [item[0] for item in decisions]
    dataset["reviewed_scope_reason"] = [item[1] for item in decisions]
    dataset["reviewed_keep_for_training"] = (
        dataset["reviewed_modeling_scope"].isin(["main", "clean_sensitivity"]).astype(int)
    )
    return dataset


def build_summary(overlay: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    rows.append({"metric": "reviewed_rows", "value": len(overlay)})
    rows.append({"metric": "manual_keep_1", "value": int((overlay["manual_keep_for_model"] == 1).sum())})
    rows.append({"metric": "manual_keep_0", "value": int((overlay["manual_keep_for_model"] == 0).sum())})
    rows.append({"metric": "manual_noise_1", "value": int((overlay["manual_is_noise"] == 1).sum())})
    rows.append({"metric": "manual_noise_0", "value": int((overlay["manual_is_noise"] == 0).sum())})
    rows.append({"metric": "reviewed_training_rows", "value": int(dataset["reviewed_keep_for_training"].sum())})
    for category, count in overlay["manual_corrected_category"].value_counts().sort_index().items():
        rows.append({"metric": f"category::{category}", "value": int(count)})
    for status, count in overlay["manual_review_status"].value_counts().sort_index().items():
        rows.append({"metric": f"status::{status}", "value": int(count)})
    return pd.DataFrame(rows)


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_report(overlay: pd.DataFrame, dataset: pd.DataFrame) -> None:
    category_counts = overlay["manual_corrected_category"].value_counts().sort_index().reset_index(name="events")
    category_counts.columns = ["manual_corrected_category", "events"]
    status_counts = overlay["manual_review_status"].value_counts().sort_index().reset_index(name="events")
    status_counts.columns = ["manual_review_status", "events"]
    scope_counts = dataset.groupby(["reviewed_modeling_scope"], dropna=False).size().reset_index(name="events")
    lines = [
        "# 人工复核应用摘要",
        "",
        "## 结论",
        "",
        f"- 已应用人工数字复核 {len(overlay)} 条。",
        f"- 人工标记可保留事件 {int((overlay['manual_keep_for_model'] == 1).sum())} 条；不进主模型 {int((overlay['manual_keep_for_model'] == 0).sum())} 条。",
        f"- 人工标记噪声/流程事件 {int((overlay['manual_is_noise'] == 1).sum())} 条。",
        "- `keep=1` 只表示人工确认事件有经济含义；是否进入主模型仍受原始样本策略和同窗重叠约束。",
        "",
        "## 输出产物",
        "",
        "| 产物 | 路径 | 用途 |",
        "| --- | --- | --- |",
        f"| reviewed overlay | `{OVERLAY_OUTPUT_PATH}` | 保存人工判断的标准化结果 |",
        f"| reviewed 建模宽表 | `{MODELING_OUTPUT_PATH}` | 后续 baseline/model 优先读取 |",
        f"| 数字复核摘要 | `{SUMMARY_OUTPUT_PATH}` | 机器可读的复核统计 |",
        "",
        "## 复核状态分布",
        "",
        markdown_table(status_counts),
        "",
        "## 修正后类型分布",
        "",
        markdown_table(category_counts),
        "",
        "## reviewed 建模范围分布",
        "",
        markdown_table(scope_counts),
        "",
        "## 使用边界",
        "",
        "- 原始 SSOT 未被修改。",
        "- 人工标为噪声或不保留的事件会降为 `case_or_audit_only`。",
        "- 人工标为保留但原始仍为重污染或结构性排除的事件，不自动升入主模型。",
    ]
    REPORT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    review = normalize_code_columns(read_csv(INPUT_PATH))
    modeling = read_csv(MODELING_INPUT_PATH)
    missing_ids = set(review["analysis_group_id"].astype(str)) - set(modeling["analysis_group_id"].astype(str))
    if missing_ids:
        raise ValueError(f"人工复核 ID 未出现在建模宽表：{sorted(missing_ids)[:20]}")

    overlay = build_overlay(review)
    dataset = build_reviewed_modeling_dataset(modeling, overlay)
    summary = build_summary(overlay, dataset)

    OVERLAY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODELING_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    overlay.to_csv(OVERLAY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    dataset.to_csv(MODELING_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary.to_csv(SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    write_report(overlay, dataset)

    result = {
        "reviewed_rows": len(overlay),
        "manual_keep_1": int((overlay["manual_keep_for_model"] == 1).sum()),
        "manual_keep_0": int((overlay["manual_keep_for_model"] == 0).sum()),
        "manual_noise_1": int((overlay["manual_is_noise"] == 1).sum()),
        "reviewed_training_rows": int(dataset["reviewed_keep_for_training"].sum()),
        "overlay": str(OVERLAY_OUTPUT_PATH),
        "reviewed_modeling_dataset": str(MODELING_OUTPUT_PATH),
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

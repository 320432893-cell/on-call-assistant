"""构建机器学习主线 SSOT 建模数据集。

唯一职责：从已验证的事件组与 ML readiness 诊断表生成事件、标签、特征、切分和字段字典。
不做什么：不重新采集数据；不重算行情 CAR；不训练模型；不把事件后窗口结果写入特征表。
允许依赖的层：只读取 market-impact-study/data/processed 下的稳定处理结果。
谁不应 import：线上服务、交互 dashboard 和模型训练脚本不应反向 import 本入口脚本。
"""
# 职责：从已验证的事件组与 ML readiness 诊断表生成事件、标签、特征、切分和字段字典。
# 不做什么：不重新采集数据；不重算行情 CAR；不训练模型；不把事件后窗口结果写入特征表。
# 允许依赖层：只读取 market-impact-study/data/processed 下的稳定处理结果。
# 谁不应该 import：线上服务、交互 dashboard 和模型训练脚本不应反向 import 本入口脚本。

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROCESSED_DIR = Path("market-impact-study/data/processed")
ML_READINESS_DIR = PROCESSED_DIR / "ml_readiness"
OUTPUT_DIR = PROCESSED_DIR / "ml_dataset"
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

EVENT_GROUPS_PATH = PROCESSED_DIR / "event_analysis_groups_scored.csv"
OVERLAP_PATH = ML_READINESS_DIR / "event_overlap_diagnostics.csv"

TRAIN_END = pd.Timestamp("2022-12-31")
VALID_START = pd.Timestamp("2023-01-01")
VALID_END = pd.Timestamp("2023-12-31")
TEST_START = pd.Timestamp("2024-01-01")

WINDOWS = ("p0_p5", "p0_p20", "p0_p60")

EVENT_COLUMNS = [
    "analysis_group_id",
    "event_id",
    "company",
    "ts_code",
    "symbol",
    "event_date",
    "aligned_trade_date",
    "pre_trade_date",
    "source_type",
    "source_types",
    "primary_category",
    "category_tags",
    "title",
    "summary",
    "group_titles_sample",
    "source_url",
    "pdf_url",
    "local_pdf_path",
    "has_pdf",
    "source_count",
    "group_event_count",
    "group_source_count",
    "group_evidence_count",
    "car_status",
    "is_subject_company",
    "is_peer_event",
    "is_pre_listing",
    "is_ipo_listing_related",
    "is_market_trading_related",
]

SAFE_NUMERIC_FEATURES = [
    "source_count",
    "evidence_count",
    "group_event_count",
    "group_source_count",
    "group_evidence_count",
    "keyword_score_num",
    "source_weight_num",
    "signal_strength_num",
    "has_pdf_num",
    "pre_total_mv_yi",
]

TEXT_DICTIONARIES = {
    "risk": ("风险", "诉讼", "处罚", "减持", "亏损", "下滑", "终止", "异常", "质押", "违约"),
    "growth": ("增长", "提升", "增加", "盈利", "中标", "订单", "合作", "拓展", "海外"),
    "capital": ("回购", "分红", "定增", "增持", "减持", "股权激励", "解禁", "质押"),
    "ir": ("调研", "投资者", "说明会", "互动", "接待", "机构"),
    "tech": ("研发", "专利", "产品", "技术", "AI", "智能", "芯片", "车联网"),
    "order": ("订单", "客户", "中标", "合同", "供应商"),
    "policy": ("政策", "监管", "补贴", "税", "行业"),
    "finance": ("营收", "净利润", "毛利率", "现金流", "业绩", "预告", "快报"),
}

REQUIRED_EVENT_COLUMNS = ["analysis_group_id", "event_date", "company", "ts_code", "primary_category", "car_status"]

KNOWN_DICTIONARY: dict[tuple[str, str], tuple[str, str, str, str]] = {
    ("event_master", "analysis_group_id"): ("string", "event_analysis_groups_scored", "事件组唯一键", "none"),
    ("event_master", "event_date"): ("date", "event_analysis_groups_scored", "事件发生或披露日期", "none"),
    ("event_master", "primary_category"): ("category", "event_analysis_groups_scored", "事件主分类", "low"),
    ("label_master", "relative_mv_return_p0_p20"): (
        "float",
        "event_analysis_groups_scored",
        "主标签：事件后 20 个交易日公司市值收益率减同行平均市值收益率",
        "target",
    ),
    ("label_master", "abnormal_mv_impact_yi_p0_p20"): (
        "float",
        "event_analysis_groups_scored",
        "CFO 展示标签：20 日异常市值影响，单位亿元",
        "target",
    ),
    ("feature_master", "as_of_date"): ("date", "event_master", "特征可用日期，必须不晚于事件日", "none"),
    ("feature_master", "pre_total_mv_yi"): (
        "float",
        "event_analysis_groups_scored",
        "事件前一交易日总市值，单位亿元",
        "low",
    ),
    ("split_master", "split"): ("category", "event_date", "固定时间切分标记", "none"),
}


def read_csv(path: Path, *, dtype: str | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少输入文件：{path}")
    return pd.read_csv(path, dtype=dtype)


def require_columns(frame: pd.DataFrame, columns: list[str], path: Path) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{path} 缺少必要字段：{missing}")


def to_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def bool_text(value: object) -> str:
    if str(value).strip().lower() in {"1", "1.0", "true", "yes"}:
        return "1"
    return "0"


def joined_text(row: pd.Series | dict[str, object]) -> str:
    return " ".join(
        str(row.get(column, "") or "")
        for column in ["title", "summary", "group_titles_sample", "category_tags", "primary_category", "source_type"]
    )


def text_signal_features(text: str) -> dict[str, int]:
    clean = str(text or "")
    features: dict[str, int] = {
        "text_char_len": len(clean),
        "text_digit_count": len(re.findall(r"\d", clean)),
        "text_percent_count": len(re.findall(r"%|％|百分之", clean)),
        "text_money_word_count": len(re.findall(r"亿元|万元|人民币|美元|金额|市值|营收|利润", clean)),
    }
    for name, words in TEXT_DICTIONARIES.items():
        features[f"text_{name}_keyword_count"] = sum(clean.count(word) for word in words)
        features[f"text_has_{name}_keyword"] = int(features[f"text_{name}_keyword_count"] > 0)
    return features


def split_by_event_date(event_date: object, car_status: object = "ok") -> tuple[str, str]:
    if str(car_status) != "ok":
        return "excluded_unlabeled", "CAR 未成功或事件在上市前，保留审计但不进入默认建模"
    event_dt = pd.to_datetime(event_date, errors="coerce")
    if pd.isna(event_dt):
        return "excluded_bad_date", "事件日期无法解析"
    if event_dt <= TRAIN_END:
        return "train", "事件日不晚于 2022-12-31"
    if VALID_START <= event_dt <= VALID_END:
        return "valid", "事件日在 2023 年"
    if event_dt >= TEST_START:
        return "test", "事件日不早于 2024-01-01"
    return "excluded_bad_date", "事件日期未落入固定切分区间"


def relative_reaction_label(value: object, threshold: float = 0.02) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return ""
    if numeric >= threshold:
        return "positive_revaluation"
    if numeric <= -threshold:
        return "negative_shock"
    return "neutral"


def build_event_master(events: pd.DataFrame, overlap: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in EVENT_COLUMNS if column in events.columns]
    event_master = events[columns].copy()

    overlap_columns = [
        "analysis_group_id",
        "capital_action_subtype",
        "capital_action_subtype_hits",
        "overlap_event_count_p0_p5",
        "overlap_event_count_p0_p20",
        "overlap_event_count_p0_p60",
        "overlap_category_count_p0_p20",
        "overlap_categories_p0_p20",
        "is_overlap_clean_p0_p5",
        "is_overlap_clean_p0_p20",
        "is_overlap_clean_p0_p60",
    ]
    if not overlap.empty:
        join_columns = [column for column in overlap_columns if column in overlap.columns]
        event_master = event_master.merge(
            overlap[join_columns].drop_duplicates("analysis_group_id"),
            on="analysis_group_id",
            how="left",
        )

    for column in ["has_pdf", "is_subject_company", "is_peer_event", "is_pre_listing", "is_ipo_listing_related"]:
        if column in event_master.columns:
            event_master[column] = event_master[column].map(bool_text)
    return event_master


def build_label_master(events: pd.DataFrame) -> pd.DataFrame:
    label = events[["analysis_group_id", "event_date", "car_status"]].copy()
    for window in WINDOWS:
        actual_col = f"actual_mv_return_{window}"
        peer_col = f"peer_avg_mv_return_{window}"
        label[f"actual_mv_return_{window}"] = pd.to_numeric(events.get(actual_col), errors="coerce")
        label[f"peer_avg_mv_return_{window}"] = pd.to_numeric(events.get(peer_col), errors="coerce")
        label[f"relative_mv_return_{window}"] = (
            label[f"actual_mv_return_{window}"] - label[f"peer_avg_mv_return_{window}"]
        )
        for source_col in [
            f"car_{window}",
            f"abnormal_mv_impact_yi_{window}",
            f"actual_mv_change_yi_{window}",
            f"window_coverage_{window}",
            f"end_trade_date_{window}",
        ]:
            if source_col in events.columns:
                label[source_col] = events[source_col]

    label["relative_mv_reaction_label_p0_p20"] = label["relative_mv_return_p0_p20"].map(relative_reaction_label)
    return label


def categorical_flags(events: pd.DataFrame, column: str, prefix: str) -> pd.DataFrame:
    if column not in events.columns:
        return pd.DataFrame(index=events.index)
    return pd.get_dummies(events[column].fillna("").astype(str), prefix=prefix, dtype=int)


def source_type_flags(events: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=events.index)
    if "source_types" not in events.columns and "source_type" not in events.columns:
        return result
    values = events.get("source_types", events.get("source_type")).fillna("").astype(str)
    known_sources = sorted({item.strip() for cell in values for item in re.split(r"[|,;，；]", cell) if item.strip()})
    for source in known_sources:
        safe_name = re.sub(r"\W+", "_", source).strip("_").lower()
        result[f"source_has_{safe_name}"] = values.map(lambda text, needle=source: int(needle in text))
    return result


def build_feature_master(events: pd.DataFrame) -> pd.DataFrame:
    feature = events[["analysis_group_id", "event_date"]].copy()
    feature["as_of_date"] = feature["event_date"]

    numeric_source = to_numeric(events, SAFE_NUMERIC_FEATURES)
    for column in SAFE_NUMERIC_FEATURES:
        if column in numeric_source.columns:
            feature[column] = numeric_source[column]

    text_features = pd.DataFrame([text_signal_features(joined_text(row)) for _, row in events.iterrows()])
    feature = pd.concat([feature.reset_index(drop=True), text_features.reset_index(drop=True)], axis=1)
    return pd.concat(
        [
            feature,
            categorical_flags(events, "primary_category", "category"),
            source_type_flags(events),
        ],
        axis=1,
    )


def build_split_master(events: pd.DataFrame, event_master: pd.DataFrame, label_master: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    label_lookup = label_master.set_index("analysis_group_id")["relative_mv_return_p0_p20"]
    event_lookup = event_master.set_index("analysis_group_id")
    for _, row in events.iterrows():
        split, reason = split_by_event_date(row.get("event_date"), row.get("car_status"))
        group_id = row["analysis_group_id"]
        master_row = event_lookup.loc[group_id]
        is_label_ok = pd.notna(label_lookup.get(group_id))
        if split in {"train", "valid", "test"} and not is_label_ok:
            split = "excluded_unlabeled"
            reason = "主标签 relative_mv_return_p0_p20 缺失，保留审计但不进入默认建模"
        is_default_training_candidate = (
            split in {"train", "valid", "test"}
            and is_label_ok
            and bool_text(master_row.get("is_ipo_listing_related", "0")) == "0"
            and bool_text(master_row.get("is_market_trading_related", "0")) == "0"
        )
        is_clean_p0_p20 = bool_text(master_row.get("is_overlap_clean_p0_p20", "0")) == "1"
        rows.append(
            {
                "analysis_group_id": group_id,
                "event_date": row.get("event_date", ""),
                "split": split,
                "split_reason": reason,
                "has_main_label": int(is_label_ok),
                "is_default_training_candidate": int(is_default_training_candidate),
                "is_clean_p0_p20": int(is_clean_p0_p20),
                "default_model_scope": "main_clean"
                if is_default_training_candidate and is_clean_p0_p20
                else "audit_or_aux",
            }
        )
    return pd.DataFrame(rows)


def infer_dtype(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series):
        return "float" if pd.api.types.is_float_dtype(series) else "integer"
    sample = series.dropna().astype(str).head(50)
    date_like = sample.str.match(r"^\d{4}-\d{2}-\d{2}$")
    if not sample.empty and date_like.mean() >= 0.8:
        return "date"
    return "string"


def leakage_risk_for(table: str, column: str) -> str:
    known = KNOWN_DICTIONARY.get((table, column))
    if known:
        return known[3]
    if table == "label_master":
        return "target"
    if re.search(r"car_|actual_mv_|abnormal_mv_|peer_avg_mv_|end_trade_date|window_coverage", column):
        return "target_or_post_event"
    if table == "feature_master":
        return "low"
    return "none"


def business_meaning_for(table: str, column: str) -> str:
    known = KNOWN_DICTIONARY.get((table, column))
    if known:
        return known[2]
    if column.startswith("text_"):
        return "轻量文本信号特征"
    if column.startswith("category_"):
        return "事件类型哑变量"
    if column.startswith("source_has_"):
        return "事件来源哑变量"
    if column.startswith("overlap_") or column.startswith("is_overlap_"):
        return "事件窗口污染诊断字段，不进入默认特征"
    return "由上游 SSOT 派生的建模或审计字段"


def source_for(table: str, column: str) -> str:
    known = KNOWN_DICTIONARY.get((table, column))
    if known:
        return known[1]
    if table == "event_master":
        return "event_analysis_groups_scored / event_overlap_diagnostics"
    if table == "label_master":
        return "event_analysis_groups_scored"
    if table == "feature_master":
        return "event_master / event_analysis_groups_scored"
    if table == "split_master":
        return "event_date / car_status"
    return "generated"


def build_data_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for table, frame in tables.items():
        for column in frame.columns:
            known = KNOWN_DICTIONARY.get((table, column))
            dtype = known[0] if known else infer_dtype(frame[column])
            rows.append(
                {
                    "table": table,
                    "column": column,
                    "dtype": dtype,
                    "source": source_for(table, column),
                    "business_meaning": business_meaning_for(table, column),
                    "leakage_risk": leakage_risk_for(table, column),
                }
            )
    return pd.DataFrame(rows)


def write_schema_contract(tables: dict[str, pd.DataFrame]) -> None:
    contract = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "primary_key": {table: "analysis_group_id" for table in tables if table != "data_dictionary"},
        "split_policy": {
            "train": "<=2022-12-31",
            "valid": "2023-01-01..2023-12-31",
            "test": ">=2024-01-01",
            "excluded": "CAR unsuccessful or bad event date",
        },
        "tables": {
            table: {
                "rows": len(frame),
                "columns": list(frame.columns),
            }
            for table, frame in tables.items()
        },
    }
    (OUTPUT_DIR / "schema_contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_summary(tables: dict[str, pd.DataFrame], split_master: pd.DataFrame) -> None:
    split_counts = split_master.groupby(["split", "default_model_scope"], dropna=False).size().reset_index(name="rows")
    outputs = pd.DataFrame(
        [{"table": table, "rows": len(frame), "columns": len(frame.columns)} for table, frame in tables.items()]
    )
    lines = [
        "# ML SSOT 数据集摘要",
        "",
        "## 结论",
        "",
        "- 已生成事件、标签、特征、时间切分和字段字典五张主表。",
        "- `feature_master` 只保留事件日前或事件披露本身可获得的种子特征；事件后窗口结果只在 `label_master` 或事件诊断字段中出现。",
        "- 默认主标签为 `relative_mv_return_p0_p20`，即 20 个交易日公司市值收益率减同行平均市值收益率。",
        "",
        "## 产物规模",
        "",
        markdown_table(outputs),
        "",
        "## 切分与默认建模范围",
        "",
        markdown_table(split_counts),
        "",
        "## 后续扩展",
        "",
        "- 明天可在不改变样本和标签口径的前提下，追加 point-in-time 财务、估值、交易历史和管理层滚动特征。",
    ]
    DOC_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (DOC_REPORTS_DIR / "ML_SSOT_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    events = read_csv(EVENT_GROUPS_PATH)
    require_columns(events, REQUIRED_EVENT_COLUMNS, EVENT_GROUPS_PATH)
    overlap = read_csv(OVERLAP_PATH) if OVERLAP_PATH.exists() else pd.DataFrame()

    events = events.drop_duplicates("analysis_group_id").reset_index(drop=True)
    event_master = build_event_master(events, overlap)
    label_master = build_label_master(events)
    feature_master = build_feature_master(events)
    split_master = build_split_master(events, event_master, label_master)

    tables = {
        "event_master": event_master,
        "label_master": label_master,
        "feature_master": feature_master,
        "split_master": split_master,
    }
    data_dictionary = build_data_dictionary(tables)
    tables["data_dictionary"] = data_dictionary

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for table, frame in tables.items():
        frame.to_csv(OUTPUT_DIR / f"{table}.csv", index=False, encoding="utf-8-sig")
    write_schema_contract(tables)
    write_summary(tables, split_master)

    sys.stdout.write(
        f"ml_ssot_output={OUTPUT_DIR} rows={len(event_master)} "
        f"features={len(feature_master.columns)} dictionary_rows={len(data_dictionary)}\n"
    )
    sys.stdout.write(split_master["split"].value_counts(dropna=False).to_string())
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

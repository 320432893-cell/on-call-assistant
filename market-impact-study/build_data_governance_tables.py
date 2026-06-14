"""生成样本与标签治理产物。

唯一职责：基于 ML SSOT 输出人工复核队列、标签质量摘要和样本使用策略。
不做什么：不新增显性/隐性特征；不训练模型；不修改 SSOT 主表。
允许依赖的层：只读取 market-impact-study/data/processed/ml_dataset。
谁不应 import：模型训练脚本和 dashboard 不应依赖本入口脚本作为运行时逻辑。
"""
# 职责：基于 ML SSOT 输出人工复核队列、标签质量摘要和样本使用策略。
# 不做什么：不新增显性/隐性特征；不训练模型；不修改 SSOT 主表。
# 允许依赖层：只读取 market-impact-study/data/processed/ml_dataset。
# 谁不应该 import：模型训练脚本和 dashboard 不应依赖本入口脚本作为运行时逻辑。

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ML_DATASET_DIR = Path("market-impact-study/data/processed/ml_dataset")
OUTPUT_DIR = Path("market-impact-study/data/processed/data_governance")
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")
DOCS_DIR = Path("market-impact-study/docs")

MAIN_LABEL = "relative_mv_return_p0_p20"
IMPACT_LABEL = "abnormal_mv_impact_yi_p0_p20"
REVIEW_QUEUE_SIZE = 360

REVIEW_COLUMNS = [
    "review_rank",
    "review_reason",
    "suggested_action",
    "analysis_group_id",
    "company",
    "symbol",
    "event_date",
    "split",
    "default_model_scope",
    "primary_category",
    "capital_action_subtype",
    "source_type",
    "source_types",
    "title",
    "group_titles_sample",
    MAIN_LABEL,
    IMPACT_LABEL,
    "actual_mv_return_p0_p20",
    "peer_avg_mv_return_p0_p20",
    "overlap_event_count_p0_p20",
    "is_overlap_clean_p0_p20",
    "source_count",
    "group_event_count",
    "group_source_count",
    "has_main_label",
    "is_default_training_candidate",
    "manual_keep_for_model",
    "manual_is_noise",
    "manual_corrected_category",
    "manual_notes",
]


def read_table(name: str) -> pd.DataFrame:
    path = ML_DATASET_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"缺少 SSOT 表：{path}")
    return pd.read_csv(path)


def load_governance_base() -> pd.DataFrame:
    event = read_table("event_master")
    label = read_table("label_master")
    split = read_table("split_master")
    base = event.merge(
        label.drop(columns=["event_date", "car_status"], errors="ignore"), on="analysis_group_id", how="left"
    )
    base = base.merge(split.drop(columns=["event_date"], errors="ignore"), on="analysis_group_id", how="left")
    numeric_columns = [
        MAIN_LABEL,
        "relative_mv_return_p0_p5",
        "relative_mv_return_p0_p60",
        IMPACT_LABEL,
        "abnormal_mv_impact_yi_p0_p5",
        "abnormal_mv_impact_yi_p0_p60",
        "actual_mv_return_p0_p20",
        "peer_avg_mv_return_p0_p20",
        "overlap_event_count_p0_p20",
        "source_count",
        "group_event_count",
        "group_source_count",
    ]
    for column in numeric_columns:
        if column in base.columns:
            base[column] = pd.to_numeric(base[column], errors="coerce")
    base["abs_main_label"] = base[MAIN_LABEL].abs()
    base["abs_impact_label"] = base[IMPACT_LABEL].abs()
    return base


def quantile_threshold(series: pd.Series, q: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(q))


def append_reason(current: str, reason: str) -> str:
    if not current:
        return reason
    if reason in current.split("|"):
        return current
    return f"{current}|{reason}"


def suggested_action(row: pd.Series) -> str:
    title_text = f"{row.get('title', '')} {row.get('group_titles_sample', '')}"
    if str(row.get("is_ipo_listing_related", "0")) == "1" or str(row.get("is_market_trading_related", "0")) == "1":
        return "排除默认建模，保留为审计/案例"
    if any(word in title_text for word in ["临时停牌", "交易异常波动", "股票交易异常"]):
        return "排除默认建模，保留为审计/案例"
    if str(row.get("primary_category", "")) == "其他":
        return "优先人工重分类"
    if float(row.get("overlap_event_count_p0_p20") or 0) > 0:
        return "检查同窗事件污染，必要时降为稳健性样本"
    if abs(float(row.get(MAIN_LABEL) or 0)) >= 0.1:
        return "核验极端标签与事件经济含义"
    return "确认事件分类与标题证据"


def build_review_queue(base: pd.DataFrame) -> pd.DataFrame:
    q95_abs = quantile_threshold(base["abs_main_label"], 0.95)
    q90_abs_impact = quantile_threshold(base["abs_impact_label"], 0.90)

    frame = base.copy()
    frame["review_reason"] = ""
    frame.loc[frame[MAIN_LABEL] >= quantile_threshold(frame[MAIN_LABEL], 0.975), "review_reason"] = "top_positive_label"
    frame.loc[frame[MAIN_LABEL] <= quantile_threshold(frame[MAIN_LABEL], 0.025), "review_reason"] = "top_negative_label"

    for condition, reason in [
        (frame["abs_main_label"] >= q95_abs, "extreme_relative_label"),
        (frame["abs_impact_label"] >= q90_abs_impact, "large_mv_impact"),
        (frame["primary_category"].astype(str) == "其他", "category_other"),
        (frame["symbol"].astype(str) == "300590", "subject_company"),
        (frame["overlap_event_count_p0_p20"].fillna(0) > 0, "overlap_dirty_p20"),
        (frame["is_default_training_candidate"].fillna(0).astype(int) == 0, "not_default_training"),
    ]:
        frame.loc[condition, "review_reason"] = frame.loc[condition, "review_reason"].map(
            lambda value, item=reason: append_reason(str(value), item)
        )

    selected = frame[frame["review_reason"].astype(bool)].copy()
    selected["review_priority_score"] = 0.0
    selected["review_priority_score"] += selected["abs_main_label"].rank(pct=True).fillna(0) * 40
    selected["review_priority_score"] += selected["abs_impact_label"].rank(pct=True).fillna(0) * 25
    selected["review_priority_score"] += (selected["primary_category"].astype(str) == "其他").astype(int) * 15
    selected["review_priority_score"] += (selected["symbol"].astype(str) == "300590").astype(int) * 10
    selected["review_priority_score"] += (selected["overlap_event_count_p0_p20"].fillna(0) > 0).astype(int) * 10
    selected["suggested_action"] = selected.apply(suggested_action, axis=1)
    selected["manual_keep_for_model"] = ""
    selected["manual_is_noise"] = ""
    selected["manual_corrected_category"] = ""
    selected["manual_notes"] = ""
    selected = selected.sort_values("review_priority_score", ascending=False).head(REVIEW_QUEUE_SIZE)
    selected = selected.reset_index(drop=True)
    selected["review_rank"] = selected.index + 1
    return selected[[column for column in REVIEW_COLUMNS if column in selected.columns]]


def build_label_distribution(base: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    scopes = {
        "all_events": base.index == base.index,
        "default_training_candidate": base["is_default_training_candidate"].fillna(0).astype(int) == 1,
        "clean_p20": base["is_clean_p0_p20"].fillna(0).astype(int) == 1,
        "subject_company": base["symbol"].astype(str) == "300590",
    }
    label_columns = ["relative_mv_return_p0_p5", MAIN_LABEL, "relative_mv_return_p0_p60", IMPACT_LABEL]
    for scope, mask in scopes.items():
        scoped = base.loc[mask]
        for label in label_columns:
            values = pd.to_numeric(scoped[label], errors="coerce").dropna()
            row: dict[str, object] = {"scope": scope, "label": label, "n": len(values)}
            if values.empty:
                row.update({"mean": None, "std": None, "p01": None, "p05": None, "p50": None, "p95": None, "p99": None})
            else:
                row.update(
                    {
                        "mean": values.mean(),
                        "std": values.std(),
                        "p01": values.quantile(0.01),
                        "p05": values.quantile(0.05),
                        "p50": values.quantile(0.50),
                        "p95": values.quantile(0.95),
                        "p99": values.quantile(0.99),
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def build_category_audit(base: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        base.groupby("primary_category", dropna=False)
        .agg(
            events=("analysis_group_id", "count"),
            default_training_candidates=("is_default_training_candidate", "sum"),
            main_label_n=(MAIN_LABEL, "count"),
            median_relative_mv_return_p20=(MAIN_LABEL, "median"),
            median_abnormal_mv_impact_yi_p20=(IMPACT_LABEL, "median"),
            overlap_dirty_p20=(
                "overlap_event_count_p0_p20",
                lambda x: int((pd.to_numeric(x, errors="coerce") > 0).sum()),
            ),
        )
        .reset_index()
        .sort_values("events", ascending=False)
    )
    grouped["audit_priority"] = grouped.apply(
        lambda row: (
            "高"
            if row["primary_category"] == "其他" or row["overlap_dirty_p20"] / max(row["events"], 1) > 0.8
            else "中"
        ),
        axis=1,
    )
    return grouped


def sample_policy_for(row: pd.Series) -> tuple[str, str]:
    if int(row.get("has_main_label") or 0) == 0:
        return "exclude_from_model", "主标签缺失，只保留审计"
    if str(row.get("is_ipo_listing_related", "0")) == "1" or str(row.get("is_market_trading_related", "0")) == "1":
        return "case_or_audit_only", "IPO/交易机制事件不进入默认模型"
    if int(row.get("is_default_training_candidate") or 0) == 0:
        return "case_or_audit_only", "不满足默认训练候选条件"
    if int(row.get("is_clean_p0_p20") or 0) == 1:
        return "main_clean_sensitivity", "无同公司 20 日窗口重叠，适合稳健性/敏感性检验"
    if float(row.get("overlap_event_count_p0_p20") or 0) <= 2:
        return "main_model_with_overlap_flag", "轻度同窗重叠，主模型可用但需重叠标记控制"
    return "robustness_or_case", "重叠污染较重，建议仅稳健性或案例使用"


def build_sample_policy(base: pd.DataFrame) -> pd.DataFrame:
    policy = base[
        [
            "analysis_group_id",
            "company",
            "symbol",
            "event_date",
            "primary_category",
            "split",
            "default_model_scope",
            "has_main_label",
            "is_default_training_candidate",
            "is_clean_p0_p20",
            "overlap_event_count_p0_p20",
            MAIN_LABEL,
            IMPACT_LABEL,
            "title",
        ]
    ].copy()
    decisions = policy.apply(sample_policy_for, axis=1)
    policy["sample_policy"] = [item[0] for item in decisions]
    policy["policy_reason"] = [item[1] for item in decisions]
    return policy


def build_sample_policy_summary(policy: pd.DataFrame) -> pd.DataFrame:
    return (
        policy.groupby(["sample_policy", "split"], dropna=False)
        .size()
        .reset_index(name="events")
        .sort_values(["sample_policy", "split"])
    )


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_reports(
    review_queue: pd.DataFrame,
    label_distribution: pd.DataFrame,
    category_audit: pd.DataFrame,
    sample_policy_summary: pd.DataFrame,
) -> None:
    DOC_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    top_review_reasons = (
        review_queue["review_reason"].str.get_dummies(sep="|").sum().sort_values(ascending=False).reset_index()
    )
    top_review_reasons.columns = ["reason", "events"]
    main_label = label_distribution[
        (label_distribution["scope"] == "default_training_candidate") & (label_distribution["label"] == MAIN_LABEL)
    ]
    lines = [
        "# 数据治理摘要",
        "",
        "## 结论",
        "",
        f"- 已生成 {len(review_queue)} 条人工复核队列，优先覆盖极端标签、移为自身事件、`其他` 类和同窗重叠事件。",
        "- 已固化样本使用策略：主模型、clean 稳健性、案例/审计、排除样本分开管理。",
        "- 当前不新增显性或隐性特征，只治理样本和标签，降低后续建模与报告返工。",
        "",
        "## 主标签体检",
        "",
        markdown_table(main_label),
        "",
        "## 复核原因分布",
        "",
        markdown_table(top_review_reasons.head(12)),
        "",
        "## 事件类型审计",
        "",
        markdown_table(category_audit.head(12)),
        "",
        "## 样本策略摘要",
        "",
        markdown_table(sample_policy_summary),
    ]
    (DOC_REPORTS_DIR / "DATA_GOVERNANCE_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    policy_lines = [
        "# 样本使用策略",
        "",
        "## 原则",
        "",
        "- 主模型优先服务解释与复现，不承诺预测绝对市值。",
        "- 有主标签、非 IPO/交易机制事件、满足时间切分的样本可进入默认建模候选。",
        "- 同窗重叠不是直接删除理由，但必须分层：主模型可用、clean 稳健性、重污染案例/附录。",
        "- 人工复核只改分类和样本使用建议，不直接改原始 SSOT；修正结果后续应单独落表。",
        "",
        "## 策略定义",
        "",
        "| 策略 | 用途 | 边界 |",
        "| --- | --- | --- |",
        "| `main_model_with_overlap_flag` | 第一版主模型样本 | 有主标签且轻度重叠，模型中需控制/标记污染风险 |",
        "| `main_clean_sensitivity` | 稳健性/敏感性检验 | 20 日窗口无同公司重叠，但样本少，不单独作为主模型 |",
        "| `robustness_or_case` | 稳健性或案例复盘 | 重叠污染较重，不适合直接支撑主结论 |",
        "| `case_or_audit_only` | 报告案例或审计保留 | IPO、交易机制、不满足默认候选等 |",
        "| `exclude_from_model` | 不入模 | 主标签缺失 |",
        "",
        "## 当前样本分布",
        "",
        markdown_table(sample_policy_summary),
        "",
        "## 人工复核入口",
        "",
        "- `data/processed/data_governance/top_event_review_queue.csv` 是优先复核清单。",
        "- 复核字段包括 `manual_keep_for_model`、`manual_is_noise`、`manual_corrected_category`、`manual_notes`。",
    ]
    (DOCS_DIR / "SAMPLE_POLICY.md").write_text("\n".join(policy_lines) + "\n", encoding="utf-8")


def main() -> int:
    base = load_governance_base()
    review_queue = build_review_queue(base)
    label_distribution = build_label_distribution(base)
    category_audit = build_category_audit(base)
    sample_policy = build_sample_policy(base)
    sample_policy_summary = build_sample_policy_summary(sample_policy)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    review_queue.to_csv(OUTPUT_DIR / "top_event_review_queue.csv", index=False, encoding="utf-8-sig")
    label_distribution.to_csv(OUTPUT_DIR / "label_distribution_summary.csv", index=False, encoding="utf-8-sig")
    category_audit.to_csv(OUTPUT_DIR / "category_audit_summary.csv", index=False, encoding="utf-8-sig")
    sample_policy.to_csv(OUTPUT_DIR / "sample_policy_master.csv", index=False, encoding="utf-8-sig")
    sample_policy_summary.to_csv(OUTPUT_DIR / "sample_policy_summary.csv", index=False, encoding="utf-8-sig")
    write_reports(review_queue, label_distribution, category_audit, sample_policy_summary)

    sys.stdout.write(
        f"data_governance_output={OUTPUT_DIR} review_queue={len(review_queue)} "
        f"sample_policy_rows={len(sample_policy)}\n"
    )
    sys.stdout.write(sample_policy_summary.to_string(index=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

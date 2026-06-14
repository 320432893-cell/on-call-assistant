"""生成建模宽表、人工复核模板和数据治理图表。

唯一职责：把已校验的 SSOT 与样本治理结果合并成后续 EDA/建模统一入口，并生成无需额外依赖的 HTML/SVG 图表。
不做什么：不新增显性/隐性特征；不训练模型；不修改人工复核结果。
允许依赖的层：只读取 market-impact-study/data/processed 下的 SSOT 和 data_governance 产物。
谁不应 import：模型训练脚本不应 import 本入口脚本；应直接读取输出的 modeling_dataset_v1.csv。
"""
# 职责：把已校验的 SSOT 与样本治理结果合并成建模入口，并生成 HTML/SVG 图表。
# 不做什么：不新增显性/隐性特征；不训练模型；不修改人工复核结果。
# 允许依赖层：只读取 market-impact-study/data/processed 下的 SSOT 和 data_governance 产物。
# 谁不应该 import：模型训练脚本不应 import 本入口脚本；应直接读取输出的 modeling_dataset_v1.csv。

from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

import pandas as pd

ML_DATASET_DIR = Path("market-impact-study/data/processed/ml_dataset")
GOVERNANCE_DIR = Path("market-impact-study/data/processed/data_governance")
MODELING_DIR = Path("market-impact-study/data/processed/modeling")
FIGURE_DIR = Path("market-impact-study/figures/data_governance")
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

MAIN_LABEL = "relative_mv_return_p0_p20"
MANUAL_REVIEW_TEMPLATE_SIZE = 100


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少输入文件：{path}")
    return pd.read_csv(path)


def load_tables() -> dict[str, pd.DataFrame]:
    return {
        "event": read_csv(ML_DATASET_DIR / "event_master.csv"),
        "label": read_csv(ML_DATASET_DIR / "label_master.csv"),
        "feature": read_csv(ML_DATASET_DIR / "feature_master.csv"),
        "split": read_csv(ML_DATASET_DIR / "split_master.csv"),
        "sample_policy": read_csv(GOVERNANCE_DIR / "sample_policy_master.csv"),
        "review_queue": read_csv(GOVERNANCE_DIR / "top_event_review_queue.csv"),
        "label_distribution": read_csv(GOVERNANCE_DIR / "label_distribution_summary.csv"),
        "category_audit": read_csv(GOVERNANCE_DIR / "category_audit_summary.csv"),
        "sample_policy_summary": read_csv(GOVERNANCE_DIR / "sample_policy_summary.csv"),
    }


def build_modeling_dataset(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    event = tables["event"]
    label = tables["label"].drop(columns=["event_date", "car_status"], errors="ignore")
    feature = tables["feature"].drop(columns=["event_date"], errors="ignore")
    split = tables["split"].drop(columns=["event_date"], errors="ignore")
    sample_policy = tables["sample_policy"][["analysis_group_id", "sample_policy", "policy_reason"]].drop_duplicates(
        "analysis_group_id"
    )

    dataset = event.merge(label, on="analysis_group_id", how="left")
    dataset = dataset.merge(feature, on="analysis_group_id", how="left", suffixes=("", "_feature"))
    dataset = dataset.merge(split, on="analysis_group_id", how="left")
    dataset = dataset.merge(sample_policy, on="analysis_group_id", how="left")
    dataset["modeling_scope"] = dataset["sample_policy"].map(
        {
            "main_model_with_overlap_flag": "main",
            "main_clean_sensitivity": "clean_sensitivity",
            "robustness_or_case": "robustness_or_case",
            "case_or_audit_only": "case_or_audit_only",
            "exclude_from_model": "exclude_from_model",
        }
    )
    return dataset


def build_manual_review_template(review_queue: pd.DataFrame) -> pd.DataFrame:
    template = review_queue.head(MANUAL_REVIEW_TEMPLATE_SIZE).copy()
    for column in ["manual_keep_for_model", "manual_is_noise", "manual_corrected_category", "manual_notes"]:
        if column not in template.columns:
            template[column] = ""
    template["manual_review_status"] = ""
    template["manual_reviewer"] = ""
    template["manual_review_date"] = ""
    template["evidence_to_check"] = template[["title", "group_titles_sample"]].fillna("").agg(" || ".join, axis=1)
    priority_columns = [
        "review_rank",
        "review_reason",
        "suggested_action",
        "manual_review_status",
        "manual_keep_for_model",
        "manual_is_noise",
        "manual_corrected_category",
        "manual_notes",
        "manual_reviewer",
        "manual_review_date",
        "analysis_group_id",
        "company",
        "symbol",
        "event_date",
        "primary_category",
        "title",
        "evidence_to_check",
        MAIN_LABEL,
        "abnormal_mv_impact_yi_p0_p20",
        "overlap_event_count_p0_p20",
        "split",
        "default_model_scope",
    ]
    return template[[column for column in priority_columns if column in template.columns]]


def finite(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def svg_bar_chart(frame: pd.DataFrame, label_col: str, value_col: str, title: str, width: int = 960) -> str:
    data = frame[[label_col, value_col]].copy()
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce").fillna(0)
    data = data.sort_values(value_col, ascending=True)
    row_height = 34
    left = 220
    right = 40
    top = 56
    height = top + len(data) * row_height + 30
    chart_width = width - left - right
    max_value = max(float(data[value_col].max()), 1.0)
    rows: list[str] = []
    for idx, row in enumerate(data.itertuples(index=False)):
        label = str(getattr(row, label_col))
        value = finite(getattr(row, value_col))
        y = top + idx * row_height
        bar_width = max(1, value / max_value * chart_width)
        rows.append(
            f'<text x="{left - 12}" y="{y + 20}" text-anchor="end">{html.escape(label)}</text>'
            f'<rect x="{left}" y="{y + 4}" width="{bar_width:.2f}" height="20" rx="2"></rect>'
            f'<text x="{left + bar_width + 8}" y="{y + 20}">{value:.0f}</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
text {{ font: 14px Arial, "Microsoft YaHei", sans-serif; fill: #222; }}
rect {{ fill: #2f6f8f; }}
.title {{ font-size: 20px; font-weight: 700; }}
</style>
<text class="title" x="24" y="32">{html.escape(title)}</text>
{"".join(rows)}
</svg>
"""


def histogram_bins(values: pd.Series, bins: int = 24) -> pd.DataFrame:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return pd.DataFrame({"bin": [], "count": []})
    lo = float(clean.quantile(0.01))
    hi = float(clean.quantile(0.99))
    if lo == hi:
        lo -= 0.01
        hi += 0.01
    clipped = clean.clip(lo, hi)
    cut = pd.cut(clipped, bins=bins)
    counts = cut.value_counts(sort=False)
    return pd.DataFrame(
        {
            "bin": [f"{interval.left:.2f}..{interval.right:.2f}" for interval in counts.index],
            "count": counts.to_numpy(),
        }
    )


def boxplot_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for category, group in dataset.groupby("primary_category", dropna=False):
        values = pd.to_numeric(group[MAIN_LABEL], errors="coerce").dropna()
        if values.empty:
            continue
        rows.append(
            {
                "primary_category": category,
                "n": len(values),
                "p05": values.quantile(0.05),
                "p25": values.quantile(0.25),
                "p50": values.quantile(0.50),
                "p75": values.quantile(0.75),
                "p95": values.quantile(0.95),
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def svg_boxplot(summary: pd.DataFrame, title: str, width: int = 1080) -> str:
    row_height = 42
    left = 180
    right = 50
    top = 56
    height = top + len(summary) * row_height + 45
    all_values = summary[["p05", "p25", "p50", "p75", "p95"]].to_numpy().ravel()
    lo = min(float(pd.Series(all_values).min()), -0.05)
    hi = max(float(pd.Series(all_values).max()), 0.05)
    span = hi - lo if hi != lo else 1.0
    chart_width = width - left - right

    def x(value: float) -> float:
        return left + (value - lo) / span * chart_width

    rows: list[str] = []
    zero_x = x(0)
    for idx, row in enumerate(summary.itertuples(index=False)):
        y = top + idx * row_height
        label = str(row.primary_category)
        p05 = x(float(row.p05))
        p25 = x(float(row.p25))
        p50 = x(float(row.p50))
        p75 = x(float(row.p75))
        p95 = x(float(row.p95))
        rows.append(
            f'<text x="{left - 12}" y="{y + 23}" text-anchor="end">{html.escape(label)} ({int(row.n)})</text>'
            f'<line x1="{p05:.2f}" y1="{y + 18}" x2="{p95:.2f}" y2="{y + 18}" class="whisker"></line>'
            f'<rect x="{p25:.2f}" y="{y + 7}" width="{max(p75 - p25, 1):.2f}" height="22" class="box"></rect>'
            f'<line x1="{p50:.2f}" y1="{y + 5}" x2="{p50:.2f}" y2="{y + 31}" class="median"></line>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
text {{ font: 14px Arial, "Microsoft YaHei", sans-serif; fill: #222; }}
.title {{ font-size: 20px; font-weight: 700; }}
.axis {{ stroke: #999; stroke-width: 1; }}
.whisker {{ stroke: #2f6f8f; stroke-width: 2; }}
.box {{ fill: #d8ecf3; stroke: #2f6f8f; stroke-width: 1.5; }}
.median {{ stroke: #b23b3b; stroke-width: 2; }}
</style>
<text class="title" x="24" y="32">{html.escape(title)}</text>
<line x1="{zero_x:.2f}" y1="{top - 8}" x2="{zero_x:.2f}" y2="{height - 32}" class="axis"></line>
{"".join(rows)}
<text x="{left}" y="{height - 12}">{lo:.2f}</text>
<text x="{width - right}" y="{height - 12}" text-anchor="end">{hi:.2f}</text>
</svg>
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_figure_assets(tables: dict[str, pd.DataFrame], dataset: pd.DataFrame) -> pd.DataFrame:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figures: list[dict[str, str]] = []

    sample_summary = tables["sample_policy_summary"].copy()
    sample_by_policy = sample_summary.groupby("sample_policy", as_index=False)["events"].sum()
    path = FIGURE_DIR / "sample_policy_distribution.svg"
    write_text(path, svg_bar_chart(sample_by_policy, "sample_policy", "events", "样本策略分布"))
    figures.append(
        {
            "figure_id": "F-DG-01",
            "path": str(path),
            "title": "样本策略分布",
            "data_source": "sample_policy_summary.csv",
            "why": "说明哪些样本进入主模型、稳健性、案例或排除，避免后续训练临时筛样本。",
        }
    )

    review_reason = tables["review_queue"]["review_reason"].str.get_dummies(sep="|").sum().sort_values().reset_index()
    review_reason.columns = ["reason", "events"]
    path = FIGURE_DIR / "review_reason_distribution.svg"
    write_text(path, svg_bar_chart(review_reason, "reason", "events", "人工复核原因分布"))
    figures.append(
        {
            "figure_id": "F-DG-02",
            "path": str(path),
            "title": "人工复核原因分布",
            "data_source": "top_event_review_queue.csv",
            "why": "展示为什么这些事件需要人工复核，支撑事件治理过程。",
        }
    )

    histogram = histogram_bins(dataset[MAIN_LABEL])
    path = FIGURE_DIR / "main_label_histogram.svg"
    write_text(path, svg_bar_chart(histogram, "bin", "count", "20日相对市值反应分布", width=1120))
    figures.append(
        {
            "figure_id": "F-DG-03",
            "path": str(path),
            "title": "20日相对市值反应分布",
            "data_source": "modeling_dataset_v1.csv",
            "why": "检查主标签是否被极端值主导，并为 winsorize/分位数分析提供依据。",
        }
    )

    category = tables["category_audit"].copy().sort_values("events")
    path = FIGURE_DIR / "category_event_count.svg"
    write_text(path, svg_bar_chart(category, "primary_category", "events", "事件类型样本量"))
    figures.append(
        {
            "figure_id": "F-DG-04",
            "path": str(path),
            "title": "事件类型样本量",
            "data_source": "category_audit_summary.csv",
            "why": "展示事件分类结构，突出其他类占比和分类审计必要性。",
        }
    )

    box = boxplot_summary(dataset)
    box.to_csv(FIGURE_DIR / "category_label_boxplot_summary.csv", index=False, encoding="utf-8-sig")
    path = FIGURE_DIR / "category_label_boxplot.svg"
    write_text(path, svg_boxplot(box, "事件类型 x 20日相对市值反应"))
    figures.append(
        {
            "figure_id": "F-DG-05",
            "path": str(path),
            "title": "事件类型 x 20日相对市值反应",
            "data_source": "modeling_dataset_v1.csv",
            "why": "为后续特征工程和报告中的事件类型解释提供直观依据。",
        }
    )

    manifest = pd.DataFrame(figures)
    manifest.to_csv(FIGURE_DIR / "figure_manifest.csv", index=False, encoding="utf-8-sig")
    return manifest


def html_table(frame: pd.DataFrame, max_rows: int = 20) -> str:
    subset = frame.head(max_rows)
    header = "".join(f"<th>{html.escape(str(column))}</th>" for column in subset.columns)
    rows = []
    for _, row in subset.iterrows():
        rows.append("".join(f"<td>{html.escape(str(value))}</td>" for value in row))
    body = "".join(f"<tr>{row}</tr>" for row in rows)
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def write_dashboard(figures: pd.DataFrame, tables: dict[str, pd.DataFrame], dataset: pd.DataFrame) -> Path:
    figure_cards = "\n".join(
        f"""
        <section>
          <h2>{html.escape(row.title)}</h2>
          <p>{html.escape(row.why)}</p>
          <img src="../../../{html.escape(row.path)}" alt="{html.escape(row.title)}" />
        </section>
        """
        for row in figures.itertuples(index=False)
    )
    stats = {
        "modeling_rows": len(dataset),
        "modeling_columns": len(dataset.columns),
        "manual_review_template_rows": MANUAL_REVIEW_TEMPLATE_SIZE,
        "main_model_rows": int((dataset["modeling_scope"] == "main").sum()),
        "clean_sensitivity_rows": int((dataset["modeling_scope"] == "clean_sensitivity").sum()),
    }
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>数据治理与建模入口</title>
  <style>
    body {{ margin: 0; font: 15px Arial, "Microsoft YaHei", sans-serif; color: #202020; background: #f7f8f9; }}
    header {{ padding: 28px 36px; background: #ffffff; border-bottom: 1px solid #dde2e6; }}
    main {{ max-width: 1160px; margin: 0 auto; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric, section {{ background: #ffffff; border: 1px solid #dde2e6; border-radius: 6px; padding: 16px; }}
    .metric strong {{ display: block; font-size: 24px; margin-top: 8px; }}
    img {{ width: 100%; height: auto; border: 1px solid #e4e7ea; background: #fff; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; }}
    th, td {{ border: 1px solid #dde2e6; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef3f5; }}
    code {{ background: #eef3f5; padding: 2px 4px; border-radius: 3px; }}
  </style>
</head>
<body>
  <header>
    <h1>数据治理与建模入口</h1>
    <p>本页只展示样本、标签和建模入口，不包含模型训练结果。目的在于说明后续模型为什么从这些样本和字段开始。</p>
  </header>
  <main>
    <div class="grid">
      {"".join(f'<div class="metric">{html.escape(k)}<strong>{v}</strong></div>' for k, v in stats.items())}
    </div>
    {figure_cards}
    <section>
      <h2>建模宽表字段入口</h2>
      <p>后续 EDA、显性/隐性特征拼接、训练和图表均优先读取 <code>data/processed/modeling/modeling_dataset_v1.csv</code>。</p>
      {html_table(pd.DataFrame({"column": dataset.columns[:80]}), 80)}
    </section>
    <section>
      <h2>复核模板样例</h2>
      <p>人工复核不改原始 SSOT，先填 overlay 模板，再由后续脚本合并。</p>
      {html_table(tables["review_queue"], 10)}
    </section>
  </main>
</body>
</html>
"""
    output = MODELING_DIR / "data_governance_dashboard.html"
    write_text(output, html_text)
    return output


def write_report(dataset: pd.DataFrame, figures: pd.DataFrame, dashboard_path: Path) -> None:
    scope_counts = dataset["modeling_scope"].value_counts(dropna=False).reset_index()
    scope_counts.columns = ["modeling_scope", "rows"]
    lines = [
        "# 建模入口与图表生成报告",
        "",
        "## 为什么今天做这些",
        "",
        "- 不需要人工判断，且后续 EDA、特征工程、建模和报告都会复用。",
        "- 建模宽表减少重复 join，避免不同脚本读不同口径。",
        "- 复核 overlay 模板让人工修正独立于原始 SSOT，保证可追溯。",
        "- SVG/HTML 图表不依赖额外绘图库，当前环境可直接生成和查看。",
        "",
        "## 生成产物",
        "",
        "| 产物 | 路径 | 用途 |",
        "| --- | --- | --- |",
        "| 建模宽表 | `data/processed/modeling/modeling_dataset_v1.csv` | 后续训练、EDA、图表统一入口 |",
        "| 人工复核模板 | `data/processed/data_governance/manual_review_overlay_template.csv` | 前 100 条高优先级事件人工复核 |",
        f"| 数据治理 dashboard | `{dashboard_path}` | 汇总样本、标签和图表 |",
        "| 图表 manifest | `figures/data_governance/figure_manifest.csv` | 报告/PPT 图表索引 |",
        "",
        "## 建模范围分布",
        "",
        scope_counts.to_markdown(index=False),
        "",
        "## 图表清单",
        "",
        figures.to_markdown(index=False),
        "",
        "## 使用边界",
        "",
        "- `modeling_dataset_v1.csv` 是建模入口，不代表所有字段都可直接入模；训练脚本仍需根据特征注册表筛字段。",
        "- 人工复核模板是 overlay，不应覆盖原始 SSOT。",
        "- 当前图表是数据治理图，不是模型效果图；模型效果图要等 baseline 和主模型训练后生成。",
    ]
    write_text(DOC_REPORTS_DIR / "MODELING_ASSETS_SUMMARY.md", "\n".join(lines) + "\n")


def main() -> int:
    tables = load_tables()
    dataset = build_modeling_dataset(tables)
    review_template = build_manual_review_template(tables["review_queue"])

    MODELING_DIR.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(MODELING_DIR / "modeling_dataset_v1.csv", index=False, encoding="utf-8-sig")
    review_template.to_csv(GOVERNANCE_DIR / "manual_review_overlay_template.csv", index=False, encoding="utf-8-sig")

    figures = write_figure_assets(tables, dataset)
    dashboard_path = write_dashboard(figures, tables, dataset)
    write_report(dataset, figures, dashboard_path)

    summary = {
        "modeling_dataset_rows": len(dataset),
        "modeling_dataset_columns": len(dataset.columns),
        "manual_review_template_rows": len(review_template),
        "figures": len(figures),
        "dashboard": str(dashboard_path),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

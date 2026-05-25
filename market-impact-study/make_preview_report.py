"""Build a static HTML preview for the market impact study outputs."""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path("market-impact-study/data/processed")
TOP_DIR = PROCESSED_DIR / "top_events"
OUTPUT_PATH = PROCESSED_DIR / "preview_report.html"

FIELD_LABELS = {
    "status": "计算状态",
    "rows": "数量",
    "event_date": "事件日期",
    "company": "公司",
    "primary_category": "事件类型",
    "title": "事件标题",
    "group_event_count": "同组事件数",
    "pre_total_mv_yi": "事件前市值（亿元）",
    "end_total_mv_yi_p0_p20": "事件后20日市值（亿元）",
    "actual_mv_change_yi_p0_p20": "客观市值变化[0,+20]（亿元）",
    "actual_mv_return_p0_p20": "客观涨跌幅[0,+20]",
    "peer_avg_mv_return_p0_p20": "同期竞品平均涨跌幅",
    "peer_rank_by_mv_return_p0_p20": "同期竞品排名",
    "peer_rank_total_p0_p20": "可比公司数",
    "objective_change_score": "客观变化综合评分",
    "car_m1_p1": "CAR[-1,+1]",
    "car_p0_p5": "CAR[0,+5]",
    "car_p0_p20": "CAR[0,+20]",
    "abnormal_mv_impact_yi_p0_p20": "异常市值影响[0,+20]（亿元）",
    "event_priority_score": "事件综合评分",
    "yiwei_car_p0_p20": "移为同期CAR[0,+20]",
    "yiwei_abnormal_mv_impact_yi_p0_p20": "移为同期异常市值影响（亿元）",
    "peer_learning_score": "竞品关键动作综合评分",
    "peer_key_action_score": "竞品关键动作综合评分",
    "yiwei_actual_mv_change_yi_p0_p20": "移为同期客观市值变化（亿元）",
    "yiwei_actual_mv_return_p0_p20": "移为同期客观涨跌幅",
    "event_count": "事件组数量",
    "avg_actual_mv_return_p0_p20": "平均客观涨跌幅[0,+20]",
    "median_actual_mv_change_yi_p0_p20": "客观市值变化中位数（亿元）",
    "abs_actual_mv_change_yi_p0_p20": "客观市值变化绝对值合计（亿元）",
    "avg_car_p0_p20": "平均CAR[0,+20]",
    "median_impact_yi_p0_p20": "异常市值影响中位数（亿元）",
    "abs_impact_yi_p0_p20": "异常市值影响绝对值合计（亿元）",
}

STATUS_LABELS = {
    "ok": "已计算",
    "pre_listing": "上市前事件，主分析排除",
    "after_price_coverage": "行情尚未覆盖，待更新",
}


def fmt_num(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if pd.isna(value) else escape(str(value))
    return f"{number:.{digits}f}"


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def table_html(df: pd.DataFrame, columns: list[str], limit: int = 20) -> str:
    if df.empty:
        return '<p class="empty">暂无数据</p>'
    use_cols = [column for column in columns if column in df.columns]
    view = df[use_cols].head(limit).copy()
    numeric_cols = {
        "car_m1_p1",
        "car_p0_p5",
        "car_p0_p20",
        "yiwei_car_p0_p20",
        "abnormal_mv_impact_yi_p0_p20",
        "yiwei_abnormal_mv_impact_yi_p0_p20",
        "event_priority_score",
        "peer_learning_score",
        "peer_key_action_score",
        "objective_change_score",
        "pre_total_mv_yi",
        "end_total_mv_yi_p0_p20",
        "actual_mv_change_yi_p0_p20",
        "actual_mv_return_p0_p20",
        "peer_avg_mv_return_p0_p20",
        "peer_rank_by_mv_return_p0_p20",
        "peer_rank_total_p0_p20",
        "yiwei_actual_mv_change_yi_p0_p20",
        "yiwei_actual_mv_return_p0_p20",
        "avg_car_p0_p20",
        "avg_actual_mv_return_p0_p20",
        "median_actual_mv_change_yi_p0_p20",
        "abs_actual_mv_change_yi_p0_p20",
        "median_impact_yi_p0_p20",
        "abs_impact_yi_p0_p20",
    }
    header = "".join(f"<th>{escape(FIELD_LABELS.get(column, column))}</th>" for column in use_cols)
    rows = []
    for _, row in view.iterrows():
        cells = []
        for column in use_cols:
            value = row[column]
            if column == "status":
                value = STATUS_LABELS.get(str(value), value)
            text = fmt_num(value) if column in numeric_cols else escape(str(value))
            cells.append(f"<td>{text}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def write_chinese_csv(df: pd.DataFrame, filename: str, columns: list[str]) -> None:
    if df.empty:
        return
    use_cols = [column for column in columns if column in df.columns]
    output = df[use_cols].copy()
    if "status" in output.columns:
        output["status"] = output["status"].map(lambda value: STATUS_LABELS.get(str(value), value))
    output = output.rename(columns={column: FIELD_LABELS.get(column, column) for column in use_cols})
    output.to_csv(PROCESSED_DIR / filename, index=False, encoding="utf-8-sig")


def bar_chart_html(df: pd.DataFrame) -> str:
    if df.empty or "primary_category" not in df or "abs_impact_yi_p0_p20" not in df:
        return '<p class="empty">暂无分类汇总</p>'
    chart = df[["primary_category", "abs_impact_yi_p0_p20"]].copy()
    chart["abs_impact_yi_p0_p20"] = pd.to_numeric(chart["abs_impact_yi_p0_p20"], errors="coerce").fillna(0)
    chart = chart.sort_values("abs_impact_yi_p0_p20", ascending=True)
    max_value = chart["abs_impact_yi_p0_p20"].max() or 1
    bars = []
    for _, row in chart.iterrows():
        width = max(2, row["abs_impact_yi_p0_p20"] / max_value * 100)
        bars.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{escape(str(row["primary_category"]))}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{width:.1f}%"></span></span>'
            f'<span class="bar-value">{row["abs_impact_yi_p0_p20"]:.0f}</span>'
            "</div>"
        )
    return '<div class="bars">' + "".join(bars) + "</div>"


def main() -> int:
    subject = load_csv(TOP_DIR / "subject_top_100.csv")
    peers = load_csv(TOP_DIR / "peer_action_top_100.csv")
    subject_objective = load_csv(TOP_DIR / "subject_objective_mv_change_top_100.csv")
    peer_objective = load_csv(TOP_DIR / "peer_objective_mv_change_top_100.csv")
    positive = load_csv(TOP_DIR / "positive_impact_top_50.csv")
    negative = load_csv(TOP_DIR / "negative_impact_top_50.csv")
    positive_actual = load_csv(TOP_DIR / "positive_actual_mv_change_top_50.csv")
    negative_actual = load_csv(TOP_DIR / "negative_actual_mv_change_top_50.csv")
    spillover = load_csv(TOP_DIR / "peer_spillover_to_yiwei_top_50.csv")
    learning = load_csv(TOP_DIR / "peer_learning_actions_top_50.csv")
    ipo = load_csv(TOP_DIR / "ipo_listing_events_top_100.csv")
    category = load_csv(TOP_DIR / "category_impact_summary.csv")
    status = load_csv(PROCESSED_DIR / "car_status_summary.csv")

    event_cols = [
        "event_date",
        "company",
        "primary_category",
        "title",
        "group_event_count",
        "pre_total_mv_yi",
        "end_total_mv_yi_p0_p20",
        "actual_mv_change_yi_p0_p20",
        "actual_mv_return_p0_p20",
        "peer_avg_mv_return_p0_p20",
        "peer_rank_by_mv_return_p0_p20",
        "peer_rank_total_p0_p20",
        "car_m1_p1",
        "car_p0_p20",
        "abnormal_mv_impact_yi_p0_p20",
        "event_priority_score",
    ]
    objective_cols = [
        "event_date",
        "company",
        "primary_category",
        "title",
        "pre_total_mv_yi",
        "end_total_mv_yi_p0_p20",
        "actual_mv_change_yi_p0_p20",
        "actual_mv_return_p0_p20",
        "peer_avg_mv_return_p0_p20",
        "peer_rank_by_mv_return_p0_p20",
        "peer_rank_total_p0_p20",
        "car_p0_p20",
        "objective_change_score",
    ]
    spill_cols = [
        "event_date",
        "company",
        "primary_category",
        "title",
        "actual_mv_return_p0_p20",
        "actual_mv_change_yi_p0_p20",
        "car_p0_p20",
        "yiwei_actual_mv_return_p0_p20",
        "yiwei_actual_mv_change_yi_p0_p20",
        "yiwei_car_p0_p20",
        "yiwei_abnormal_mv_impact_yi_p0_p20",
        "peer_key_action_score",
    ]
    category_cols = [
        "primary_category",
        "event_count",
        "avg_actual_mv_return_p0_p20",
        "median_actual_mv_change_yi_p0_p20",
        "abs_actual_mv_change_yi_p0_p20",
        "avg_car_p0_p20",
        "median_impact_yi_p0_p20",
        "abs_impact_yi_p0_p20",
    ]

    write_chinese_csv(subject, "移为自身事件Top100_中文.csv", event_cols)
    write_chinese_csv(peers, "竞品关键动作Top100_中文.csv", event_cols)
    write_chinese_csv(subject_objective, "移为客观市值变化Top100_中文.csv", objective_cols)
    write_chinese_csv(peer_objective, "竞品客观市值变化Top100_中文.csv", objective_cols)
    write_chinese_csv(positive, "正向异常市值影响Top50_中文.csv", event_cols)
    write_chinese_csv(negative, "负向异常市值影响Top50_中文.csv", event_cols)
    write_chinese_csv(positive_actual, "正向客观市值变化Top50_中文.csv", objective_cols)
    write_chinese_csv(negative_actual, "负向客观市值变化Top50_中文.csv", objective_cols)
    write_chinese_csv(spillover, "竞品事件对移为外溢Top50_中文.csv", spill_cols)
    write_chinese_csv(learning, "竞品关键动作综合评分Top50_中文.csv", spill_cols)
    write_chinese_csv(ipo, "IPO上市初期事件Top100_中文.csv", objective_cols)
    write_chinese_csv(category, "事件类型影响汇总_中文.csv", category_cols)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>移为通信市值事件分析预览</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: #20242a; background: #f5f7fa; }}
    header {{ padding: 24px 32px; background: #1f2937; color: white; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    p {{ margin: 4px 0; line-height: 1.55; }}
    main {{ padding: 24px 32px 48px; }}
    section {{ margin-bottom: 24px; padding: 20px; background: white; border: 1px solid #dce2ea; border-radius: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #e7ecf2; vertical-align: top; }}
    th {{ text-align: left; background: #f0f3f7; font-weight: 700; }}
    td:nth-child(4) {{ width: 34%; }}
    .note {{ color: #5d6673; font-size: 13px; }}
    .empty {{ color: #7a8491; }}
    .bars {{ display: flex; flex-direction: column; gap: 10px; }}
    .bar-row {{ display: grid; grid-template-columns: 120px minmax(120px, 1fr) 80px; gap: 10px; align-items: center; font-size: 13px; }}
    .bar-track {{ height: 14px; background: #e6ebf1; border-radius: 4px; overflow: hidden; }}
    .bar-fill {{ display: block; height: 100%; background: #2563eb; }}
    .bar-value {{ text-align: right; color: #4b5563; }}
    @media (max-width: 900px) {{ main, header {{ padding-left: 16px; padding-right: 16px; }} .grid {{ grid-template-columns: 1fr; }} table {{ font-size: 12px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>移为通信市值事件分析预览</h1>
    <p>数据口径：先看事件窗口内客观市值变化，再用 CAR 作为同行调整后的辅助指标。</p>
    <p class="note">注意：这是测试预览页，不是 CFO 终稿。分类仍需复核，事件分析法不能单独证明因果。</p>
  </header>
  <main>
    <section>
      <h2>CAR 计算状态</h2>
      {table_html(status, ["status", "rows"], 10)}
    </section>
    <section>
      <h2>分类影响绝对值汇总</h2>
      {bar_chart_html(category)}
      {table_html(category, category_cols, 12)}
    </section>
    <section>
      <h2>IPO / 上市初期事件专题 Top 20</h2>
      {table_html(ipo, objective_cols, 20)}
    </section>
    <section>
      <h2>移为自身客观市值变化 Top 20</h2>
      {table_html(subject_objective, objective_cols, 20)}
    </section>
    <section>
      <h2>竞品客观市值变化 Top 20</h2>
      {table_html(peer_objective, objective_cols, 20)}
    </section>
    <div class="grid">
      <section>
        <h2>正向客观市值变化 Top 20</h2>
        {table_html(positive_actual, objective_cols, 20)}
      </section>
      <section>
        <h2>负向客观市值变化 Top 20</h2>
        {table_html(negative_actual, objective_cols, 20)}
      </section>
    </div>
    <section>
      <h2>移为自身事件分析法辅助 Top 20</h2>
      {table_html(subject, event_cols, 20)}
    </section>
    <section>
      <h2>竞品关键动作事件分析法辅助 Top 20</h2>
      {table_html(peers, event_cols, 20)}
    </section>
    <section>
      <h2>竞品事件对移为外溢 Top 20</h2>
      {table_html(spillover, spill_cols, 20)}
    </section>
    <section>
      <h2>竞品关键动作综合评分 Top 20</h2>
      {table_html(learning, spill_cols, 20)}
    </section>
  </main>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    sys.stdout.write(f"preview={OUTPUT_PATH}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

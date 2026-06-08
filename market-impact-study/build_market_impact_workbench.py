"""生成市值事件工作台。"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from build_interactive_market_dashboard import (
    COMPANIES,
    PROCESSED_DIR,
    load_event_rows,
    load_market_rows,
    text_value,
)
from make_preview_report import FIELD_LABELS, STATUS_LABELS

TOP_DIR = PROCESSED_DIR / "top_events"
SPILLOVER_PATH = PROCESSED_DIR / "peer_spillover_to_yiwei.csv"
CAR_STATUS_PATH = PROCESSED_DIR / "car_status_summary.csv"
WORKBENCH_OUTPUT = PROCESSED_DIR / "market_impact_workbench.html"


def finite(value: object, digits: int = 6) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def json_value(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, int | bool | str):
        return value
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    return str(value)


def load_spillover_rows() -> list[dict[str, object]]:
    if not SPILLOVER_PATH.exists():
        return []
    columns = [
        "analysis_group_id",
        "event_id",
        "company",
        "event_date",
        "primary_category",
        "title",
        "actual_mv_change_yi_p0_p20",
        "actual_mv_return_p0_p20",
        "car_p0_p20",
        "yiwei_actual_mv_change_yi_p0_p20",
        "yiwei_actual_mv_return_p0_p20",
        "yiwei_car_p0_p20",
        "yiwei_abnormal_mv_impact_yi_p0_p20",
        "peer_minus_yiwei_car_p0_p20",
    ]
    frame = pd.read_csv(SPILLOVER_PATH, usecols=lambda column: column in columns)
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "id": text_value(row.get("analysis_group_id")),
                "event_id": text_value(row.get("event_id")),
                "company": text_value(row.get("company")),
                "date": text_value(row.get("event_date"))[:10],
                "category": text_value(row.get("primary_category")),
                "title": text_value(row.get("title")),
                "peer_mv_change_20d": finite(row.get("actual_mv_change_yi_p0_p20"), 4),
                "peer_mv_return_20d": finite(row.get("actual_mv_return_p0_p20"), 6),
                "peer_car_20d": finite(row.get("car_p0_p20"), 6),
                "yiwei_mv_change_20d": finite(row.get("yiwei_actual_mv_change_yi_p0_p20"), 4),
                "yiwei_mv_return_20d": finite(row.get("yiwei_actual_mv_return_p0_p20"), 6),
                "yiwei_car_20d": finite(row.get("yiwei_car_p0_p20"), 6),
                "yiwei_abnormal_mv_impact_20d": finite(row.get("yiwei_abnormal_mv_impact_yi_p0_p20"), 4),
                "peer_minus_yiwei_car_20d": finite(row.get("peer_minus_yiwei_car_p0_p20"), 6),
            }
        )
    return rows


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def table_payload(label: str, filename: str, columns: list[str], limit: int = 300) -> dict[str, object]:
    path = TOP_DIR / filename
    if filename == "car_status_summary.csv":
        path = PROCESSED_DIR / filename
    frame = load_csv(path)
    use_columns = [column for column in columns if column in frame.columns]
    if not frame.empty and use_columns:
        frame = frame[use_columns].head(limit)
    else:
        frame = pd.DataFrame(columns=use_columns)
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        item: dict[str, object] = {}
        for column in use_columns:
            value = row[column]
            if column == "status":
                value = STATUS_LABELS.get(str(value), value)
            item[column] = json_value(value)
        rows.append(item)
    return {
        "label": label,
        "source": filename,
        "columns": use_columns,
        "headers": {column: FIELD_LABELS.get(column, column) for column in use_columns},
        "rows": rows,
    }


def build_top_payload() -> dict[str, object]:
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
    tables = [
        table_payload("CAR 计算状态", "car_status_summary.csv", ["status", "rows"], 30),
        table_payload("分类影响汇总", "category_impact_summary.csv", category_cols, 100),
        table_payload("IPO / 上市初期事件", "ipo_listing_events_top_100.csv", objective_cols, 100),
        table_payload("移为自身客观市值变化", "subject_objective_mv_change_top_100.csv", objective_cols, 100),
        table_payload("竞品客观市值变化", "peer_objective_mv_change_top_100.csv", objective_cols, 100),
        table_payload("正向客观市值变化", "positive_actual_mv_change_top_50.csv", objective_cols, 50),
        table_payload("负向客观市值变化", "negative_actual_mv_change_top_50.csv", objective_cols, 50),
        table_payload("移为自身事件分析法辅助", "subject_top_100.csv", event_cols, 100),
        table_payload("竞品关键动作事件分析法辅助", "peer_action_top_100.csv", event_cols, 100),
        table_payload("竞品事件对移为外溢", "peer_spillover_to_yiwei_top_50.csv", spill_cols, 50),
        table_payload("竞品关键动作综合评分", "peer_learning_actions_top_50.csv", spill_cols, 50),
    ]
    return {"tables": tables}


def load_workbench_events() -> list[dict[str, object]]:
    rows = load_event_rows()
    for row in rows:
        if row.get("evidence_level") == "none":
            row["evidence_label"] = "未挂接"
    return rows


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_workbench_html(payload: dict[str, Any]) -> str:
    return WORKBENCH_HTML.replace("__PAYLOAD__", dumps(payload))


WORKBENCH_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>移为通信市值事件工作台</title>
  <style>
    :root {
      --ink: #20242a;
      --muted: #6b7280;
      --line: #dfe5ec;
      --soft: #f5f7fa;
      --panel: #ffffff;
      --accent: #b42318;
      --blue: #2463a6;
      --green: #197a50;
      --warn: #a15c00;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: #f7f8fa;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }
    header {
      padding: 14px 24px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
    }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 21px; }
    h2 { font-size: 18px; margin-bottom: 8px; }
    h3 { font-size: 15px; margin-bottom: 8px; }
    a { color: var(--blue); text-decoration: none; font-weight: 700; }
    a:hover { text-decoration: underline; }
    button, select, input { font: inherit; }
    button, select, input {
      min-height: 30px;
      border: 1px solid #cfd7e2;
      border-radius: 5px;
      background: #fff;
      color: var(--ink);
    }
    button { padding: 4px 10px; cursor: pointer; }
    button.active, button.primary {
      background: #1f2937;
      border-color: #1f2937;
      color: #fff;
      font-weight: 700;
    }
    button.icon { width: 28px; padding: 0; font-weight: 700; }
    select, input { padding: 4px 8px; min-width: 120px; }
    main { padding: 14px 18px 28px; }
    .muted { color: var(--muted); font-size: 12px; line-height: 1.5; }
    .filters {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 10px 12px;
      align-items: end;
      margin-bottom: 12px;
    }
    .field { min-width: 0; }
    .field label {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      margin-bottom: 5px;
    }
    .field select, .field input { width: 100%; min-width: 0; }
    .span2 { grid-column: span 2; }
    .span3 { grid-column: span 3; }
    .span4 { grid-column: span 4; }
    .span6 { grid-column: span 6; }
    .range { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
    .company-picks {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1px solid #d6dde7;
      border-radius: 5px;
      padding: 4px 8px;
      background: #fff;
      font-size: 12px;
    }
    .chip input { width: 13px; min-width: 13px; min-height: 13px; }
    .tabs {
      display: flex;
      gap: 6px;
      margin: 0 0 12px;
      flex-wrap: wrap;
    }
    .tabs button { border-radius: 6px; }
    .kpis {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .kpi {
      min-height: 76px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
    }
    .kpi .value { margin-top: 7px; font-size: 23px; font-weight: 800; font-variant-numeric: tabular-nums; }
    .panel {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 12px;
    }
    .view { display: none; }
    .view.active { display: block; }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 12px;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }
    .seg {
      display: inline-flex;
      border: 1px solid #cfd7e2;
      border-radius: 6px;
      overflow: hidden;
      background: #fff;
    }
    .seg button {
      border: 0;
      border-right: 1px solid #cfd7e2;
      border-radius: 0;
      min-height: 30px;
      font-size: 12px;
    }
    .seg button:last-child { border-right: 0; }
    .market-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 12px;
      align-items: start;
    }
    .market-stack {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 12px;
    }
    .market-chart-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 224px;
      gap: 12px;
      align-items: start;
    }
    .chart-shell { min-width: 0; }
    svg.main-chart {
      width: 100%;
      height: 470px;
      display: block;
      border: 1px solid #edf1f5;
      border-radius: 6px;
      background: #fff;
    }
    #alignedChart { height: 500px; }
    #peerChart { height: 500px; }
    .side {
      border-left: 3px solid #e6ebf1;
      padding-left: 12px;
      min-width: 0;
    }
    .info-block {
      border: 1px solid #edf1f5;
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfd;
      min-width: 0;
    }
    .market-rank-panel {
      border: 1px solid #e6ebf1;
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfd;
      min-width: 0;
    }
    .market-rank-panel h3 {
      margin-bottom: 10px;
      color: #334155;
      font-size: 13px;
      letter-spacing: 0;
    }
    .focus-rank {
      display: flex;
      flex-direction: column;
      gap: 7px;
    }
    .focus-company {
      padding: 8px;
      border-radius: 5px;
      background: #fff;
      border: 1px solid #e9eef4;
    }
    .focus-company .name {
      color: #111827;
      font-size: 15px;
      font-weight: 800;
    }
    .rank-row {
      display: grid;
      grid-template-columns: 24px minmax(0, 1fr);
      gap: 7px;
      align-items: center;
      padding: 7px 8px;
      border: 1px solid #e9eef4;
      border-radius: 5px;
      background: #fff;
    }
    .rank-no {
      color: #94a3b8;
      font-size: 11px;
      font-weight: 800;
      font-variant-numeric: tabular-nums;
    }
    .rank-label {
      color: #64748b;
      font-size: 11px;
      line-height: 1.2;
    }
    .rank-value {
      margin-top: 2px;
      color: #111827;
      font-size: 17px;
      font-weight: 850;
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
      white-space: nowrap;
    }
    .market-events-block { width: 100%; }
    .mini-events-table th, .mini-events-table td { white-space: nowrap; }
    .mini-events-table td:nth-child(4) { white-space: normal; }
    .basket-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 420px;
      overflow: auto;
    }
    .event-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px;
      background: #fff;
    }
    .event-card .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .table-wrap { overflow: auto; border: 1px solid #edf1f5; border-radius: 6px; }
    .top-layout {
      display: grid;
      grid-template-columns: 250px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
    }
    .top-topic-list {
      display: flex;
      flex-direction: column;
      gap: 7px;
      max-height: 620px;
      overflow: auto;
    }
    .top-topic-list button { text-align: left; }
    .top-table-wrap {
      overflow: auto;
      border: 1px solid #edf1f5;
      border-radius: 6px;
      max-height: 620px;
    }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
    th, td { border-bottom: 1px solid #edf1f5; padding: 7px 8px; vertical-align: top; word-break: break-word; }
    th { background: #f4f6f9; color: #4b5563; text-align: left; position: sticky; top: 0; z-index: 1; }
    tr.active-row { background: rgba(180, 35, 24, .055); }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .pos { color: var(--green); }
    .neg { color: var(--accent); }
    .tag {
      display: inline-flex;
      border-radius: 999px;
      padding: 2px 7px;
      background: #eef2f7;
      color: #334155;
      white-space: nowrap;
      font-size: 12px;
    }
    .tag.strong { background: #dcfce7; color: #166534; }
    .tag.auxiliary { background: #dbeafe; color: #1d4ed8; }
    .tag.weak { background: #fef3c7; color: #92400e; }
    .tag.none { background: #f1f5f9; color: #64748b; }
    .drawer {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 12px;
    }
    .drawer > div {
      border: 1px solid #edf1f5;
      border-radius: 6px;
      padding: 10px;
    }
    .tip {
      display: none;
      position: fixed;
      z-index: 20;
      pointer-events: none;
      max-width: 340px;
      background: rgba(255,255,255,.98);
      border: 1px solid #cfd7e2;
      border-radius: 6px;
      box-shadow: 0 12px 28px rgba(15, 23, 42, .16);
      padding: 9px 10px;
      font-size: 12px;
      line-height: 1.5;
    }
    .empty { color: var(--muted); padding: 12px 0; }
    .spark { width: 112px; height: 26px; display: block; }
    .spill-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .mini {
      border: 1px solid #edf1f5;
      border-radius: 6px;
      padding: 9px;
      background: #fbfcfd;
    }
    @media (max-width: 1180px) {
      .filters { grid-template-columns: repeat(6, minmax(0, 1fr)); }
      .span2, .span3 { grid-column: span 2; }
      .span4, .span6 { grid-column: span 6; }
      .market-grid { grid-template-columns: 1fr; }
      .market-chart-row { grid-template-columns: 1fr; }
      .top-layout { grid-template-columns: 1fr; }
      .side { border-left: 0; padding-left: 0; }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 720px) {
      header { align-items: start; flex-direction: column; }
      main { padding: 10px; }
      .filters { grid-template-columns: 1fr; }
      .span2, .span3, .span4, .span6 { grid-column: span 1; }
      .range, .drawer, .spill-grid { grid-template-columns: 1fr; }
      .kpis { grid-template-columns: 1fr; }
      svg.main-chart, #alignedChart, #peerChart { height: 430px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>移为通信市值事件工作台</h1>
      <p class="muted">口径：总市值单位为亿元；CAR 作为同行调整辅助字段；RAG 挂接状态不等同于原始事件来源。</p>
    </div>
  </header>
  <main>
    <section class="filters" aria-label="全局筛选">
      <div class="field span2">
        <label>时间期间</label>
        <select id="period">
          <option value="yiwei">移为上市以来</option>
          <option value="5y">近五年</option>
          <option value="3y">近三年</option>
          <option value="1y">近一年</option>
          <option value="all">全样本区间</option>
          <option value="custom">自定义</option>
        </select>
      </div>
      <div class="field span2">
        <label>月份</label>
        <select id="month"></select>
      </div>
      <div class="field span3">
        <label>自定义日期</label>
        <div class="range">
          <input id="startDate" type="date" />
          <input id="endDate" type="date" />
        </div>
      </div>
      <div class="field span2">
        <label>事件窗口</label>
        <select id="windowSize">
          <option value="5">5 日</option>
          <option value="20" selected>20 日</option>
          <option value="60">60 日</option>
          <option value="custom">自定义</option>
        </select>
      </div>
      <div class="field span3">
        <label>自定义窗口</label>
        <div class="range">
          <input id="windowBefore" type="number" value="0" min="-120" max="0" />
          <input id="windowAfter" type="number" value="20" min="1" max="240" />
        </div>
      </div>
      <div class="field span3">
        <label>事件类型</label>
        <select id="category"></select>
      </div>
      <div class="field span3">
        <label>二级事件</label>
        <select id="subtype"></select>
      </div>
      <div class="field span3">
        <label>关键词</label>
        <input id="search" placeholder="标题 / 公司 / 来源" />
      </div>
      <div class="field span6">
        <label>公司</label>
        <div id="companyPicks" class="company-picks"></div>
      </div>
    </section>

    <nav class="tabs" aria-label="视图">
      <button class="active" data-view="marketView" type="button">市值走势</button>
      <button data-view="eventsView" type="button">事件影响</button>
      <button data-view="peersView" type="button">竞品对比</button>
      <button data-view="alignedView" type="button">事件对齐 / 外溢</button>
      <button data-view="topView" type="button">Top 专题</button>
    </nav>

    <section id="kpis" class="kpis"></section>

    <section id="marketView" class="view active">
      <div class="panel">
        <div class="toolbar">
          <div>
            <h2>市值走势</h2>
            <p class="muted">主图按时间跨度自动采样；事件点限量显示，完整事件保留在事件影响表。</p>
          </div>
          <div>
            <div class="seg" aria-label="走势模式">
              <button class="active" data-market-mode="focus" type="button">单公司</button>
              <button data-market-mode="overlay" type="button">叠加</button>
              <button data-market-mode="lane" type="button">分面</button>
            </div>
            <div class="seg" aria-label="走势指标">
              <button class="active" data-market-unit="value" type="button">市值</button>
              <button data-market-unit="index" type="button">指数</button>
            </div>
          </div>
        </div>
        <div class="market-stack">
          <div class="market-chart-row">
            <div class="chart-shell">
              <svg id="marketChart" class="main-chart" role="img" aria-label="市值走势"></svg>
            </div>
            <aside class="market-rank-panel">
              <h3>区间表现</h3>
              <div id="focusInfo"></div>
            </aside>
          </div>
          <section class="info-block market-events-block">
            <h3>筛选事件</h3>
            <div id="eventMiniTable"></div>
          </section>
        </div>
      </div>
    </section>

    <section id="eventsView" class="view">
      <div class="panel">
        <div class="toolbar">
          <div>
            <h2>事件影响</h2>
            <p class="muted">表格展示事件窗口内客观市值变化、CAR 辅助字段、原始来源和 RAG 挂接状态。</p>
          </div>
          <button id="exportEvents" type="button">导出当前事件 CSV</button>
        </div>
        <div id="eventTable" class="table-wrap"></div>
        <div id="eventDrawer" class="drawer"></div>
      </div>
    </section>

    <section id="peersView" class="view">
      <div class="panel">
        <div class="toolbar">
          <div>
            <h2>竞品对比</h2>
            <p class="muted">气泡图：x=区间涨跌幅，y=最大回撤，大小=期末总市值。</p>
          </div>
        </div>
        <svg id="peerChart" class="main-chart" role="img" aria-label="竞品对比气泡图"></svg>
      </div>
      <div class="panel">
        <h2>公司可比矩阵</h2>
        <div id="companyMatrix" class="table-wrap"></div>
      </div>
    </section>

    <section id="alignedView" class="view">
      <div class="panel">
        <div class="toolbar">
          <div>
            <h2>事件对齐</h2>
            <p class="muted">事件篮中的事件按事件日 T=0 对齐，显示窗口内相对涨跌幅。</p>
          </div>
          <button id="clearBasket" type="button">清空事件篮</button>
        </div>
        <div class="market-grid">
          <div class="chart-shell">
            <svg id="alignedChart" class="main-chart" role="img" aria-label="事件对齐曲线"></svg>
          </div>
          <aside class="side">
            <h3>事件篮</h3>
            <div id="basketList" class="basket-list"></div>
          </aside>
        </div>
        <div class="spill-grid">
          <div class="mini">
            <h3>外溢字段</h3>
            <div id="spilloverDetail"></div>
          </div>
          <div class="mini">
            <h3>事件篮指标</h3>
            <div id="basketMetrics"></div>
          </div>
        </div>
      </div>
    </section>

    <section id="topView" class="view">
      <div class="panel">
        <div class="toolbar">
          <div>
            <h2>Top 专题</h2>
            <p class="muted">专题表来源为 processed/top_events 与 CAR 状态汇总；用于筛选、排序和导出。</p>
          </div>
          <div>
            <input id="topSearch" placeholder="筛选当前专题表" />
            <button id="exportTop" type="button">导出当前专题 CSV</button>
          </div>
        </div>
        <div class="top-layout">
          <aside id="topTopics" class="top-topic-list"></aside>
          <div>
            <h3 id="topTitle"></h3>
            <p id="topSource" class="muted" style="margin-bottom:8px;"></p>
            <div id="topTable" class="top-table-wrap"></div>
          </div>
        </div>
      </div>
    </section>
  </main>
  <div id="tip" class="tip"></div>
  <script id="payload" type="application/json">__PAYLOAD__</script>
  <script>
    const payload = JSON.parse(document.getElementById('payload').textContent);
    const companies = payload.companies;
    const marketRows = payload.marketRows.map(row => ({...row, t: Date.parse(row.date)}));
    const events = payload.events.map(row => ({...row, t: Date.parse(row.date)}));
    const spilloverRows = payload.spilloverRows || [];
    const topTables = payload.topTables || [];
    const spilloverById = new Map();
    spilloverRows.forEach(row => {
      if (row.id) spilloverById.set(row.id, row);
      if (row.event_id) spilloverById.set(row.event_id, row);
    });

    const byCompany = new Map();
    marketRows.forEach(row => {
      if (!byCompany.has(row.ts_code)) byCompany.set(row.ts_code, []);
      byCompany.get(row.ts_code).push(row);
    });
    byCompany.forEach(rows => rows.sort((a, b) => a.t - b.t));

    const colors = ['#b42318', '#2463a6', '#14866d', '#7c3aed', '#b35c00', '#334155', '#2e7d32', '#64748b', '#d29a00'];
    const colorByCode = Object.fromEntries(companies.map((company, index) => [company.ts_code, colors[index % colors.length]]));
    const selectedCompanies = new Set(companies.map(company => company.ts_code));
    const basket = [];
    let activeView = 'marketView';
    let marketMode = 'focus';
    let marketUnit = 'value';
    let focusedCompany = '300590.SZ';
    let selectedEventId = '';
    let selectedTopIndex = 0;
    let topSort = {column: '', dir: 1};

    const els = {
      period: document.getElementById('period'),
      month: document.getElementById('month'),
      start: document.getElementById('startDate'),
      end: document.getElementById('endDate'),
      windowSize: document.getElementById('windowSize'),
      before: document.getElementById('windowBefore'),
      after: document.getElementById('windowAfter'),
      category: document.getElementById('category'),
      subtype: document.getElementById('subtype'),
      search: document.getElementById('search'),
      companyPicks: document.getElementById('companyPicks'),
      kpis: document.getElementById('kpis'),
      marketChart: document.getElementById('marketChart'),
      alignedChart: document.getElementById('alignedChart'),
      peerChart: document.getElementById('peerChart'),
      focusInfo: document.getElementById('focusInfo'),
      eventMiniTable: document.getElementById('eventMiniTable'),
      eventTable: document.getElementById('eventTable'),
      eventDrawer: document.getElementById('eventDrawer'),
      companyMatrix: document.getElementById('companyMatrix'),
      basketList: document.getElementById('basketList'),
      spilloverDetail: document.getElementById('spilloverDetail'),
      basketMetrics: document.getElementById('basketMetrics'),
      topSearch: document.getElementById('topSearch'),
      topTopics: document.getElementById('topTopics'),
      topTitle: document.getElementById('topTitle'),
      topSource: document.getElementById('topSource'),
      topTable: document.getElementById('topTable'),
      tip: document.getElementById('tip'),
    };

    function htmlEscape(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[ch]));
    }
    function fmt(value, digits = 2) {
      const number = Number(value);
      return Number.isFinite(number) ? number.toFixed(digits) : '';
    }
    function pct(value) {
      const number = Number(value);
      return Number.isFinite(number) ? (number * 100).toFixed(2) + '%' : '';
    }
    function cls(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return '';
      return number >= 0 ? 'pos' : 'neg';
    }
    function dateStr(t) {
      return new Date(t).toISOString().slice(0, 10);
    }
    function addDays(t, days) {
      const date = new Date(t);
      date.setDate(date.getDate() + days);
      return date.getTime();
    }
    function uniq(values) {
      return Array.from(new Set(values.filter(Boolean))).sort((a, b) => String(a).localeCompare(String(b), 'zh-CN'));
    }
    function monthDiff(start, end) {
      return (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth();
    }
    function linePath(points) {
      return points.map((point, index) => `${index ? 'L' : 'M'}${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(' ');
    }
    function areaPath(points, baselineY) {
      if (!points.length) return '';
      const first = points[0];
      const last = points[points.length - 1];
      return `${linePath(points)} L${last[0].toFixed(1)},${baselineY.toFixed(1)} L${first[0].toFixed(1)},${baselineY.toFixed(1)} Z`;
    }
    function yearBands(range, x, top, height) {
      const startYear = new Date(range[0]).getFullYear();
      const endYear = new Date(range[1]).getFullYear();
      let body = '';
      for (let year = startYear; year <= endYear; year += 1) {
        const yStart = Math.max(range[0], Date.parse(`${year}-01-01`));
        const yEnd = Math.min(range[1], Date.parse(`${year + 1}-01-01`));
        const x0 = x(yStart);
        const x1 = x(yEnd);
        const fill = year % 2 === 0 ? '#fff8f3' : '#f6faf9';
        body += `<rect x="${x0.toFixed(1)}" y="${top}" width="${Math.max(0, x1 - x0).toFixed(1)}" height="${height}" fill="${fill}" opacity=".62"/>`;
      }
      return body;
    }
    function showTip(event, html) {
      els.tip.innerHTML = html;
      els.tip.style.display = 'block';
      const rect = els.tip.getBoundingClientRect();
      let left = event.clientX + 14;
      let top = event.clientY + 14;
      if (left + rect.width > window.innerWidth - 8) left = event.clientX - rect.width - 14;
      if (top + rect.height > window.innerHeight - 8) top = event.clientY - rect.height - 14;
      els.tip.style.left = `${Math.max(8, left)}px`;
      els.tip.style.top = `${Math.max(8, top)}px`;
    }
    function hideTip() {
      els.tip.style.display = 'none';
    }
    function buildTimeTicks(range) {
      const start = new Date(range[0]);
      const end = new Date(range[1]);
      const months = Math.max(1, monthDiff(start, end));
      const step = months > 96 ? 24 : months > 60 ? 12 : months > 30 ? 6 : months > 12 ? 3 : 1;
      const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
      const ticks = [];
      while (cursor.getTime() <= range[1]) {
        const t = cursor.getTime();
        if (t >= range[0]) {
          ticks.push({t, label: step >= 12 ? String(cursor.getFullYear()) : `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}`});
        }
        cursor.setMonth(cursor.getMonth() + step);
      }
      if (!ticks.length) ticks.push({t: range[0], label: dateStr(range[0])});
      return ticks;
    }
    function currentRange() {
      const minT = Math.min(...marketRows.map(row => row.t));
      const maxT = Math.max(...marketRows.map(row => row.t));
      const yiweiRows = byCompany.get('300590.SZ') || [];
      const yiweiMinT = yiweiRows.length ? yiweiRows[0].t : minT;
      const yiweiMaxT = yiweiRows.length ? yiweiRows[yiweiRows.length - 1].t : maxT;
      if (els.period.value === 'custom') {
        if (!els.start.value || !els.end.value) return [addDays(maxT, -365), maxT];
        return [Date.parse(els.start.value), Date.parse(els.end.value)];
      }
      if (els.month.value && els.month.value !== 'all') {
        const start = Date.parse(`${els.month.value}-01`);
        const end = new Date(start);
        end.setMonth(end.getMonth() + 1);
        end.setDate(0);
        return [start, end.getTime()];
      }
      if (els.period.value === '1y') return [addDays(maxT, -365), maxT];
      if (els.period.value === '3y') return [addDays(maxT, -365 * 3), maxT];
      if (els.period.value === '5y') return [addDays(maxT, -365 * 5), maxT];
      if (els.period.value === 'yiwei') return [yiweiMinT, yiweiMaxT];
      return [minT, maxT];
    }
    function windowConfig() {
      if (els.windowSize.value === 'custom') return [Number(els.before.value || 0), Number(els.after.value || 20)];
      return [0, Number(els.windowSize.value || 20)];
    }
    function selectedRows(tsCode) {
      const range = currentRange();
      return (byCompany.get(tsCode) || []).filter(row => row.t >= range[0] && row.t <= range[1]);
    }
    function filteredEvents(options = {}) {
      const range = currentRange();
      const q = els.search.value.trim().toLowerCase();
      return events.filter(event => {
        if (event.t < range[0] || event.t > range[1]) return false;
        if (!selectedCompanies.has(event.ts_code)) return false;
        if (options.focusOnly && focusedCompany && event.ts_code !== focusedCompany) return false;
        if (!options.ignoreCategory && els.category.value && event.category !== els.category.value) return false;
        if (!options.ignoreSubtype && els.subtype.value && event.subtype !== els.subtype.value) return false;
        if (q) {
          const haystack = [event.company, event.category, event.subtype, event.title, event.evidence_source, event.evidence_title].join(' ').toLowerCase();
          if (!haystack.includes(q)) return false;
        }
        return true;
      }).sort((a, b) => b.t - a.t || Number(b.priority_score || 0) - Number(a.priority_score || 0));
    }
    function companyStats(tsCode) {
      const rows = selectedRows(tsCode);
      if (!rows.length) return null;
      const start = Number(rows[0].total_mv_yi);
      const end = Number(rows[rows.length - 1].total_mv_yi);
      let peak = -Infinity;
      let maxDrawdown = 0;
      let min = Infinity;
      let max = -Infinity;
      rows.forEach(row => {
        const value = Number(row.total_mv_yi);
        if (!Number.isFinite(value)) return;
        peak = Math.max(peak, value);
        min = Math.min(min, value);
        max = Math.max(max, value);
        if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (value - peak) / peak);
      });
      const evs = filteredEvents().filter(event => event.ts_code === tsCode);
      return {
        rows, start, end, min, max,
        change: end - start,
        ret: start ? (end - start) / start : null,
        maxDrawdown,
        eventCount: evs.length,
        basketCount: basket.filter(event => event.ts_code === tsCode).length,
      };
    }
    function populateMonths() {
      const previous = els.month.value;
      const range = currentRange();
      els.month.innerHTML = '<option value="all">全部月份</option>';
      if (els.period.value !== 'custom') {
        const months = uniq(marketRows.filter(row => row.t >= range[0] && row.t <= range[1]).map(row => row.date.slice(0, 7)));
        els.month.innerHTML += months.map(month => `<option value="${htmlEscape(month)}">${htmlEscape(month)}</option>`).join('');
      }
      if ([...els.month.options].some(option => option.value === previous)) els.month.value = previous;
    }
    function populateCategories() {
      const previousCategory = els.category.value;
      const previousSubtype = els.subtype.value;
      const inRange = filteredEvents({ignoreCategory: true, ignoreSubtype: true});
      const categories = uniq(inRange.map(event => event.category));
      els.category.innerHTML = '<option value="">全部事件类型</option>' + categories.map(item => `<option value="${htmlEscape(item)}">${htmlEscape(item)}</option>`).join('');
      if (categories.includes(previousCategory)) els.category.value = previousCategory;
      const subtypes = els.category.value ? uniq(inRange.filter(event => event.category === els.category.value).map(event => event.subtype)) : [];
      els.subtype.innerHTML = '<option value="">全部二级事件</option>' + subtypes.map(item => `<option value="${htmlEscape(item)}">${htmlEscape(item)}</option>`).join('');
      if (subtypes.includes(previousSubtype)) els.subtype.value = previousSubtype;
    }
    function initCompanies() {
      els.companyPicks.innerHTML = companies.map(company => `
        <label class="chip"><input type="checkbox" value="${htmlEscape(company.ts_code)}" checked />${htmlEscape(company.company)}</label>
      `).join('');
      els.companyPicks.querySelectorAll('input').forEach(input => {
        input.addEventListener('change', () => {
          if (input.checked) selectedCompanies.add(input.value);
          else selectedCompanies.delete(input.value);
          if (!selectedCompanies.has(focusedCompany)) focusedCompany = selectedCompanies.values().next().value || '';
          renderAll();
        });
      });
    }
    function renderKpis() {
      const stats = companies.filter(company => selectedCompanies.has(company.ts_code)).map(company => companyStats(company.ts_code)).filter(Boolean);
      const evs = filteredEvents();
      const yiwei = companyStats('300590.SZ');
      const totalMv = stats.reduce((sum, stat) => sum + Number(stat.end || 0), 0);
      const range = currentRange();
      els.kpis.innerHTML = [
        ['日期区间', `${dateStr(range[0])}<br>${dateStr(range[1])}`],
        ['筛选事件组', evs.length],
        ['事件篮', basket.length],
        ['移为区间涨跌幅', yiwei ? pct(yiwei.ret) : ''],
        ['选中公司期末市值合计', `${fmt(totalMv, 1)} 亿`],
      ].map(([label, value]) => `<div class="kpi"><div class="muted">${label}</div><div class="value">${value}</div></div>`).join('');
    }
    function axisGrid(width, height, margin, range) {
      let body = `<rect x="${margin.left}" y="${margin.top}" width="${width - margin.left - margin.right}" height="${height - margin.top - margin.bottom}" fill="#fff" stroke="#edf1f5"/>`;
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const x = t => margin.left + (t - range[0]) / Math.max(1, range[1] - range[0]) * plotW;
      buildTimeTicks(range).forEach(tick => {
        const tx = x(tick.t);
        body += `<line x1="${tx}" y1="${margin.top}" x2="${tx}" y2="${height - margin.bottom}" stroke="#edf1f5"/>`;
        body += `<text x="${tx}" y="${height - margin.bottom + 22}" fill="#64748b" font-size="11" text-anchor="middle">${htmlEscape(tick.label)}</text>`;
      });
      body += `<line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="#aab6c4"/>`;
      return {body, x, plotW, plotH};
    }
    function sample(rows, maxPoints = 90) {
      if (rows.length <= maxPoints) return rows;
      const step = Math.ceil(rows.length / maxPoints);
      return rows.filter((_, index) => index % step === 0 || index === rows.length - 1);
    }
    function chartRows(rows, range) {
      if (rows.length <= 260) return rows;
      const days = (range[1] - range[0]) / 86400000;
      const keyLength = days > 365 * 5 ? 7 : days > 365 * 2 ? 10 : 0;
      if (!keyLength) return sample(rows, 260);
      const bucket = new Map();
      rows.forEach(row => bucket.set(row.date.slice(0, keyLength), row));
      const compact = Array.from(bucket.values());
      if (compact[compact.length - 1] !== rows[rows.length - 1]) compact.push(rows[rows.length - 1]);
      return compact;
    }
    function eventPointLimit(range) {
      const days = (range[1] - range[0]) / 86400000;
      if (days > 365 * 5) return 45;
      if (days > 365 * 2) return 75;
      return 140;
    }
    function chartGranularityLabel(range) {
      const days = (range[1] - range[0]) / 86400000;
      if (days > 365 * 5) return '月末采样';
      if (days > 365 * 2) return '周采样';
      return '交易日';
    }
    function closest(rows, t) {
      let best = rows[0] || null;
      let bestGap = best ? Math.abs(best.t - t) : Infinity;
      rows.forEach(row => {
        const gap = Math.abs(row.t - t);
        if (gap < bestGap) {
          best = row;
          bestGap = gap;
        }
      });
      return best;
    }
    function valueFor(row, base) {
      const value = Number(row.total_mv_yi);
      if (marketUnit === 'index') return base ? (value / base - 1) : 0;
      return value;
    }
    function yScale(values, top, height) {
      let min = Math.min(...values);
      let max = Math.max(...values);
      if (!Number.isFinite(min) || !Number.isFinite(max)) { min = 0; max = 1; }
      if (min === max) { min -= 1; max += 1; }
      const pad = (max - min) * 0.08;
      min -= pad;
      max += pad;
      return {
        min, max,
        y: value => top + (max - value) / Math.max(0.000001, max - min) * height,
      };
    }
    function renderFocusMarketChart(svg, width, height, margin, range, selected, focus) {
      const rawRows = selectedRows(focus.ts_code);
      if (!rawRows.length) {
        svg.innerHTML = `<text x="24" y="48" fill="#64748b">当前区间没有 ${htmlEscape(focus.company)} 市值数据</text>`;
        return;
      }
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const x = t => margin.left + (t - range[0]) / Math.max(1, range[1] - range[0]) * plotW;
      let body = `<rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="#fff" stroke="#edf1f5"/>`;
      body += yearBands(range, x, margin.top, plotH);
      buildTimeTicks(range).forEach(tick => {
        const tx = x(tick.t);
        body += `<line x1="${tx}" y1="${margin.top}" x2="${tx}" y2="${height - margin.bottom}" stroke="#dde5ee" opacity=".7"/>`;
        body += `<text x="${tx}" y="${height - margin.bottom + 22}" fill="#64748b" font-size="11" text-anchor="middle">${htmlEscape(tick.label)}</text>`;
      });
      body += `<line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="#aab6c4"/>`;

      const rows = chartRows(rawRows, range);
      const base = Number(rawRows[0].total_mv_yi);
      const values = rows.map(row => valueFor(row, base));
      const scale = yScale(values, margin.top + 14, plotH - 28);
      for (let i = 0; i <= 4; i += 1) {
        const gy = margin.top + 14 + (plotH - 28) * i / 4;
        const value = scale.max - (scale.max - scale.min) * i / 4;
        body += `<line x1="${margin.left}" y1="${gy}" x2="${width - margin.right}" y2="${gy}" stroke="#eef2f6"/>`;
        body += `<text x="${margin.left - 10}" y="${gy + 4}" fill="#64748b" font-size="11" text-anchor="end">${marketUnit === 'index' ? pct(value) : fmt(value, 0)}</text>`;
      }
      const points = rows.map(row => [x(row.t), scale.y(valueFor(row, base))]);
      const baseline = height - margin.bottom;
      body += `<path d="${areaPath(points, baseline)}" fill="#c84232" opacity=".12"/>`;
      body += `<path d="${linePath(points)}" fill="none" stroke="#fff" stroke-width="6.2" stroke-linecap="round" stroke-linejoin="round" opacity=".86"/>`;
      body += `<path d="${linePath(points)}" fill="none" stroke="#c84232" stroke-width="4.1" stroke-linecap="round" stroke-linejoin="round"/>`;
      const valuedRows = rows.map(row => ({row, value: valueFor(row, base)})).filter(item => Number.isFinite(item.value));
      const firstItem = valuedRows[0];
      const lastItem = valuedRows[valuedRows.length - 1];
      const minItem = valuedRows.reduce((best, item) => !best || item.value < best.value ? item : best, null);
      const maxItem = valuedRows.reduce((best, item) => !best || item.value > best.value ? item : best, null);
      [minItem, maxItem].filter(Boolean).forEach(item => {
        const px = x(item.row.t);
        const py = scale.y(item.value);
        const isMax = item === maxItem;
        const label = marketUnit === 'index' ? pct(item.value) : fmt(item.value, 2);
        body += `<circle cx="${px}" cy="${py}" r="4.3" fill="#fff" stroke="#c84232" stroke-width="2"/>`;
        body += `<text x="${px}" y="${py + (isMax ? -10 : 18)}" fill="#334155" font-size="11" font-weight="700" text-anchor="middle">${label}</text>`;
      });
      if (lastItem) {
        const px = x(lastItem.row.t);
        const py = scale.y(lastItem.value);
        const label = marketUnit === 'index' ? pct(lastItem.value) : `${fmt(lastItem.value, 2)}亿`;
        const bx = Math.min(width - margin.right - 76, px + 10);
        const by = Math.max(margin.top + 6, Math.min(height - margin.bottom - 30, py - 16));
        body += `<circle cx="${px}" cy="${py}" r="4.8" fill="#c84232"/>`;
        body += `<rect x="${bx}" y="${by}" width="72" height="24" rx="4" fill="#c84232"/>`;
        body += `<text x="${bx + 36}" y="${by + 16}" fill="#fff" font-size="12" font-weight="800" text-anchor="middle">${label}</text>`;
      }
      if (firstItem) {
        const px = x(firstItem.row.t);
        const py = scale.y(firstItem.value);
        body += `<circle cx="${px}" cy="${py}" r="3.8" fill="#fff" stroke="#c84232" stroke-width="1.8"/>`;
      }
      sample(rows, 70).forEach(row => {
        body += `<circle class="hover-point" data-company="${htmlEscape(focus.company)}" data-date="${htmlEscape(row.date)}" data-value="${fmt(row.total_mv_yi)}" cx="${x(row.t)}" cy="${scale.y(valueFor(row, base))}" r="4" fill="#7f1d1d" opacity="0"/>`;
      });

      const allFocusEvents = filteredEvents({focusOnly: true});
      basket.filter(event => event.ts_code === focus.ts_code && event.t >= range[0] && event.t <= range[1]).forEach((event, index) => {
        const cx = x(event.t);
        body += `<line x1="${cx}" y1="${margin.top}" x2="${cx}" y2="${height - margin.bottom}" stroke="#1f2937" stroke-width="1.4" stroke-dasharray="4 4" opacity=".85"/>`;
        body += `<text x="${cx + 5}" y="${margin.top + 16 + index * 15}" fill="#1f2937" font-size="12" font-weight="700">E${index + 1}</text>`;
      });

      body += `<text x="${margin.left}" y="${margin.top - 12}" fill="#334155" font-size="12">${marketUnit === 'index' ? '相对涨跌幅' : '总市值（亿元）'}</text>`;
      body += `<text x="${width - margin.right}" y="${margin.top - 12}" fill="#64748b" font-size="11" text-anchor="end">${chartGranularityLabel(range)} · 筛选事件 ${allFocusEvents.length}</text>`;
      svg.innerHTML = body;
      bindChartInteractions(svg);
    }
    function renderMarketChart() {
      const svg = els.marketChart;
      const width = svg.clientWidth || 980;
      const height = svg.clientHeight || 470;
      const margin = {left: 74, right: 44, top: 34, bottom: 46};
      const range = currentRange();
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      const selected = companies.filter(company => selectedCompanies.has(company.ts_code));
      if (!selected.length) {
        svg.innerHTML = '<text x="24" y="48" fill="#64748b">未选择公司</text>';
        return;
      }
      const grid = axisGrid(width, height, margin, range);
      let body = grid.body;
      const plotH = height - margin.top - margin.bottom;
      const eventY = new Map();
      const focus = selected.find(company => company.ts_code === focusedCompany) || selected[0];
      if (marketMode === 'focus') {
        renderFocusMarketChart(svg, width, height, margin, range, selected, focus);
        return;
      }

      if (marketMode === 'lane') {
        const laneH = plotH / selected.length;
        selected.forEach((company, index) => {
          const rawRows = selectedRows(company.ts_code);
          if (!rawRows.length) return;
          const rows = chartRows(rawRows, range);
          const base = Number(rawRows[0].total_mv_yi);
          const values = rows.map(row => valueFor(row, base));
          const scale = yScale(values, margin.top + index * laneH + 18, Math.max(42, laneH - 34));
          const points = rows.map(row => [grid.x(row.t), scale.y(valueFor(row, base))]);
          body += `<line x1="${margin.left}" y1="${margin.top + (index + 1) * laneH}" x2="${width - margin.right}" y2="${margin.top + (index + 1) * laneH}" stroke="#edf1f5"/>`;
          body += `<text x="12" y="${margin.top + index * laneH + 20}" fill="${colorByCode[company.ts_code]}" font-size="12" font-weight="700">${htmlEscape(company.company)}</text>`;
          body += `<path d="${linePath(points)}" fill="none" stroke="${colorByCode[company.ts_code]}" stroke-width="${company.ts_code === focusedCompany ? 3 : 1.8}" opacity="${company.ts_code === focusedCompany ? 1 : .58}"/>`;
          sample(rows, 45).forEach(row => {
            body += `<circle class="hover-point" data-company="${htmlEscape(company.company)}" data-date="${htmlEscape(row.date)}" data-value="${fmt(row.total_mv_yi)}" cx="${grid.x(row.t)}" cy="${scale.y(valueFor(row, base))}" r="4" fill="${colorByCode[company.ts_code]}" opacity="0"/>`;
          });
        });
      } else {
        const series = marketMode === 'focus' ? [focus] : selected;
        const allValues = [];
        const seriesRows = series.map(company => {
          const rawRows = selectedRows(company.ts_code);
          const rows = chartRows(rawRows, range);
          const base = rawRows.length ? Number(rawRows[0].total_mv_yi) : 0;
          rows.forEach(row => allValues.push(valueFor(row, base)));
          return {company, rows, rawRows, base};
        });
        const scale = yScale(allValues, margin.top, plotH);
        for (let i = 0; i <= 5; i += 1) {
          const gy = margin.top + plotH * i / 5;
          const value = scale.max - (scale.max - scale.min) * i / 5;
          body += `<line x1="${margin.left}" y1="${gy}" x2="${width - margin.right}" y2="${gy}" stroke="#edf1f5"/>`;
          body += `<text x="${margin.left - 10}" y="${gy + 4}" fill="#64748b" font-size="11" text-anchor="end">${marketUnit === 'index' ? pct(value) : fmt(value, 0)}</text>`;
        }
        seriesRows.forEach(({company, rows, rawRows, base}, index) => {
          if (!rows.length) return;
          const points = rows.map(row => [grid.x(row.t), scale.y(valueFor(row, base))]);
          const isFocus = company.ts_code === focus.ts_code;
          body += `<path d="${linePath(points)}" fill="none" stroke="${colorByCode[company.ts_code]}" stroke-width="${isFocus ? 3.4 : 2}" opacity="${isFocus ? 1 : .48}" stroke-linecap="round" stroke-linejoin="round"/>`;
          const last = points[points.length - 1];
          if (last) body += `<text x="${Math.min(width - margin.right - 4, last[0] + 7)}" y="${last[1] + 4}" fill="${colorByCode[company.ts_code]}" font-size="${isFocus ? 13 : 11}" font-weight="${isFocus ? 700 : 600}">${htmlEscape(company.company)}</text>`;
          sample(rows, 70).forEach(row => {
            body += `<circle class="hover-point" data-company="${htmlEscape(company.company)}" data-date="${htmlEscape(row.date)}" data-value="${fmt(row.total_mv_yi)}" cx="${grid.x(row.t)}" cy="${scale.y(valueFor(row, base))}" r="4" fill="${colorByCode[company.ts_code]}" opacity="0"/>`;
          });
          if (marketMode === 'focus') {
            filteredEvents({focusOnly: true}).forEach(event => {
              const row = closest(rawRows, event.t);
              if (row) eventY.set(event.id, scale.y(valueFor(row, base)));
            });
          }
          if (marketMode === 'overlay') {
            body += `<text x="${margin.left + 8}" y="${margin.top + 16 + index * 18}" fill="${colorByCode[company.ts_code]}" font-size="12">${htmlEscape(company.company)}</text>`;
          }
        });
      }

      const eventSet = filteredEvents({focusOnly: marketMode === 'focus'})
        .slice()
        .sort((a, b) => Math.abs(Number(b.mv_change_20d || 0)) - Math.abs(Number(a.mv_change_20d || 0)))
        .slice(0, eventPointLimit(range))
        .sort((a, b) => a.t - b.t);
      eventSet.forEach(event => {
        const companyIndex = selected.findIndex(company => company.ts_code === event.ts_code);
        if (companyIndex < 0) return;
        const cx = grid.x(event.t);
        let cy = eventY.get(event.id);
        if (!cy) cy = marketMode === 'lane' ? margin.top + (companyIndex + .5) * (plotH / selected.length) : margin.top + 18 + (companyIndex % 9) * 14;
        const inBasket = basket.some(item => item.id === event.id);
        body += `<g class="event-dot" data-id="${htmlEscape(event.id)}" data-company="${htmlEscape(event.company)}" data-date="${htmlEscape(event.date)}" data-title="${htmlEscape(event.title)}" data-change="${fmt(event.mv_change_20d)}"><circle cx="${cx}" cy="${cy}" r="${inBasket ? 6 : 4}" fill="#fff" stroke="${colorByCode[event.ts_code] || '#b42318'}" stroke-width="${inBasket ? 2.3 : 1.5}" opacity=".9"/><circle cx="${cx}" cy="${cy}" r="1.8" fill="${colorByCode[event.ts_code] || '#b42318'}" opacity=".9"/></g>`;
      });
      body += `<text x="${margin.left}" y="${margin.top - 12}" fill="#334155" font-size="12">${marketUnit === 'index' ? '相对涨跌幅' : '总市值（亿元）'}</text>`;
      body += `<text x="${width - margin.right}" y="${margin.top - 12}" fill="#64748b" font-size="11" text-anchor="end">${chartGranularityLabel(range)} · 事件点 ${eventSet.length}</text>`;
      svg.innerHTML = body;
      bindChartInteractions(svg);
    }
    function bindChartInteractions(svg) {
      svg.querySelectorAll('.hover-point').forEach(node => {
        node.addEventListener('mousemove', event => showTip(event, `<strong>${htmlEscape(node.dataset.company)} · ${htmlEscape(node.dataset.date)}</strong><div>总市值：${htmlEscape(node.dataset.value)} 亿元</div>`));
        node.addEventListener('mouseleave', hideTip);
      });
      svg.querySelectorAll('.event-dot').forEach(node => {
        node.addEventListener('click', () => {
          const event = events.find(item => item.id === node.dataset.id);
          if (event) addEvent(event);
        });
        node.addEventListener('mousemove', event => showTip(event, `<strong>${htmlEscape(node.dataset.company)} · ${htmlEscape(node.dataset.date)}</strong><div>${htmlEscape(node.dataset.title)}</div><div>20日变化：${htmlEscape(node.dataset.change)} 亿元</div>`));
        node.addEventListener('mouseleave', hideTip);
      });
    }
    function renderFocusInfo() {
      const focus = companies.find(company => company.ts_code === focusedCompany) || companies[0];
      const stat = companyStats(focus.ts_code);
      if (!stat) {
        els.focusInfo.innerHTML = '<p class="empty">当前区间无行情数据</p>';
        return;
      }
      const metrics = [
        ['起始市值', `${fmt(stat.start)} 亿`, ''],
        ['结束市值', `${fmt(stat.end)} 亿`, ''],
        ['市值变化', `${fmt(stat.change)} 亿`, cls(stat.change)],
        ['区间涨跌幅', pct(stat.ret), cls(stat.ret)],
        ['最大回撤', pct(stat.maxDrawdown), 'neg'],
      ];
      els.focusInfo.innerHTML = `
        <div class="focus-rank">
          <div class="focus-company">
            <div class="name">${htmlEscape(focus.company)}</div>
            <div class="muted">${htmlEscape(focus.ts_code)}</div>
          </div>
          ${metrics.map(([label, value, klass], index) => `
            <div class="rank-row">
              <div class="rank-no">${String(index + 1).padStart(2, '0')}</div>
              <div>
                <div class="rank-label">${htmlEscape(label)}</div>
                <div class="rank-value ${klass}">${htmlEscape(value)}</div>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    }
    function addEvent(event) {
      if (!basket.some(item => item.id === event.id)) basket.push(event);
      if (basket.length > 10) basket.shift();
      selectedEventId = event.id;
      activeView = 'alignedView';
      setActiveView();
      renderAll();
    }
    function removeEvent(id) {
      const index = basket.findIndex(event => event.id === id);
      if (index >= 0) basket.splice(index, 1);
      renderAll();
    }
    function renderMiniEvents() {
      const rows = filteredEvents({focusOnly: marketMode === 'focus'}).slice(0, 12);
      if (!rows.length) {
        els.eventMiniTable.innerHTML = '<p class="empty">当前筛选无事件</p>';
        return;
      }
      els.eventMiniTable.innerHTML = `<div class="table-wrap"><table class="mini-events-table"><thead><tr>
        <th style="width:86px;">日期</th><th style="width:78px;">公司</th><th style="width:112px;">类型</th><th>事件标题</th><th class="num" style="width:86px;">20日变化</th><th style="width:86px;">RAG挂接</th>
      </tr></thead><tbody>${rows.map(event => `
        <tr>
          <td>${htmlEscape(event.date)}</td>
          <td>${htmlEscape(event.company)}</td>
          <td>${htmlEscape(event.category)}</td>
          <td><a href="#" class="mini-event" data-id="${htmlEscape(event.id)}">${htmlEscape(event.title)}</a></td>
          <td class="num ${cls(event.mv_change_20d)}">${fmt(event.mv_change_20d)}</td>
          <td>${htmlEscape(event.evidence_label || '')}</td>
        </tr>
      `).join('')}</tbody></table></div>`;
      els.eventMiniTable.querySelectorAll('.mini-event').forEach(link => {
        link.addEventListener('click', event => {
          event.preventDefault();
          const selected = events.find(item => item.id === link.dataset.id);
          if (selected) addEvent(selected);
        });
      });
    }
    function eventRows() {
      return filteredEvents().slice(0, 500);
    }
    function renderEventTable() {
      const rows = eventRows();
      if (!rows.length) {
        els.eventTable.innerHTML = '<p class="empty">当前筛选无事件</p>';
        els.eventDrawer.innerHTML = '';
        return;
      }
      if (!selectedEventId || !rows.some(row => row.id === selectedEventId)) selectedEventId = rows[0].id;
      els.eventTable.innerHTML = `<table><thead><tr>
        <th style="width:42px;">+</th><th style="width:88px;">日期</th><th style="width:82px;">公司</th><th style="width:106px;">事件类型</th><th style="width:120px;">二级事件</th><th>事件标题</th><th class="num" style="width:86px;">5日变化</th><th class="num" style="width:86px;">20日变化</th><th class="num" style="width:86px;">60日变化</th><th class="num" style="width:78px;">CAR20</th><th style="width:96px;">来源</th><th style="width:84px;">RAG挂接</th><th style="width:66px;">链接</th>
      </tr></thead><tbody>${rows.map(event => `
        <tr class="${selectedEventId === event.id ? 'active-row' : ''}">
          <td><button class="icon add-event" data-id="${htmlEscape(event.id)}" type="button">+</button></td>
          <td>${htmlEscape(event.date)}</td>
          <td>${htmlEscape(event.company)}</td>
          <td>${htmlEscape(event.category)}</td>
          <td>${htmlEscape(event.subtype)}</td>
          <td><a href="#" class="event-detail" data-id="${htmlEscape(event.id)}">${htmlEscape(event.title)}</a></td>
          <td class="num ${cls(event.mv_change_5d)}">${fmt(event.mv_change_5d)}</td>
          <td class="num ${cls(event.mv_change_20d)}">${fmt(event.mv_change_20d)}</td>
          <td class="num ${cls(event.mv_change_60d)}">${fmt(event.mv_change_60d)}</td>
          <td class="num ${cls(event.car_20d)}">${pct(event.car_20d)}</td>
          <td>${htmlEscape(event.source_types || event.source_type || '')}</td>
          <td><span class="tag ${event.evidence_level}">${htmlEscape(event.evidence_label)}</span></td>
          <td>${event.source_url || event.evidence_url ? `<a href="${htmlEscape(event.source_url || event.evidence_url)}" target="_blank" rel="noreferrer">打开</a>` : ''}</td>
        </tr>
      `).join('')}</tbody></table>`;
      els.eventTable.querySelectorAll('.add-event').forEach(button => {
        button.addEventListener('click', () => {
          const event = events.find(item => item.id === button.dataset.id);
          if (event) addEvent(event);
        });
      });
      els.eventTable.querySelectorAll('.event-detail').forEach(link => {
        link.addEventListener('click', event => {
          event.preventDefault();
          selectedEventId = link.dataset.id;
          renderEventTable();
          renderDrawer();
        });
      });
      renderDrawer();
    }
    function renderDrawer() {
      const event = events.find(item => item.id === selectedEventId);
      if (!event) {
        els.eventDrawer.innerHTML = '';
        return;
      }
      els.eventDrawer.innerHTML = `
        <div>
          <h3>事件字段</h3>
          <p><strong>${htmlEscape(event.company)}</strong> · ${htmlEscape(event.date)} · ${htmlEscape(event.category)} / ${htmlEscape(event.subtype)}</p>
          <p style="margin-top:8px;">${htmlEscape(event.title)}</p>
          <p class="muted" style="margin-top:8px;">同组标题：${htmlEscape(event.titles_sample || '')}</p>
        </div>
        <div>
          <h3>窗口与来源字段</h3>
          <p>5 / 20 / 60 日市值变化：
            <span class="${cls(event.mv_change_5d)}">${fmt(event.mv_change_5d)}</span> /
            <span class="${cls(event.mv_change_20d)}">${fmt(event.mv_change_20d)}</span> /
            <span class="${cls(event.mv_change_60d)}">${fmt(event.mv_change_60d)}</span> 亿元
          </p>
          <p>CAR[0,+20]：<span class="${cls(event.car_20d)}">${pct(event.car_20d)}</span></p>
          <p>原始来源：${htmlEscape(event.source_types || event.source_type || '')}</p>
          <p>RAG挂接：<span class="tag ${event.evidence_level}">${htmlEscape(event.evidence_label)}</span> ${htmlEscape(event.evidence_source || '')}</p>
          <p style="margin-top:8px;">${event.source_url || event.evidence_url ? `<a href="${htmlEscape(event.source_url || event.evidence_url)}" target="_blank" rel="noreferrer">打开原始来源链接</a>` : ''}</p>
        </div>
      `;
    }
    function spark(rows) {
      if (!rows.length) return '';
      const w = 112;
      const h = 26;
      const min = Math.min(...rows.map(row => Number(row.total_mv_yi)));
      const max = Math.max(...rows.map(row => Number(row.total_mv_yi)));
      const minT = rows[0].t;
      const maxT = rows[rows.length - 1].t;
      const points = rows.map(row => [
        (row.t - minT) / Math.max(1, maxT - minT) * w,
        h - (Number(row.total_mv_yi) - min) / Math.max(1, max - min) * (h - 3) - 1,
      ]);
      return `<svg class="spark" viewBox="0 0 ${w} ${h}"><path d="${linePath(points)}" fill="none" stroke="#14866d" stroke-width="2"/></svg>`;
    }
    function renderCompanyMatrix() {
      const yiwei = companyStats('300590.SZ');
      const rows = companies.filter(company => selectedCompanies.has(company.ts_code)).map(company => [company, companyStats(company.ts_code)]).filter(([, stat]) => stat);
      els.companyMatrix.innerHTML = `<table><thead><tr>
        <th style="width:92px;">公司</th><th style="width:128px;">走势</th><th class="num">起始市值</th><th class="num">结束市值</th><th class="num">市值变化</th><th class="num">涨跌幅</th><th class="num">相对移为</th><th class="num">最大回撤</th><th class="num">事件数</th><th class="num">事件篮</th>
      </tr></thead><tbody>${rows.map(([company, stat]) => {
        const rel = yiwei && company.ts_code !== '300590.SZ' ? stat.ret - yiwei.ret : null;
        return `<tr class="${focusedCompany === company.ts_code ? 'active-row' : ''}">
          <td><a href="#" class="company-focus" data-code="${htmlEscape(company.ts_code)}">${htmlEscape(company.company)}</a></td>
          <td>${spark(stat.rows)}</td>
          <td class="num">${fmt(stat.start)}</td>
          <td class="num">${fmt(stat.end)}</td>
          <td class="num ${cls(stat.change)}">${fmt(stat.change)}</td>
          <td class="num ${cls(stat.ret)}">${pct(stat.ret)}</td>
          <td class="num ${cls(rel)}">${rel === null ? '基准' : pct(rel)}</td>
          <td class="num neg">${pct(stat.maxDrawdown)}</td>
          <td class="num">${stat.eventCount}</td>
          <td class="num">${stat.basketCount}</td>
        </tr>`;
      }).join('')}</tbody></table>`;
      els.companyMatrix.querySelectorAll('.company-focus').forEach(link => {
        link.addEventListener('click', event => {
          event.preventDefault();
          focusedCompany = link.dataset.code;
          activeView = 'marketView';
          setActiveView();
          renderAll();
        });
      });
    }
    function renderPeerChart() {
      const svg = els.peerChart;
      const width = svg.clientWidth || 980;
      const height = svg.clientHeight || 500;
      const margin = {left: 78, right: 42, top: 54, bottom: 64};
      const range = currentRange();
      const rangeLabel = `${dateStr(range[0])} 至 ${dateStr(range[1])}`;
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      const stats = companies.filter(company => selectedCompanies.has(company.ts_code)).map(company => [company, companyStats(company.ts_code)]).filter(([, stat]) => stat);
      if (!stats.length) {
        svg.innerHTML = '<text x="24" y="48" fill="#64748b">当前区间无公司数据</text>';
        return;
      }
      const xVals = stats.map(([, stat]) => Number(stat.ret || 0));
      const yVals = stats.map(([, stat]) => Math.abs(Number(stat.maxDrawdown || 0)));
      const maxSize = Math.max(...stats.map(([, stat]) => Number(stat.end || 0)), 1);
      const minX = Math.min(...xVals, 0) - .08;
      const maxX = Math.max(...xVals, 0) + .08;
      const maxY = Math.max(...yVals, .05) + .05;
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const x = value => margin.left + (value - minX) / Math.max(.001, maxX - minX) * plotW;
      const y = value => margin.top + (maxY - value) / Math.max(.001, maxY) * plotH;
      let body = `<rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="#fff" stroke="#edf1f5"/>`;
      for (let i = 0; i <= 5; i += 1) {
        const gx = margin.left + plotW * i / 5;
        const gy = margin.top + plotH * i / 5;
        const xv = minX + (maxX - minX) * i / 5;
        const yv = maxY - maxY * i / 5;
        body += `<line x1="${gx}" y1="${margin.top}" x2="${gx}" y2="${height - margin.bottom}" stroke="#edf1f5"/>`;
        body += `<line x1="${margin.left}" y1="${gy}" x2="${width - margin.right}" y2="${gy}" stroke="#edf1f5"/>`;
        body += `<text x="${gx}" y="${height - margin.bottom + 20}" fill="#64748b" font-size="11" text-anchor="middle">${pct(xv)}</text>`;
        body += `<text x="${margin.left - 10}" y="${gy + 4}" fill="#64748b" font-size="11" text-anchor="end">${pct(yv)}</text>`;
      }
      body += `<line x1="${x(0)}" y1="${margin.top}" x2="${x(0)}" y2="${height - margin.bottom}" stroke="#cbd5e1" stroke-dasharray="4 4"/>`;
      body += `<text x="${margin.left}" y="24" fill="#111827" font-size="14" font-weight="800">竞品区间对比</text>`;
      body += `<text x="${width - margin.right}" y="24" fill="#64748b" font-size="12" text-anchor="end">${rangeLabel}</text>`;
      body += `<text x="${margin.left + plotW / 2}" y="${height - 18}" fill="#334155" font-size="12" font-weight="700" text-anchor="middle">区间涨跌幅</text>`;
      body += `<text x="14" y="${margin.top + 14}" fill="#334155" font-size="12" font-weight="700">最大回撤</text>`;
      stats.sort((a, b) => Number(a[1].end) - Number(b[1].end)).forEach(([company, stat]) => {
        const radius = 8 + Math.sqrt(Number(stat.end || 0) / maxSize) * 24;
        const cx = x(Number(stat.ret || 0));
        const cy = y(Math.abs(Number(stat.maxDrawdown || 0)));
        const isYiwei = company.ts_code === '300590.SZ';
        body += `<circle class="peer-dot" data-code="${htmlEscape(company.ts_code)}" data-company="${htmlEscape(company.company)}" data-range="${htmlEscape(rangeLabel)}" data-ret="${pct(stat.ret)}" data-drawdown="${pct(stat.maxDrawdown)}" data-end="${fmt(stat.end)}" cx="${cx}" cy="${cy}" r="${radius}" fill="${colorByCode[company.ts_code]}" fill-opacity="${isYiwei ? .9 : .66}" stroke="${isYiwei ? '#7f1d1d' : colorByCode[company.ts_code]}" stroke-width="${isYiwei ? 3 : 1.2}"/>`;
        body += `<text x="${cx + radius + 5}" y="${cy + 4}" fill="${isYiwei ? '#7f1d1d' : '#334155'}" font-size="${isYiwei ? 13 : 11}" font-weight="${isYiwei ? 700 : 600}" stroke="#fff" stroke-width="3" paint-order="stroke">${htmlEscape(company.company)}</text>`;
      });
      svg.innerHTML = body;
      svg.querySelectorAll('.peer-dot').forEach(node => {
        node.addEventListener('click', () => {
          focusedCompany = node.dataset.code;
          renderAll();
        });
        node.addEventListener('mousemove', event => showTip(event, `<strong>${htmlEscape(node.dataset.company)}</strong><div>区间：${htmlEscape(node.dataset.range)}</div><div>区间涨跌幅：${htmlEscape(node.dataset.ret)}</div><div>最大回撤：${htmlEscape(node.dataset.drawdown)}</div><div>期末市值：${htmlEscape(node.dataset.end)} 亿元</div>`));
        node.addEventListener('mouseleave', hideTip);
      });
    }
    function renderBasket() {
      if (!basket.length) {
        els.basketList.innerHTML = '<p class="empty">在事件表或走势事件点点击 + 加入事件篮。</p>';
      } else {
        els.basketList.innerHTML = basket.map((event, index) => `<div class="event-card">
          <div class="row"><strong>E${index + 1}</strong><button class="icon remove-event" data-id="${htmlEscape(event.id)}" type="button">×</button></div>
          <p>${htmlEscape(event.company)} · ${htmlEscape(event.date)}</p>
          <p class="muted">${htmlEscape(event.category)} / ${htmlEscape(event.subtype)}</p>
          <p style="margin-top:5px;">${htmlEscape(event.title)}</p>
          <p class="muted">20日变化：<span class="${cls(event.mv_change_20d)}">${fmt(event.mv_change_20d)}</span> 亿元</p>
        </div>`).join('');
        els.basketList.querySelectorAll('.remove-event').forEach(button => {
          button.addEventListener('click', () => removeEvent(button.dataset.id));
        });
      }
      renderBasketMetrics();
    }
    function renderAlignedChart() {
      const svg = els.alignedChart;
      const width = svg.clientWidth || 980;
      const height = svg.clientHeight || 500;
      const margin = {left: 72, right: 42, top: 32, bottom: 58};
      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      if (!basket.length) {
        svg.innerHTML = '<text x="24" y="48" fill="#64748b">事件篮为空</text>';
        return;
      }
      const [before, after] = windowConfig();
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const x = day => margin.left + (day - before) / Math.max(1, after - before) * plotW;
      let min = Infinity;
      let max = -Infinity;
      const series = basket.slice(0, 10).map((event, index) => {
        const rows = (byCompany.get(event.ts_code) || []).filter(row => row.t >= addDays(event.t, before) && row.t <= addDays(event.t, after));
        const baseRow = closest(rows, event.t) || rows[0];
        const base = baseRow ? Number(baseRow.total_mv_yi) : 0;
        const points = rows.map(row => {
          const day = Math.round((row.t - event.t) / 86400000);
          const ret = base ? Number(row.total_mv_yi) / base - 1 : 0;
          min = Math.min(min, ret);
          max = Math.max(max, ret);
          return {day, ret, date: row.date};
        });
        return {event, index, points};
      });
      if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) { min = -.1; max = .1; }
      const pad = (max - min) * .1;
      min -= pad;
      max += pad;
      const y = value => margin.top + (max - value) / Math.max(.000001, max - min) * plotH;
      let body = `<rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="#fff" stroke="#edf1f5"/>`;
      for (let i = 0; i <= 5; i += 1) {
        const gy = margin.top + plotH * i / 5;
        const value = max - (max - min) * i / 5;
        body += `<line x1="${margin.left}" y1="${gy}" x2="${width - margin.right}" y2="${gy}" stroke="#edf1f5"/>`;
        body += `<text x="${margin.left - 8}" y="${gy + 4}" fill="#64748b" font-size="11" text-anchor="end">${pct(value)}</text>`;
      }
      body += `<line x1="${x(0)}" y1="${margin.top}" x2="${x(0)}" y2="${height - margin.bottom}" stroke="#b42318" stroke-dasharray="4 4"/>`;
      body += `<text x="${x(0) + 5}" y="${margin.top + 14}" fill="#b42318" font-size="12">T=0</text>`;
      series.forEach(item => {
        const points = item.points.map(point => [x(point.day), y(point.ret)]);
        body += `<path d="${linePath(points)}" fill="none" stroke="${colorByCode[item.event.ts_code] || colors[item.index % colors.length]}" stroke-width="2.3" opacity=".9"/>`;
        body += `<text x="${margin.left + 8}" y="${margin.top + 18 + item.index * 17}" fill="${colorByCode[item.event.ts_code] || colors[item.index % colors.length]}" font-size="12">E${item.index + 1} ${htmlEscape(item.event.company)}</text>`;
      });
      body += `<text x="${margin.left}" y="${height - 18}" fill="#334155" font-size="12">事件日相对天数：${before} 至 +${after}</text>`;
      svg.innerHTML = body;
    }
    function renderSpillover() {
      const selected = basket.map(event => ({event, spill: spilloverById.get(event.id) || spilloverById.get(event.event_id)})).filter(item => item.spill);
      if (!selected.length) {
        els.spilloverDetail.innerHTML = '<p class="empty">事件篮中无可匹配外溢字段的竞品事件。</p>';
        return;
      }
      els.spilloverDetail.innerHTML = `<table><thead><tr><th>事件</th><th class="num">竞品20日</th><th class="num">移为同期20日</th><th class="num">移为CAR20</th></tr></thead><tbody>${selected.map(item => `
        <tr>
          <td>${htmlEscape(item.event.company)} · ${htmlEscape(item.event.date)}</td>
          <td class="num ${cls(item.spill.peer_mv_return_20d)}">${pct(item.spill.peer_mv_return_20d)}</td>
          <td class="num ${cls(item.spill.yiwei_mv_return_20d)}">${pct(item.spill.yiwei_mv_return_20d)}</td>
          <td class="num ${cls(item.spill.yiwei_car_20d)}">${pct(item.spill.yiwei_car_20d)}</td>
        </tr>
      `).join('')}</tbody></table>`;
    }
    function renderBasketMetrics() {
      if (!basket.length) {
        els.basketMetrics.innerHTML = '<p class="empty">事件篮为空</p>';
        return;
      }
      const changes = basket.map(event => Number(event.mv_change_20d)).filter(Number.isFinite);
      const car = basket.map(event => Number(event.car_20d)).filter(Number.isFinite);
      const avg = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
      els.basketMetrics.innerHTML = `
        <p>事件数：${basket.length}</p>
        <p>20日市值变化均值：<span class="${cls(avg(changes))}">${fmt(avg(changes))}</span> 亿元</p>
        <p>CAR[0,+20]均值：<span class="${cls(avg(car))}">${pct(avg(car))}</span></p>
      `;
    }
    function exportCsv(filename, rows, columns) {
      const escapeCsv = value => `"${String(value ?? '').replace(/"/g, '""')}"`;
      const lines = [columns.map(escapeCsv).join(',')].concat(rows.map(row => columns.map(column => escapeCsv(row[column])).join(',')));
      const blob = new Blob(['\ufeff' + lines.join('\n')], {type: 'text/csv;charset=utf-8'});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    }
    function isNumeric(value) {
      return value !== null && value !== '' && Number.isFinite(Number(value));
    }
    function formatCell(value) {
      if (value === null || value === undefined) return '';
      if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3);
      return String(value);
    }
    function currentTopRows() {
      const topic = topTables[selectedTopIndex] || {rows: []};
      const q = els.topSearch.value.trim().toLowerCase();
      let rows = topic.rows || [];
      if (q) {
        rows = rows.filter(row => Object.values(row).join(' ').toLowerCase().includes(q));
      }
      if (topSort.column) {
        rows = rows.slice().sort((a, b) => {
          const av = a[topSort.column];
          const bv = b[topSort.column];
          if (isNumeric(av) && isNumeric(bv)) return (Number(av) - Number(bv)) * topSort.dir;
          return String(av ?? '').localeCompare(String(bv ?? ''), 'zh-CN') * topSort.dir;
        });
      }
      return rows;
    }
    function renderTopTopics() {
      if (!topTables.length) {
        els.topTopics.innerHTML = '<p class="empty">暂无专题表</p>';
        return;
      }
      els.topTopics.innerHTML = topTables.map((topic, index) => `<button class="${index === selectedTopIndex ? 'active' : ''}" data-index="${index}" type="button">${htmlEscape(topic.label)}</button>`).join('');
      els.topTopics.querySelectorAll('button').forEach(button => {
        button.addEventListener('click', () => {
          selectedTopIndex = Number(button.dataset.index);
          topSort = {column: '', dir: 1};
          els.topSearch.value = '';
          renderTopTopics();
          renderTopTable();
        });
      });
    }
    function renderTopTable() {
      const topic = topTables[selectedTopIndex];
      if (!topic) {
        els.topTitle.textContent = '';
        els.topSource.textContent = '';
        els.topTable.innerHTML = '<p class="empty">暂无专题表</p>';
        return;
      }
      const rows = currentTopRows();
      const columns = topic.columns || [];
      els.topTitle.textContent = topic.label || '';
      els.topSource.textContent = `来源文件：${topic.source || ''}；当前显示：${rows.length} 行`;
      if (!columns.length || !rows.length) {
        els.topTable.innerHTML = '<p class="empty">暂无数据</p>';
        return;
      }
      const header = columns.map(column => `<th data-column="${htmlEscape(column)}">${htmlEscape(topic.headers[column] || column)}${topSort.column === column ? (topSort.dir > 0 ? ' ↑' : ' ↓') : ''}</th>`).join('');
      const body = rows.map(row => `<tr>${columns.map(column => {
        const value = row[column];
        return `<td class="${isNumeric(value) ? 'num' : ''}">${htmlEscape(formatCell(value))}</td>`;
      }).join('')}</tr>`).join('');
      els.topTable.innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
      els.topTable.querySelectorAll('th').forEach(th => {
        th.addEventListener('click', () => {
          const column = th.dataset.column;
          if (topSort.column === column) topSort.dir *= -1;
          else topSort = {column, dir: 1};
          renderTopTable();
        });
      });
    }
    function exportTopTable() {
      const topic = topTables[selectedTopIndex];
      if (!topic) return;
      const columns = topic.columns || [];
      const rows = currentTopRows();
      const headers = columns.map(column => topic.headers[column] || column);
      const exportRows = rows.map(row => Object.fromEntries(headers.map((header, index) => [header, formatCell(row[columns[index]])])));
      exportCsv(`${topic.label || 'top_topic'}.csv`, exportRows, headers);
    }
    function setActiveView() {
      document.querySelectorAll('.tabs button').forEach(button => button.classList.toggle('active', button.dataset.view === activeView));
      document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view.id === activeView));
    }
    function renderAll() {
      populateCategories();
      els.month.disabled = els.period.value === 'custom';
      els.start.disabled = els.period.value !== 'custom';
      els.end.disabled = els.period.value !== 'custom';
      els.before.disabled = els.windowSize.value !== 'custom';
      els.after.disabled = els.windowSize.value !== 'custom';
      renderKpis();
      renderMarketChart();
      renderFocusInfo();
      renderMiniEvents();
      renderEventTable();
      renderPeerChart();
      renderCompanyMatrix();
      renderBasket();
      renderAlignedChart();
      renderSpillover();
      renderTopTopics();
      renderTopTable();
    }

    document.querySelectorAll('.tabs button').forEach(button => {
      button.addEventListener('click', () => {
        activeView = button.dataset.view;
        setActiveView();
        renderAll();
      });
    });
    document.querySelectorAll('[data-market-mode]').forEach(button => {
      button.addEventListener('click', () => {
        marketMode = button.dataset.marketMode;
        document.querySelectorAll('[data-market-mode]').forEach(item => item.classList.toggle('active', item === button));
        renderAll();
      });
    });
    document.querySelectorAll('[data-market-unit]').forEach(button => {
      button.addEventListener('click', () => {
        marketUnit = button.dataset.marketUnit;
        document.querySelectorAll('[data-market-unit]').forEach(item => item.classList.toggle('active', item === button));
        renderAll();
      });
    });
    [els.period, els.month, els.start, els.end, els.windowSize, els.before, els.after, els.category, els.subtype, els.search].forEach(input => {
      input.addEventListener('input', () => {
        if (input === els.period) populateMonths();
        if (input === els.category) els.subtype.value = '';
        renderAll();
      });
    });
    document.getElementById('clearBasket').addEventListener('click', () => {
      basket.splice(0, basket.length);
      renderAll();
    });
    document.getElementById('exportEvents').addEventListener('click', () => {
      const rows = eventRows();
      exportCsv('market_impact_filtered_events.csv', rows, ['date', 'company', 'category', 'subtype', 'title', 'mv_change_5d', 'mv_change_20d', 'mv_change_60d', 'car_20d', 'source_types', 'evidence_label', 'source_url', 'evidence_url']);
    });
    els.topSearch.addEventListener('input', renderTopTable);
    document.getElementById('exportTop').addEventListener('click', exportTopTable);
    window.addEventListener('resize', renderAll);

    initCompanies();
    populateMonths();
    setActiveView();
    renderAll();
  </script>
</body>
</html>
"""


def main() -> int:
    workbench_payload: dict[str, Any] = {
        "companies": [
            {"company": company, "ts_code": ts_code, "symbol": symbol} for company, ts_code, symbol in COMPANIES
        ],
        "marketRows": load_market_rows(),
        "events": load_workbench_events(),
        "spilloverRows": load_spillover_rows(),
        "topTables": build_top_payload()["tables"],
    }
    WORKBENCH_OUTPUT.write_text(build_workbench_html(workbench_payload), encoding="utf-8")
    sys.stdout.write(
        "\n".join(
            [
                f"workbench={WORKBENCH_OUTPUT}",
                f"market_rows={len(workbench_payload['marketRows'])}",
                f"event_rows={len(workbench_payload['events'])}",
                f"spillover_rows={len(workbench_payload['spilloverRows'])}",
                f"top_tables={len(workbench_payload['topTables'])}",
            ]
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""生成管理层可浏览的数据验收 HTML 面板。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
VALIDATION_DIR = PROCESSED_DIR / "validation"
RAW_TUSHARE_DIR = DATA_DIR / "raw/tushare"

QUALITY_CHECKS_PATH = VALIDATION_DIR / "data_quality_checks.csv"
CAR_RECHECK_PATH = VALIDATION_DIR / "car_recheck_samples.csv"
COLLECTION_INVENTORY_PATH = DATA_DIR / "summary/collection_inventory.csv"
CFO_CHAIN_PATH = PROCESSED_DIR / "cfo_event_evidence_chain.csv"
ML_OVERLAP_PATH = PROCESSED_DIR / "ml_readiness/event_overlap_summary.csv"

OUTPUT_HTML = VALIDATION_DIR / "data_quality_dashboard.html"
OUTPUT_SUMMARY = VALIDATION_DIR / "data_quality_summary.csv"

COMPANIES = [
    ("移为通信", "300590.SZ", "300590"),
    ("移远通信", "603236.SH", "603236"),
    ("高新兴", "300098.SZ", "300098"),
    ("广和通", "300638.SZ", "300638"),
    ("日海智能", "002313.SZ", "002313"),
    ("锐明技术", "002970.SZ", "002970"),
    ("有方科技", "688159.SH", "688159"),
    ("美格智能", "002881.SZ", "002881"),
    ("博实结", "301608.SZ", "301608"),
]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def number(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return math.nan
    return parsed if math.isfinite(parsed) else math.nan


def pct(value: object) -> float | None:
    parsed = number(value)
    if math.isnan(parsed):
        return None
    return round(parsed * 100, 2)


def compact(value: object) -> str:
    return " ".join(str(value or "").split())


def load_summary() -> tuple[pd.DataFrame, dict[str, object]]:
    checks = read_csv(QUALITY_CHECKS_PATH)
    car = read_csv(CAR_RECHECK_PATH)
    inventory = read_csv(COLLECTION_INVENTORY_PATH)
    chain = read_csv(CFO_CHAIN_PATH)

    check_total = len(checks)
    check_passed = int((checks["是否通过"] == "通过").sum())
    car_total = len(car)
    car_passed = int((car["复核状态"] == "pass").sum())
    event_groups = len(chain)
    company_count = chain["公司"].nunique()

    inventory_rows = pd.to_numeric(inventory["rows"], errors="coerce")
    collected_rows = int(inventory_rows.sum(skipna=True))
    ok_assets = int((inventory["status"] == "ok").sum())

    summary_rows = [
        {
            "指标": "公司数量",
            "数值": company_count,
            "单位": "家公司",
            "口径": "事件主表中的唯一公司数",
            "来源文件": str(CFO_CHAIN_PATH.relative_to(PROJECT_DIR)),
        },
        {
            "指标": "分析事件组",
            "数值": event_groups,
            "单位": "组",
            "口径": "按公司+日期+一级分类聚合后的事件组",
            "来源文件": str(CFO_CHAIN_PATH.relative_to(PROJECT_DIR)),
        },
        {
            "指标": "数据检查项",
            "数值": f"{check_passed}/{check_total}",
            "单位": "项",
            "口径": "data_quality_checks.csv 中是否通过=通过的项目数",
            "来源文件": str(QUALITY_CHECKS_PATH.relative_to(PROJECT_DIR)),
        },
        {
            "指标": "CAR抽样复算",
            "数值": f"{car_passed}/{car_total}",
            "单位": "条",
            "口径": "car_recheck_samples.csv 中复核状态=pass的样本数",
            "来源文件": str(CAR_RECHECK_PATH.relative_to(PROJECT_DIR)),
        },
        {
            "指标": "采集资产",
            "数值": ok_assets,
            "单位": "项",
            "口径": "collection_inventory.csv 中 status=ok 的资产数",
            "来源文件": str(COLLECTION_INVENTORY_PATH.relative_to(PROJECT_DIR)),
        },
        {
            "指标": "采集记录行数",
            "数值": collected_rows,
            "单位": "行",
            "口径": "collection_inventory.csv 中 rows 数值求和",
            "来源文件": str(COLLECTION_INVENTORY_PATH.relative_to(PROJECT_DIR)),
        },
    ]
    summary = pd.DataFrame(summary_rows)

    payload = {
        "summary": summary_rows,
        "checks": checks.to_dict(orient="records"),
        "carSamples": build_car_samples(car),
        "inventoryBySource": build_inventory_by_source(inventory),
        "inventoryTopDatasets": build_inventory_top_datasets(inventory),
        "marketRows": build_market_rows(),
        "eventsByCompany": build_events_by_company(chain),
        "eventDistribution": build_event_distribution(chain),
        "eventRows": build_event_rows(chain),
        "overlapRows": build_overlap_rows(),
    }
    return summary, payload


def parse_trade_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")


def build_market_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for company, ts_code, symbol in COMPANIES:
        path = RAW_TUSHARE_DIR / "daily_basic" / f"{ts_code}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype={"trade_date": str})
        frame["trade_dt"] = parse_trade_date(frame["trade_date"])
        frame["total_mv_yi"] = pd.to_numeric(frame["total_mv"], errors="coerce") / 10000
        frame = frame.dropna(subset=["trade_dt", "total_mv_yi"]).sort_values("trade_dt")
        frame["week"] = frame["trade_dt"].dt.to_period("W-FRI").astype(str)
        weekly_indexes = frame.groupby("week", sort=False).tail(1).index
        frame = frame.loc[weekly_indexes.union(pd.Index([frame.index[-1]]))].sort_values("trade_dt")
        for _, row in frame.iterrows():
            rows.append(
                {
                    "company": company,
                    "ts_code": ts_code,
                    "symbol": symbol,
                    "date": row["trade_dt"].strftime("%Y-%m-%d"),
                    "total_mv_yi": round(float(row["total_mv_yi"]), 4),
                }
            )
    return rows


def build_car_samples(car: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "事件日期",
        "公司",
        "事件类型",
        "事件标题",
        "复核状态",
        "窗口覆盖_p0_p20",
        "复算CAR_p0_p20",
        "原表CAR_p0_p20",
        "CAR差异_p0_p20",
        "复算异常市值影响_亿元_p0_p20",
        "原表异常市值影响_亿元_p0_p20",
    ]
    rows = []
    for _, row in car.head(80).iterrows():
        item = {column: compact(row.get(column)) for column in columns}
        for column in [
            "复算CAR_p0_p20",
            "原表CAR_p0_p20",
            "CAR差异_p0_p20",
            "复算异常市值影响_亿元_p0_p20",
            "原表异常市值影响_亿元_p0_p20",
        ]:
            value = number(item[column])
            item[column] = None if math.isnan(value) else round(value, 6)
        rows.append(item)
    return rows


def build_inventory_by_source(inventory: pd.DataFrame) -> list[dict[str, object]]:
    frame = inventory.copy()
    frame["rows_num"] = pd.to_numeric(frame["rows"], errors="coerce").fillna(0)
    grouped = (
        frame.groupby("source", dropna=False)
        .agg(asset_count=("dataset", "count"), row_count=("rows_num", "sum"))
        .reset_index()
        .sort_values("row_count", ascending=False)
    )
    return [
        {
            "source": compact(row["source"]) or "未标注",
            "asset_count": int(row["asset_count"]),
            "row_count": int(row["row_count"]),
        }
        for _, row in grouped.iterrows()
    ]


def build_inventory_top_datasets(inventory: pd.DataFrame) -> list[dict[str, object]]:
    frame = inventory.copy()
    frame["rows_num"] = pd.to_numeric(frame["rows"], errors="coerce").fillna(0)
    frame = frame.sort_values("rows_num", ascending=False).head(12)
    return [
        {
            "source": compact(row["source"]),
            "dataset": compact(row["dataset"]),
            "company": compact(row["company_or_scope"]),
            "symbol": compact(row["symbol"]),
            "rows": int(row["rows_num"]),
            "status": compact(row["status"]),
        }
        for _, row in frame.iterrows()
    ]


def build_events_by_company(chain: pd.DataFrame) -> list[dict[str, object]]:
    grouped = chain.groupby("公司", dropna=False).size().reset_index(name="event_group_count")
    grouped = grouped.sort_values("event_group_count", ascending=False)
    return [
        {
            "company": compact(row["公司"]) or "未标注",
            "event_group_count": int(row["event_group_count"]),
        }
        for _, row in grouped.iterrows()
    ]


def build_event_distribution(chain: pd.DataFrame) -> list[dict[str, object]]:
    grouped = (
        chain.groupby(["公司", "一级分类"], dropna=False)
        .size()
        .reset_index(name="event_group_count")
        .sort_values("event_group_count", ascending=False)
    )
    return [
        {
            "company": compact(row["公司"]),
            "category": compact(row["一级分类"]) or "未分类",
            "event_group_count": int(row["event_group_count"]),
        }
        for _, row in grouped.iterrows()
    ]


def build_event_rows(chain: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "事件日期",
        "公司",
        "一级分类",
        "二级事件",
        "代表事件标题",
        "20日客观市值变化_亿元",
        "20日相对竞品市值变化_亿元",
        "事件来源链接",
    ]
    frame = chain.copy()
    frame["abs_change"] = pd.to_numeric(frame["20日客观市值变化_亿元"], errors="coerce").abs()
    frame = frame.sort_values("abs_change", ascending=False).head(300)
    rows = []
    for _, row in frame.iterrows():
        item = {column: compact(row.get(column)) for column in columns}
        for column in ["20日客观市值变化_亿元", "20日相对竞品市值变化_亿元"]:
            value = number(item[column])
            item[column] = None if math.isnan(value) else round(value, 4)
        rows.append(item)
    return rows


def build_overlap_rows() -> list[dict[str, object]]:
    if not ML_OVERLAP_PATH.exists():
        return []
    frame = read_csv(ML_OVERLAP_PATH)
    return frame.head(80).to_dict(orient="records")


def build_html(payload: dict[str, object]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>市值影响研究数据验收面板</title>
  <style>
    :root {{
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #e5e7eb;
      --line-strong: #cbd5e1;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --red: #b91c1c;
      --blue: #2563eb;
      --green: #15803d;
      --amber: #b45309;
      --slate: #475569;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif;
      color: var(--ink);
      background: var(--bg);
      font-size: 14px;
      letter-spacing: 0;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 18px 24px 14px;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 18px;
    }}
    h1 {{ margin: 0; font-size: 22px; line-height: 1.25; }}
    h2 {{ margin: 0; font-size: 18px; line-height: 1.3; }}
    h3 {{ margin: 0; font-size: 15px; line-height: 1.3; }}
    p {{ margin: 0; line-height: 1.55; }}
    .muted {{ color: var(--muted); }}
    .source-note {{ font-size: 12px; margin-top: 6px; }}
    main {{ padding: 16px 20px 28px; display: grid; gap: 14px; }}
    .controls {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      align-items: end;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }}
    .control-group {{ display: grid; gap: 5px; min-width: 180px; }}
    label {{ font-size: 12px; color: var(--muted); font-weight: 700; }}
    select, input {{
      height: 32px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 4px 9px;
      font: inherit;
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }}
    .kpi {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-height: 92px;
      padding: 12px;
      display: grid;
      align-content: space-between;
    }}
    .kpi .label {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .kpi .value {{ font-size: 24px; line-height: 1.15; font-weight: 800; margin-top: 8px; }}
    .kpi .unit {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }}
    .panel-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 10px;
    }}
    .grid-2 {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }}
    .chart-main {{ min-height: 500px; }}
    .chart-secondary {{ min-height: 440px; }}
    svg {{ width: 100%; display: block; }}
    .axis text {{ fill: var(--muted); font-size: 12px; }}
    .grid-line {{ stroke: var(--line); stroke-width: 1; }}
    .zero-line {{ stroke: var(--line-strong); stroke-width: 1.5; }}
    .bar-bg {{ fill: #eef2f7; }}
    .bar-main {{ fill: var(--blue); }}
    .bar-aux {{ fill: rgba(37, 99, 235, .38); }}
    .bar-green {{ fill: var(--green); }}
    .bar-amber {{ fill: var(--amber); }}
    .bar-slate {{ fill: var(--slate); }}
    .line-main {{ stroke: var(--blue); stroke-width: 3; fill: none; }}
    .line-peer {{ stroke: var(--slate); stroke-width: 1.8; fill: none; opacity: .46; }}
    .line-selected {{ stroke: var(--red); stroke-width: 3.4; fill: none; opacity: .96; }}
    .line-hit {{ fill: none; stroke: transparent; stroke-width: 14; cursor: crosshair; }}
    .market-point {{ fill: var(--red); stroke: #fff; stroke-width: 1.5; }}
    .legend {{ display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }}
    .legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
    .swatch {{ width: 12px; height: 8px; border-radius: 2px; display: inline-block; }}
    .tooltip {{
      position: fixed;
      display: none;
      pointer-events: none;
      z-index: 20;
      max-width: 340px;
      background: #fff;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      box-shadow: 0 12px 26px rgba(15, 23, 42, .08);
      padding: 9px 10px;
      font-size: 13px;
      line-height: 1.45;
    }}
    .table-wrap {{ overflow: auto; max-height: 520px; border: 1px solid var(--line); border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }}
    th, td {{ padding: 8px 9px; border-bottom: 1px solid var(--line); vertical-align: top; word-break: break-word; }}
    th {{ background: #f8fafc; color: #475569; text-align: left; position: sticky; top: 0; z-index: 1; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .status {{
      display: inline-flex;
      min-width: 42px;
      justify-content: center;
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      border: 1px solid var(--line-strong);
    }}
    .status.ok {{ color: var(--green); background: #f0fdf4; border-color: #bbf7d0; }}
    .status.other {{ color: var(--slate); background: #f8fafc; }}
    @media (max-width: 1240px) {{
      .kpis {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .grid-2 {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 760px) {{
      header {{ display: block; padding: 14px; }}
      main {{ padding: 12px; }}
      .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .controls {{ gap: 10px; }}
      .control-group {{ min-width: 100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>市值影响研究数据验收面板</h1>
      <p class="muted source-note">数据来源：本地已生成 CSV、JSONL、HTML 和校验报告；页面仅展示数据规模、事件分布和计算复核状态。</p>
    </div>
    <p class="muted source-note">生成文件：data/processed/validation/data_quality_dashboard.html</p>
  </header>
  <main>
    <section class="controls" aria-label="筛选控件">
      <div class="control-group">
        <label for="companySelect">公司</label>
        <select id="companySelect"></select>
      </div>
      <div class="control-group">
        <label for="categorySelect">事件分类</label>
        <select id="categorySelect"></select>
      </div>
    </section>

    <section class="kpis" id="kpiGrid" aria-label="核心数量"></section>

    <section class="panel chart-main">
      <div class="panel-head">
        <div>
          <h2>总市值走势</h2>
          <p class="muted source-note">单位：亿元；使用 Tushare daily_basic.total_mv，原始总市值除以 10000。</p>
        </div>
        <div class="legend">
          <span><i class="swatch" style="background:var(--red)"></i>当前选择/移为通信</span>
          <span><i class="swatch" style="background:var(--slate);opacity:.46"></i>其他公司</span>
        </div>
      </div>
      <svg id="marketChart" height="540" role="img" aria-label="总市值走势"></svg>
    </section>

    <section class="panel chart-main">
      <div class="panel-head">
        <div>
          <h2>公司事件组数量</h2>
          <p class="muted source-note">单位：事件组；按公司+日期+一级分类聚合。</p>
        </div>
        <div class="legend">
          <span><i class="swatch" style="background:var(--blue)"></i>事件组</span>
        </div>
      </div>
      <svg id="companyChart" height="500" role="img" aria-label="按公司展示事件组数量"></svg>
    </section>

    <section class="grid-2">
      <div class="panel chart-secondary">
        <div class="panel-head">
          <div>
            <h2>事件组分类分布</h2>
            <p class="muted source-note">单位：事件组；筛选公司后更新。</p>
          </div>
        </div>
        <svg id="categoryChart" height="440" role="img" aria-label="事件分类分布"></svg>
      </div>
      <div class="panel chart-secondary">
        <div class="panel-head">
          <div>
            <h2>采集资产来源</h2>
            <p class="muted source-note">单位：记录行数；按 source 汇总。</p>
          </div>
        </div>
        <svg id="inventoryChart" height="440" role="img" aria-label="采集资产来源"></svg>
      </div>
    </section>

    <section class="grid-2">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>基础检查项</h2>
            <p class="muted source-note">来源：data_quality_checks.csv</p>
          </div>
        </div>
        <div class="table-wrap"><table id="checksTable"></table></div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>CAR 抽样复算</h2>
            <p class="muted source-note">单位：CAR 为比例，异常市值影响为亿元；表内展示 [0,+20] 窗口。</p>
          </div>
        </div>
        <div class="table-wrap"><table id="carTable"></table></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>事件组明细抽样</h2>
          <p class="muted source-note">按 20 日客观市值变化绝对值排序取前 300 条，可按上方控件筛选。</p>
        </div>
      </div>
      <div class="table-wrap"><table id="eventTable"></table></div>
    </section>
  </main>
  <div class="tooltip" id="tooltip"></div>
  <script>
    const DATA = {payload_json};
    const fmt = new Intl.NumberFormat('zh-CN');
    const tip = document.getElementById('tooltip');
    const state = {{ company: '全部', category: '全部' }};

    function showTip(html, event) {{
      tip.innerHTML = html;
      tip.style.display = 'block';
      const pad = 14;
      const width = tip.offsetWidth || 300;
      const height = tip.offsetHeight || 120;
      let left = event.clientX + pad;
      let top = event.clientY + pad;
      if (left + width > window.innerWidth - 8) left = event.clientX - width - pad;
      if (top + height > window.innerHeight - 8) top = event.clientY - height - pad;
      tip.style.left = `${{Math.max(8, left)}}px`;
      tip.style.top = `${{Math.max(8, top)}}px`;
    }}
    function hideTip() {{ tip.style.display = 'none'; }}
    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}
    function n(value) {{ return Number.isFinite(Number(value)) ? Number(value) : 0; }}
    function unique(values) {{ return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-CN')); }}

    function initControls() {{
      const companies = unique(DATA.eventRows.map(d => d['公司']));
      const categories = unique(DATA.eventRows.map(d => d['一级分类']));
      fillSelect('companySelect', ['全部', ...companies], '全部');
      fillSelect('categorySelect', ['全部', ...categories], '全部');
      document.getElementById('companySelect').addEventListener('change', e => {{ state.company = e.target.value; render(); }});
      document.getElementById('categorySelect').addEventListener('change', e => {{ state.category = e.target.value; render(); }});
    }}
    function fillSelect(id, values, selected) {{
      const el = document.getElementById(id);
      el.innerHTML = values.map(v => `<option value="${{esc(v)}}" ${{v === selected ? 'selected' : ''}}>${{esc(v)}}</option>`).join('');
    }}

    function renderKpis() {{
      const byName = Object.fromEntries(DATA.summary.map(d => [d['指标'], d]));
      const items = [
        byName['公司数量'],
        byName['分析事件组'],
        byName['数据检查项'],
        byName['CAR抽样复算'],
        byName['采集资产'],
        byName['采集记录行数'],
      ].filter(Boolean);
      document.getElementById('kpiGrid').innerHTML = items.map(item => `
        <div class="kpi">
          <div>
            <div class="label">${{esc(item['指标'])}}</div>
            <div class="value">${{esc(item['数值'])}}</div>
          </div>
          <div class="unit">${{esc(item['单位'])}}</div>
        </div>
      `).join('');
    }}

    function byCompany(rows) {{
      const grouped = new Map();
      rows.forEach(row => {{
        if (!grouped.has(row.company)) grouped.set(row.company, []);
        grouped.get(row.company).push(row);
      }});
      grouped.forEach(values => values.sort((a, b) => a.date.localeCompare(b.date)));
      return grouped;
    }}

    function renderMarketChart() {{
      const svg = document.getElementById('marketChart');
      const width = svg.clientWidth || 1100;
      const height = 540;
      const margin = {{ top: 18, right: 38, bottom: 42, left: 72 }};
      const innerW = width - margin.left - margin.right;
      const innerH = height - margin.top - margin.bottom;
      const grouped = byCompany(DATA.marketRows);
      const selected = state.company === '全部' ? '移为通信' : state.company;
      const allRows = Array.from(grouped.values()).flat();
      if (!allRows.length) {{
        svg.innerHTML = '<text x="20" y="40" fill="#6b7280">无市值数据</text>';
        return;
      }}
      const minDate = Math.min(...allRows.map(d => Date.parse(d.date)));
      const maxDate = Math.max(...allRows.map(d => Date.parse(d.date)));
      const maxValue = Math.max(...allRows.map(d => n(d.total_mv_yi)), 1);
      const x = date => margin.left + (Date.parse(date) - minDate) / Math.max(1, maxDate - minDate) * innerW;
      const y = value => margin.top + innerH - n(value) / maxValue * innerH;
      const line = rows => rows.map((d, i) => `${{i === 0 ? 'M' : 'L'}}${{x(d.date).toFixed(1)}},${{y(d.total_mv_yi).toFixed(1)}}`).join(' ');
      const yearTicks = [];
      const startYear = new Date(minDate).getFullYear();
      const endYear = new Date(maxDate).getFullYear();
      for (let year = startYear; year <= endYear; year += Math.max(1, Math.ceil((endYear - startYear + 1) / 7))) {{
        yearTicks.push(new Date(`${{year}}-01-01`).getTime());
      }}
      let html = '';
      for (let i = 0; i <= 5; i++) {{
        const value = maxValue * i / 5;
        const yy = margin.top + innerH - innerH * i / 5;
        html += `<line class="grid-line" x1="${{margin.left}}" x2="${{margin.left + innerW}}" y1="${{yy}}" y2="${{yy}}"></line>`;
        html += `<text x="${{margin.left - 10}}" y="${{yy + 4}}" text-anchor="end" fill="#6b7280" font-size="12">${{fmt.format(Math.round(value))}}</text>`;
      }}
      yearTicks.forEach(tick => {{
        if (tick < minDate || tick > maxDate) return;
        const xx = margin.left + (tick - minDate) / Math.max(1, maxDate - minDate) * innerW;
        html += `<line class="grid-line" x1="${{xx}}" x2="${{xx}}" y1="${{margin.top}}" y2="${{margin.top + innerH}}"></line>`;
        html += `<text x="${{xx}}" y="${{height - 14}}" text-anchor="middle" fill="#6b7280" font-size="12">${{new Date(tick).getFullYear()}}</text>`;
      }});
      grouped.forEach((rows, company) => {{
        if (company !== selected) html += `<path class="line-peer" d="${{line(rows)}}"></path>`;
      }});
      const selectedRows = grouped.get(selected) || grouped.get('移为通信') || [];
      if (selectedRows.length) {{
        html += `<path class="line-selected" d="${{line(selectedRows)}}"></path>`;
        html += `<path class="line-hit" d="${{line(selectedRows)}}"></path>`;
        const last = selectedRows[selectedRows.length - 1];
        html += `<circle class="market-point" cx="${{x(last.date)}}" cy="${{y(last.total_mv_yi)}}" r="4"></circle>`;
        html += `<text x="${{Math.min(x(last.date) + 8, margin.left + innerW - 88)}}" y="${{y(last.total_mv_yi) - 8}}" fill="#991b1b" font-size="12" font-weight="700">${{esc(selected)}} ${{fmt.format(Math.round(last.total_mv_yi))}}亿元</text>`;
      }}
      html += `<text x="${{margin.left}}" y="${{margin.top - 3}}" fill="#6b7280" font-size="12">亿元</text>`;
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = html;
      svg.querySelectorAll('.line-hit').forEach(el => {{
        el.addEventListener('mousemove', event => {{
          const rows = selectedRows;
          if (!rows.length) return;
          const rect = svg.getBoundingClientRect();
          const px = event.clientX - rect.left;
          const ratio = Math.max(0, Math.min(1, (px - margin.left) / innerW));
          const target = minDate + ratio * (maxDate - minDate);
          let nearest = rows[0];
          let best = Math.abs(Date.parse(nearest.date) - target);
          rows.forEach(row => {{
            const diff = Math.abs(Date.parse(row.date) - target);
            if (diff < best) {{ nearest = row; best = diff; }}
          }});
          showTip(`<strong>${{esc(selected)}}</strong><br>日期：${{nearest.date}}<br>总市值：${{fmt.format(Math.round(Number(nearest.total_mv_yi) * 100) / 100)}} 亿元`, event);
        }});
        el.addEventListener('mouseleave', hideTip);
      }});
    }}

    function renderCompanyChart() {{
      const svg = document.getElementById('companyChart');
      const rows = DATA.eventsByCompany;
      const width = svg.clientWidth || 1000;
      const height = 500;
      const margin = {{ top: 18, right: 38, bottom: 34, left: 92 }};
      const innerW = width - margin.left - margin.right;
      const rowH = Math.min(42, (height - margin.top - margin.bottom) / Math.max(1, rows.length));
      const max = Math.max(...rows.map(d => n(d.event_group_count)), 1);
      const ticks = 5;
      let html = `<g transform="translate(${{margin.left}},${{margin.top}})">`;
      for (let i = 0; i <= ticks; i++) {{
        const x = innerW * i / ticks;
        const value = max * i / ticks;
        html += `<line class="grid-line" x1="${{x}}" x2="${{x}}" y1="0" y2="${{rowH * rows.length}}"></line>`;
        html += `<text x="${{x}}" y="${{rowH * rows.length + 24}}" text-anchor="middle" fill="#6b7280" font-size="12">${{fmt.format(Math.round(value))}}</text>`;
      }}
      rows.forEach((d, i) => {{
        const y = i * rowH + 7;
        const totalW = innerW * n(d.event_group_count) / max;
        html += `<text x="-12" y="${{y + 17}}" text-anchor="end" fill="#475569" font-size="12">${{esc(d.company)}}</text>`;
        html += `<rect class="bar-bg" x="0" y="${{y}}" width="${{totalW}}" height="22" rx="4"></rect>`;
        html += `<rect class="bar-main" x="0" y="${{y}}" width="${{totalW}}" height="22" rx="4"
          data-tip="${{esc(`<strong>${{d.company}}</strong><br>事件组：${{fmt.format(d.event_group_count)}} 组`)}}"></rect>`;
        html += `<text x="${{Math.min(totalW + 8, innerW - 74)}}" y="${{y + 16}}" fill="#475569" font-size="12">${{fmt.format(d.event_group_count)}}</text>`;
      }});
      html += `</g>`;
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = html;
      svg.querySelectorAll('[data-tip]').forEach(el => {{
        el.addEventListener('mousemove', e => showTip(el.getAttribute('data-tip'), e));
        el.addEventListener('mouseleave', hideTip);
      }});
    }}

    function renderHorizontalBars(svgId, rows, labelKey, valueKey, colorClass, maxRows = 10) {{
      const svg = document.getElementById(svgId);
      const data = rows.slice(0, maxRows);
      const width = svg.clientWidth || 800;
      const height = Number(svg.getAttribute('height')) || 440;
      const margin = {{ top: 14, right: 34, bottom: 28, left: 126 }};
      const innerW = width - margin.left - margin.right;
      const rowH = Math.min(38, (height - margin.top - margin.bottom) / Math.max(1, data.length));
      const max = Math.max(...data.map(d => n(d[valueKey])), 1);
      let html = `<g transform="translate(${{margin.left}},${{margin.top}})">`;
      data.forEach((d, i) => {{
        const y = i * rowH + 6;
        const value = n(d[valueKey]);
        const barW = innerW * value / max;
        const label = d[labelKey];
        html += `<text x="-10" y="${{y + 15}}" text-anchor="end" fill="#475569" font-size="12">${{esc(label)}}</text>`;
        html += `<rect class="bar-bg" x="0" y="${{y}}" width="${{innerW}}" height="20" rx="4"></rect>`;
        html += `<rect class="${{colorClass}}" x="0" y="${{y}}" width="${{barW}}" height="20" rx="4"
          data-tip="${{esc(`<strong>${{label}}</strong><br>数量：${{fmt.format(value)}}`)}}"></rect>`;
        if (i < 3) html += `<text x="${{Math.min(barW + 7, innerW - 62)}}" y="${{y + 15}}" fill="#475569" font-size="12">${{fmt.format(value)}}</text>`;
      }});
      html += `</g>`;
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = html;
      svg.querySelectorAll('[data-tip]').forEach(el => {{
        el.addEventListener('mousemove', e => showTip(el.getAttribute('data-tip'), e));
        el.addEventListener('mouseleave', hideTip);
      }});
    }}

    function renderCategoryChart() {{
      const filtered = DATA.eventDistribution.filter(d => state.company === '全部' || d.company === state.company);
      const grouped = new Map();
      filtered.forEach(d => grouped.set(d.category, (grouped.get(d.category) || 0) + n(d.event_group_count)));
      const rows = Array.from(grouped, ([category, event_group_count]) => ({{ category, event_group_count }}))
        .sort((a, b) => b.event_group_count - a.event_group_count);
      renderHorizontalBars('categoryChart', rows, 'category', 'event_group_count', 'bar-green', 10);
    }}

    function renderInventoryChart() {{
      renderHorizontalBars('inventoryChart', DATA.inventoryBySource, 'source', 'row_count', 'bar-slate', 10);
    }}

    function renderTable(id, columns, rows, linkColumn) {{
      const table = document.getElementById(id);
      const head = `<thead><tr>${{columns.map(c => `<th${{c.num ? ' class="num"' : ''}}>${{esc(c.label)}}</th>`).join('')}}</tr></thead>`;
      const body = rows.map(row => `<tr>${{columns.map(c => {{
        const raw = row[c.key];
        const cls = c.num ? ' class="num"' : '';
        if (c.key === linkColumn && raw) return `<td${{cls}}><a href="${{esc(raw)}}" target="_blank" rel="noreferrer">链接</a></td>`;
        if (c.status) return `<td${{cls}}><span class="status ${{raw === '通过' || raw === 'pass' ? 'ok' : 'other'}}">${{esc(raw)}}</span></td>`;
        return `<td${{cls}}>${{esc(raw ?? '')}}</td>`;
      }}).join('')}}</tr>`).join('');
      table.innerHTML = head + `<tbody>${{body}}</tbody>`;
    }}

    function filteredEvents() {{
      return DATA.eventRows.filter(row => {{
        if (state.company !== '全部' && row['公司'] !== state.company) return false;
        if (state.category !== '全部' && row['一级分类'] !== state.category) return false;
        return true;
      }}).slice(0, 120);
    }}

    function renderTables() {{
      renderTable('checksTable', [
        {{ key: '检查项', label: '检查项' }},
        {{ key: '是否通过', label: '状态', status: true }},
        {{ key: '详情', label: '详情' }},
      ], DATA.checks);
      renderTable('carTable', [
        {{ key: '事件日期', label: '日期' }},
        {{ key: '公司', label: '公司' }},
        {{ key: '事件类型', label: '类型' }},
        {{ key: '复核状态', label: '状态', status: true }},
        {{ key: '窗口覆盖_p0_p20', label: '窗口覆盖' }},
        {{ key: '复算CAR_p0_p20', label: '复算CAR', num: true }},
        {{ key: '原表CAR_p0_p20', label: '原表CAR', num: true }},
        {{ key: 'CAR差异_p0_p20', label: '差异', num: true }},
      ], DATA.carSamples);
      renderTable('eventTable', [
        {{ key: '事件日期', label: '日期' }},
        {{ key: '公司', label: '公司' }},
        {{ key: '一级分类', label: '一级分类' }},
        {{ key: '二级事件', label: '二级事件' }},
        {{ key: '代表事件标题', label: '事件标题' }},
        {{ key: '20日客观市值变化_亿元', label: '20日变化(亿元)', num: true }},
        {{ key: '20日相对竞品市值变化_亿元', label: '相对竞品(亿元)', num: true }},
        {{ key: '事件来源链接', label: '来源' }},
      ], filteredEvents(), '事件来源链接');
    }}

    function render() {{
      renderKpis();
      renderMarketChart();
      renderCompanyChart();
      renderCategoryChart();
      renderInventoryChart();
      renderTables();
    }}
    window.addEventListener('resize', () => {{
      renderMarketChart();
      renderCompanyChart();
      renderCategoryChart();
      renderInventoryChart();
    }});
    initControls();
    render();
  </script>
</body>
</html>
"""


def main() -> int:
    summary, payload = load_summary()
    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_SUMMARY, index=False, encoding="utf-8-sig")
    OUTPUT_HTML.write_text(build_html(payload), encoding="utf-8")
    print(f"wrote {OUTPUT_SUMMARY}")
    print(f"wrote {OUTPUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""生成交互式市值走势与事件筛选 dashboard。"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
RAW_TUSHARE_DIR = PROJECT_DIR / "data/raw/tushare"
PROCESSED_DIR = PROJECT_DIR / "data/processed"
EVENTS_PATH = PROCESSED_DIR / "rag_event_group_evidence_enhanced.csv"
GROUPS_PATH = PROCESSED_DIR / "event_analysis_groups_scored.csv"
CANDIDATES_PATH = PROCESSED_DIR / "event_candidates_scored.csv"
OUTPUT_PATH = PROCESSED_DIR / "interactive_market_dashboard.html"

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

EVIDENCE_LABELS = {
    "strong": "强证据",
    "auxiliary": "辅助证据",
    "weak": "弱证据",
    "none": "无证据",
}


def parse_trade_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")


def finite_number(value: object, digits: int = 4) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def text_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def classify_event_subtype(row: pd.Series) -> str:
    category = text_value(row.get("primary_category"))
    text = " ".join(
        [
            text_value(row.get("title")),
            text_value(row.get("group_titles_sample")),
            text_value(row.get("source_type")),
        ]
    )
    rules = {
        "业绩信号": [
            ("年报/半年报/季报", ("年度报告", "半年度报告", "季度报告", "一季报", "三季报")),
            ("业绩预告/快报", ("业绩预告", "业绩快报", "业绩修正")),
            ("利润/营收变化", ("利润", "营收", "收入", "亏损")),
        ],
        "资本动作": [
            ("分红/权益分派", ("分红", "权益分派", "利润分配")),
            ("回购", ("回购股份", "股份回购", "回购公司股份", "回购报告书")),
            ("股权激励/员工持股", ("股权激励", "限制性股票", "股票期权", "员工持股")),
            ("增减持/限售", ("增持", "减持", "限售", "解除限售")),
            ("定增/再融资", ("定增", "非公开发行", "向特定对象发行", "再融资")),
            ("并购重组/资产交易", ("收购", "并购", "资产重组", "股权转让", "资产出售")),
        ],
        "管理层/投关信号": [
            ("机构调研", ("调研", "接待", "投资者关系")),
            ("业绩说明会", ("业绩说明会", "说明会")),
            ("互动问答", ("互动", "问答", "投资者提问")),
        ],
        "产品/技术创新": [
            ("产品发布/技术研发", ("产品", "研发", "技术", "专利")),
            ("车联网/物联网", ("车联网", "物联网", "智能终端")),
            ("AI/卫星/新方向", ("AI", "人工智能", "卫星", "低空")),
        ],
        "客户/订单": [
            ("合同/订单", ("合同", "订单", "中标")),
            ("客户/合作", ("客户", "合作", "供应商")),
        ],
        "风险事件": [
            ("问询/监管", ("问询函", "关注函", "监管", "处罚", "立案")),
            ("诉讼/仲裁", ("诉讼", "仲裁")),
            ("减值/亏损风险", ("减值", "亏损", "风险提示")),
            ("异常波动", ("异常波动", "停牌", "复牌")),
        ],
    }
    for subtype, keywords in rules.get(category, []):
        if any(keyword in text for keyword in keywords):
            return subtype
    if "announcement" in text_value(row.get("source_type")):
        return "公告事件"
    if "research" in text_value(row.get("source_type")):
        return "研报事件"
    if "ir" in text_value(row.get("source_type")):
        return "调研/投关事件"
    return "其他事件"


def normalize_ts_code(symbol: object) -> str:
    raw = text_value(symbol).strip()
    if "." in raw:
        return raw
    digits = raw.zfill(6)
    suffix = "SH" if digits.startswith("6") else "SZ"
    return f"{digits}.{suffix}"


def evidence_level(row: pd.Series) -> str:
    status = text_value(row.get("rag_coverage_status"))
    strength = text_value(row.get("rag_best_evidence_strength"))
    source = text_value(row.get("rag_best_text_source"))
    if "strong" in strength or source in {"pdf", "notice_api"}:
        return "strong"
    if "aux" in strength or source in {"research_report", "ir_record", "irm_qa", "news"}:
        return "auxiliary"
    if status and status != "no_rag_evidence":
        return "weak"
    return "none"


def load_market_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for company, ts_code, symbol in COMPANIES:
        path = RAW_TUSHARE_DIR / "daily_basic" / f"{ts_code}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype={"trade_date": str})
        frame["trade_dt"] = parse_trade_date(frame["trade_date"])
        frame["total_mv_yi"] = pd.to_numeric(frame["total_mv"], errors="coerce") / 10000
        frame = frame.dropna(subset=["trade_dt", "total_mv_yi"]).sort_values("trade_dt")
        for _, row in frame.iterrows():
            rows.append(
                {
                    "company": company,
                    "ts_code": ts_code,
                    "symbol": symbol,
                    "date": row["trade_dt"].strftime("%Y-%m-%d"),
                    "total_mv_yi": finite_number(row["total_mv_yi"], 4),
                    "turnover_rate": finite_number(row.get("turnover_rate"), 4),
                    "pe": finite_number(row.get("pe"), 4),
                    "pb": finite_number(row.get("pb"), 4),
                }
            )
    return rows


def load_event_rows() -> list[dict[str, object]]:
    events = pd.read_csv(EVENTS_PATH)
    link_lookup = load_event_link_lookup()
    events["ts_code"] = events["symbol"].map(normalize_ts_code)
    rows: list[dict[str, object]] = []
    company_by_code = {ts_code: company for company, ts_code, _ in COMPANIES}
    for _, row in events.iterrows():
        ts_code = text_value(row.get("ts_code"))
        company = text_value(row.get("company")) or company_by_code.get(ts_code, "")
        level = evidence_level(row)
        event_id = text_value(row.get("event_id"))
        source_links = link_lookup.get(event_id, {})
        source_url = source_links.get("source_url", "")
        pdf_url = source_links.get("pdf_url", "")
        local_pdf_path = source_links.get("local_pdf_path", "")
        evidence_url = text_value(row.get("rag_best_pdf_url")) or pdf_url or source_url
        local_path = text_value(row.get("rag_best_local_path"))
        rows.append(
            {
                "id": text_value(row.get("analysis_group_id")),
                "event_id": event_id,
                "company": company,
                "ts_code": ts_code,
                "symbol": text_value(row.get("symbol")).zfill(6),
                "date": text_value(row.get("event_date"))[:10],
                "category": text_value(row.get("primary_category")) or "未分类",
                "subtype": classify_event_subtype(row),
                "title": text_value(row.get("title")),
                "titles_sample": text_value(row.get("group_titles_sample")),
                "source_type": text_value(row.get("source_type")),
                "source_types": text_value(row.get("source_types")),
                "group_event_count": finite_number(row.get("group_event_count"), 0),
                "pre_total_mv_yi": finite_number(row.get("pre_total_mv_yi"), 4),
                "mv_change_5d": finite_number(row.get("actual_mv_change_yi_p0_p5"), 4),
                "mv_change_20d": finite_number(row.get("actual_mv_change_yi_p0_p20"), 4),
                "mv_change_60d": finite_number(row.get("actual_mv_change_yi_p0_p60"), 4),
                "mv_return_5d": finite_number(row.get("actual_mv_return_p0_p5"), 6),
                "mv_return_20d": finite_number(row.get("actual_mv_return_p0_p20"), 6),
                "mv_return_60d": finite_number(row.get("actual_mv_return_p0_p60"), 6),
                "car_5d": finite_number(row.get("car_p0_p5"), 6),
                "car_20d": finite_number(row.get("car_p0_p20"), 6),
                "car_60d": finite_number(row.get("car_p0_p60"), 6),
                "abnormal_mv_impact_20d": finite_number(row.get("abnormal_mv_impact_yi_p0_p20"), 4),
                "priority_score": finite_number(row.get("event_priority_score"), 4),
                "objective_score": finite_number(row.get("objective_change_score"), 4),
                "rag_status": text_value(row.get("rag_coverage_status")) or "no_rag_evidence",
                "evidence_level": level,
                "evidence_label": EVIDENCE_LABELS[level],
                "evidence_title": text_value(row.get("rag_best_title")),
                "evidence_source": text_value(row.get("rag_best_text_source")),
                "evidence_url": evidence_url,
                "source_url": source_url,
                "pdf_url": pdf_url,
                "local_path": local_path or local_pdf_path,
                "evidence_refs": text_value(row.get("rag_evidence_refs")),
            }
        )
    return rows


def load_event_link_lookup() -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for path in [CANDIDATES_PATH, GROUPS_PATH]:
        if not path.exists():
            continue
        columns = pd.read_csv(path, nrows=0).columns
        usecols = [column for column in ["event_id", "source_url", "pdf_url", "local_pdf_path"] if column in columns]
        if "event_id" not in usecols:
            continue
        frame = pd.read_csv(path, dtype=str, usecols=usecols).fillna("")
        for _, row in frame.iterrows():
            event_id = text_value(row.get("event_id"))
            if not event_id:
                continue
            current = lookup.setdefault(event_id, {"source_url": "", "pdf_url": "", "local_pdf_path": ""})
            for column in ["source_url", "pdf_url", "local_pdf_path"]:
                value = text_value(row.get(column))
                if value and not current.get(column):
                    current[column] = value
    return lookup


def build_html(payload: dict[str, object]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>移为通信市值变化与事件对比 dashboard</title>
  <style>
    :root {{
      --red: #c0392b;
      --blue: #2471a3;
      --ink: #1a1a1a;
      --muted: #888888;
      --line: #e8e8e8;
      --line-soft: #f0f0f0;
      --bg: #ffffff;
      --panel: #fafafa;
      --danger: #c0392b;
      --good: #247a4d;
      --warn: #b45309;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft YaHei", "PingFang SC", -apple-system, Arial, sans-serif; color: var(--ink); background: var(--bg); font-size: 14px; }}
    header {{ padding: 14px 28px; background: #fff; color: var(--ink); border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; gap: 16px; }}
    header::before {{ content: ""; width: 3px; height: 24px; background: var(--red); display: block; flex: 0 0 auto; }}
    .headline {{ flex: 1 1 auto; min-width: 0; }}
    h1 {{ margin: 0 0 3px; font-size: 16px; font-weight: 700; letter-spacing: .5px; }}
    h2 {{ margin: 0 0 10px; font-size: 15px; }}
    h3 {{ margin: 0 0 8px; font-size: 14px; }}
    p {{ margin: 0; line-height: 1.5; }}
    button, select, input {{ font: inherit; }}
    button {{ border: 1px solid #d8d8d8; background: #fff; color: #333; border-radius: 3px; min-height: 28px; padding: 4px 10px; cursor: pointer; transition: background .1s, border-color .1s, color .1s; }}
    button:hover:not(:disabled) {{ border-color: #aaa; background: #f9f9f9; color: #111; }}
    button:disabled, select:disabled, input:disabled {{ opacity: .45; cursor: not-allowed; }}
    button.primary {{ background: #1a1a1a; border-color: #1a1a1a; color: #fff; }}
    button.icon {{ width: 26px; min-height: 26px; padding: 0; font-weight: 700; }}
    select, input {{ min-height: 28px; border: 1px solid #d8d8d8; border-radius: 3px; background: #fff; padding: 4px 7px; min-width: 120px; }}
    main {{ padding: 0 0 24px; display: flex; flex-direction: column; gap: 0; }}
    section, aside {{ background: #fff; border: 0; border-bottom: 1px solid var(--line); border-radius: 0; }}
    .steps {{ padding: 12px 20px; display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 12px; align-items: end; border-bottom: 1px solid var(--line-soft); }}
    .step {{ min-width: 0; }}
    .step.period {{ grid-column: span 2; }}
    .step.month {{ grid-column: span 2; }}
    .step.date-range {{ grid-column: span 3; }}
    .step.window {{ grid-column: span 2; }}
    .step.window-custom {{ grid-column: span 3; }}
    .step.category {{ grid-column: span 3; }}
    .step.subtype {{ grid-column: span 3; }}
    .step label {{ display: block; color: var(--muted); font-size: 10px; margin-bottom: 5px; text-transform: uppercase; letter-spacing: .5px; font-weight: 600; }}
    .step select, .step input {{ width: 100%; }}
    .date-inputs {{ display: grid; grid-template-columns: minmax(145px, 1fr) minmax(145px, 1fr); gap: 6px; }}
    .date-inputs input {{ min-width: 0; }}
    .shell {{ display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 0; align-items: start; }}
    .chart-panel {{ padding: 12px 18px 14px 28px; min-width: 0; position: relative; border-right: 1px solid var(--line); }}
    .chart-toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; justify-content: space-between; margin-bottom: 10px; }}
    .seg {{ display: inline-flex; border: 1px solid #d8d8d8; border-radius: 3px; overflow: hidden; background: #fff; }}
    .seg button {{ border: 0; border-right: 1px solid #d8d8d8; border-radius: 0; min-height: 28px; font-size: 12px; }}
    .seg button:last-child {{ border-right: 0; }}
    .seg button.active {{ background: #1a1a1a; color: #fff; font-weight: 700; }}
    .company-picks {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .chip {{ display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; border: 1px solid #d8d8d8; border-radius: 3px; background: #fff; font-size: 12px; }}
    .chip input {{ min-width: 0; min-height: 0; width: 14px; height: 14px; }}
    #chart {{ width: 100%; height: 820px; display: block; background: radial-gradient(circle at 16% 8%, rgba(192,57,43,.035), rgba(192,57,43,0) 28%), linear-gradient(180deg, #ffffff 0%, #fcfcfc 58%, #f8f8f8 100%); border: 1px solid #f0f0f0; border-radius: 6px; }}
    .chart-tip {{ position: fixed; display: none; max-width: 320px; z-index: 30; pointer-events: none; background: rgba(255,255,255,.98); border: 1px solid #d8e0ea; border-radius: 6px; box-shadow: 0 14px 30px rgba(0,0,0,.14); padding: 9px 10px; font-size: 12px; color: #1a1a1a; }}
    .chart-tip strong {{ display: block; margin-bottom: 4px; }}
    .chart-tip .line {{ color: #64748b; margin-top: 2px; }}
    .event-dot, .bubble-dot {{ cursor: pointer; }}
    .event-dot circle {{ transition: r .08s, stroke-width .08s; }}
    .event-dot:hover circle {{ r: 7; stroke-width: 2.5; }}
    .market-hover {{ cursor: crosshair; opacity: 0; transition: opacity .08s; }}
    .market-hover:hover {{ opacity: .95; }}
    .basket {{ position: sticky; top: 0; padding: 12px; max-height: 100vh; overflow: auto; background: #fff; }}
    .basket-list {{ display: flex; flex-direction: column; gap: 8px; }}
    .event-card {{ border: 1px solid var(--line); border-left: 4px solid var(--blue); border-radius: 6px; padding: 8px; background: #fff; }}
    .event-card .top {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; }}
    .event-code {{ font-weight: 700; color: var(--blue); }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 12px 20px; }}
    .metric {{ border: 1px solid var(--line-soft); border-radius: 6px; padding: 10px; background: linear-gradient(180deg, #fff, #fafafa); }}
    .metric .value {{ font-size: 18px; font-weight: 700; margin-top: 4px; }}
    .matrix, .events {{ padding: 14px 20px; overflow: auto; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }}
    th, td {{ padding: 7px 8px; border-bottom: 1px solid var(--line-soft); vertical-align: top; word-break: break-word; }}
    th {{ text-align: left; background: #f7f7f7; color: #555; position: sticky; top: 0; z-index: 1; }}
    tr.active-row {{ background: rgba(192,57,43,.06); }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .pos {{ color: var(--good); }}
    .neg {{ color: var(--danger); }}
    .tag {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 7px; background: #eef2f7; color: #334155; font-size: 12px; white-space: nowrap; }}
    .tag.strong {{ background: #dcfce7; color: #166534; }}
    .tag.auxiliary {{ background: #dbeafe; color: #1d4ed8; }}
    .tag.weak {{ background: #fef3c7; color: #92400e; }}
    .tag.none {{ background: #f1f5f9; color: #64748b; }}
    .event-link {{ color: var(--blue); text-decoration: none; font-weight: 700; }}
    .event-link:hover {{ text-decoration: underline; }}
    .drawer {{ border-top: 1px solid var(--line); padding: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .empty {{ color: var(--muted); padding: 14px 0; }}
    .spark {{ height: 28px; width: 100%; }}
    @media (max-width: 1200px) {{
      .steps {{ grid-template-columns: repeat(6, minmax(0, 1fr)); }}
      .step.period, .step.month, .step.window {{ grid-column: span 2; }}
      .step.date-range, .step.window-custom, .step.category, .step.subtype {{ grid-column: span 3; }}
      .shell {{ grid-template-columns: 1fr; }}
      .basket {{ position: static; max-height: none; }}
      .metric-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 700px) {{
      main {{ padding: 10px; }}
      .steps {{ grid-template-columns: 1fr; }}
      .step.period, .step.month, .step.date-range, .step.window, .step.window-custom, .step.category, .step.subtype {{ grid-column: span 1; }}
      .date-inputs {{ grid-template-columns: 1fr; }}
      .drawer {{ grid-template-columns: 1fr; }}
      #chart {{ height: 680px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="headline">
      <h1>移为通信市值变化与竞品事件对比</h1>
      <p class="muted">原始市值走势 + 阻塞式时间/事件筛选 + 多事件加入展示。CAR 只作为辅助列。</p>
    </div>
  </header>
  <main>
    <section class="steps" aria-label="筛选步骤">
      <div class="step period">
        <label>1. 时间期间</label>
        <select id="periodSelect">
          <option value="">请选择</option>
          <option value="all">上市以来</option>
          <option value="5y">近五年</option>
          <option value="3y">近三年</option>
          <option value="1y">近一年</option>
          <option value="custom">自定义</option>
        </select>
      </div>
      <div class="step month">
        <label>2. 具体月份</label>
        <select id="monthSelect" disabled></select>
      </div>
      <div class="step date-range">
        <label>2b. 自定义日期区间（开始 / 结束）</label>
        <div class="date-inputs">
          <input id="startDate" type="date" disabled />
          <input id="endDate" type="date" disabled />
        </div>
      </div>
      <div class="step window">
        <label>3. 事件窗口</label>
        <select id="windowSelect" disabled>
          <option value="5">5 日</option>
          <option value="20" selected>20 日</option>
          <option value="60">60 日</option>
          <option value="custom">自定义</option>
        </select>
      </div>
      <div class="step window-custom">
        <label>3b. 自定义窗口</label>
        <div style="display:flex;gap:6px;">
          <input id="windowBefore" type="number" value="0" min="-120" max="0" disabled />
          <input id="windowAfter" type="number" value="20" min="1" max="240" disabled />
        </div>
      </div>
      <div class="step category">
        <label>5. 事件类型</label>
        <select id="categorySelect" disabled></select>
      </div>
      <div class="step subtype">
        <label>6. 二级事件</label>
        <select id="subtypeSelect" disabled></select>
      </div>
    </section>

    <div class="shell">
      <section class="chart-panel">
        <div class="chart-toolbar">
          <div>
            <h2>原始市值走势</h2>
            <p class="muted">公司泳道按原始总市值绘制，单位为亿元；事件点可加入右侧事件篮子。</p>
          </div>
          <div class="seg" role="group" aria-label="图表模式">
            <button id="modeFocus" class="active" type="button">主线</button>
            <button id="modeLane" type="button">泳道</button>
            <button id="modeOverlay" type="button">叠加</button>
            <button id="modeBubble" type="button">气泡</button>
            <button id="modeAligned" type="button">事件对齐</button>
          </div>
        </div>
        <div class="company-picks" id="companyPicks"></div>
        <div class="chart-tip" id="chartTip"></div>
        <svg id="chart" role="img" aria-label="市值走势与事件"></svg>
      </section>

      <aside class="basket">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;">
          <h2>事件展示篮</h2>
          <button id="clearBasket" type="button">清空</button>
        </div>
        <div id="basketList" class="basket-list"></div>
      </aside>
    </div>

    <section class="metric-grid" id="metrics"></section>

    <section class="matrix">
      <h2>所有公司可比分析矩阵</h2>
      <p class="muted">每家公司保留原始起止市值和区间表现；点击公司行可高亮该公司并联动事件表。</p>
      <div id="companyMatrix"></div>
    </section>

    <section class="events">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;">
        <div>
          <h2>当前筛选事件</h2>
          <p class="muted">标题打开页面内详情，证据链接打开公告/PDF/研报来源；加号可加入多事件展示。</p>
        </div>
        <input id="eventSearch" placeholder="搜索标题/公司/证据" disabled />
      </div>
      <div id="eventTable"></div>
      <div id="eventDrawer" class="drawer"></div>
    </section>
  </main>
  <script id="payload" type="application/json">{payload_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('payload').textContent);
    const companies = payload.companies;
    const marketRows = payload.marketRows.map(d => ({{...d, t: Date.parse(d.date)}}));
    const events = payload.events.map(d => ({{...d, t: Date.parse(d.date)}}));
    const byCompany = new Map();
    const selectedCompanies = new Set(companies.map(c => c.ts_code));
    const basket = [];
    let chartMode = 'focus';
    let focusedCompany = '300590.SZ';
    let selectedDetailId = '';

    for (const row of marketRows) {{
      if (!byCompany.has(row.ts_code)) byCompany.set(row.ts_code, []);
      byCompany.get(row.ts_code).push(row);
    }}
    for (const rows of byCompany.values()) rows.sort((a, b) => a.t - b.t);

    const els = {{
      period: document.getElementById('periodSelect'),
      month: document.getElementById('monthSelect'),
      start: document.getElementById('startDate'),
      end: document.getElementById('endDate'),
      win: document.getElementById('windowSelect'),
      before: document.getElementById('windowBefore'),
      after: document.getElementById('windowAfter'),
      category: document.getElementById('categorySelect'),
      subtype: document.getElementById('subtypeSelect'),
      companyPicks: document.getElementById('companyPicks'),
      chart: document.getElementById('chart'),
      metrics: document.getElementById('metrics'),
      matrix: document.getElementById('companyMatrix'),
      eventTable: document.getElementById('eventTable'),
      drawer: document.getElementById('eventDrawer'),
      search: document.getElementById('eventSearch'),
      basket: document.getElementById('basketList'),
      chartTip: document.getElementById('chartTip'),
    }};

    function fmt(value, digits = 2) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return '';
      return Number(value).toFixed(digits);
    }}
    function fmtPct(value) {{
      if (value === null || value === undefined || Number.isNaN(Number(value))) return '';
      return (Number(value) * 100).toFixed(2) + '%';
    }}
    function clsNum(value) {{
      const n = Number(value);
      if (!Number.isFinite(n)) return '';
      return n >= 0 ? 'pos' : 'neg';
    }}
    function uniq(values) {{
      return Array.from(new Set(values.filter(Boolean))).sort((a, b) => String(a).localeCompare(String(b), 'zh-CN'));
    }}
    function dateStr(t) {{
      return new Date(t).toISOString().slice(0, 10);
    }}
    function addDays(t, days) {{
      const dt = new Date(t);
      dt.setDate(dt.getDate() + days);
      return dt.getTime();
    }}
    function monthDiff(start, end) {{
      return (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth();
    }}
    function buildTimeTicks(range) {{
      const start = new Date(range[0]);
      const end = new Date(range[1]);
      const months = Math.max(1, monthDiff(start, end));
      const step = months > 96 ? 24 : months > 60 ? 12 : months > 30 ? 6 : months > 12 ? 3 : 1;
      const tick = new Date(start.getFullYear(), start.getMonth(), 1);
      const ticks = [];
      const minGapMs = 1000 * 60 * 60 * 24 * 35;
      while (tick.getTime() <= range[1]) {{
        const t = tick.getTime();
        if (t >= range[0] && range[1] - t > minGapMs) {{
          ticks.push({{
            t,
            label: step >= 12 ? String(tick.getFullYear()) : `${{tick.getFullYear()}}-${{String(tick.getMonth() + 1).padStart(2, '0')}}`,
            major: tick.getMonth() === 0,
          }});
        }}
        tick.setMonth(tick.getMonth() + step);
      }}
      if (!ticks.length || ticks[0].t - range[0] > minGapMs) ticks.unshift({{t: range[0], label: dateStr(range[0]), major: true}});
      return ticks;
    }}
    function htmlEscape(s) {{
      return String(s ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function showTip(event, html) {{
      els.chartTip.innerHTML = html;
      els.chartTip.style.display = 'block';
      const pad = 14;
      const rect = els.chartTip.getBoundingClientRect();
      let left = event.clientX + pad;
      let top = event.clientY + pad;
      if (left + rect.width > window.innerWidth - 8) left = event.clientX - rect.width - pad;
      if (top + rect.height > window.innerHeight - 8) top = event.clientY - rect.height - pad;
      els.chartTip.style.left = `${{Math.max(8, left)}}px`;
      els.chartTip.style.top = `${{Math.max(8, top)}}px`;
    }}
    function hideTip() {{
      els.chartTip.style.display = 'none';
    }}

    function currentDateRange() {{
      const minT = Math.min(...marketRows.map(d => d.t));
      const maxT = Math.max(...marketRows.map(d => d.t));
      if (!els.period.value) return null;
      if (els.period.value === 'custom') {{
        if (!els.start.value || !els.end.value) return null;
        return [Date.parse(els.start.value), Date.parse(els.end.value)];
      }}
      if (els.month.value && els.month.value !== 'all') {{
        const start = Date.parse(els.month.value + '-01');
        const dt = new Date(start);
        dt.setMonth(dt.getMonth() + 1);
        dt.setDate(0);
        return [start, dt.getTime()];
      }}
      const end = maxT;
      if (els.period.value === '1y') return [addDays(end, -365), end];
      if (els.period.value === '3y') return [addDays(end, -365 * 3), end];
      if (els.period.value === '5y') return [addDays(end, -365 * 5), end];
      return [minT, maxT];
    }}

    function windowConfig() {{
      if (els.win.value === 'custom') {{
        return [Number(els.before.value || 0), Number(els.after.value || 20)];
      }}
      return [0, Number(els.win.value || 20)];
    }}

    function filteredEvents(options = {{}}) {{
      const respectFocus = options.respectFocus !== false;
      const range = currentDateRange();
      if (!range) return [];
      const q = els.search.value.trim().toLowerCase();
      return events.filter(e => {{
        if (e.t < range[0] || e.t > range[1]) return false;
        if (!selectedCompanies.has(e.ts_code)) return false;
        if (els.category.value && e.category !== els.category.value) return false;
        if (els.subtype.value && e.subtype !== els.subtype.value) return false;
        if (respectFocus && focusedCompany && e.ts_code !== focusedCompany) return false;
        if (q) {{
          const hay = [e.company, e.category, e.subtype, e.title, e.evidence_title, e.evidence_source].join(' ').toLowerCase();
          if (!hay.includes(q)) return false;
        }}
        return true;
      }}).sort((a, b) => b.t - a.t || Number(b.priority_score || 0) - Number(a.priority_score || 0));
    }}

    function selectedMarketRows(tsCode) {{
      const range = currentDateRange();
      if (!range) return [];
      return (byCompany.get(tsCode) || []).filter(d => d.t >= range[0] && d.t <= range[1]);
    }}

    function companyStats(tsCode) {{
      const rows = selectedMarketRows(tsCode);
      if (!rows.length) return null;
      const start = rows[0].total_mv_yi;
      const end = rows[rows.length - 1].total_mv_yi;
      let peak = -Infinity;
      let maxDrawdown = 0;
      let min = Infinity;
      let max = -Infinity;
      for (const row of rows) {{
        const v = Number(row.total_mv_yi);
        if (!Number.isFinite(v)) continue;
        peak = Math.max(peak, v);
        min = Math.min(min, v);
        max = Math.max(max, v);
        if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (v - peak) / peak);
      }}
      const companyEvents = filteredEvents({{respectFocus: false}}).filter(e => e.ts_code === tsCode);
      const strongEvents = companyEvents.filter(e => e.evidence_level === 'strong').length;
      return {{
        rows, start, end, min, max,
        change: end - start,
        ret: start ? (end - start) / start : null,
        maxDrawdown,
        eventCount: companyEvents.length,
        strongEvents,
        basketCount: basket.filter(e => e.ts_code === tsCode).length,
      }};
    }}

    function initCompanies() {{
      els.companyPicks.innerHTML = companies.map(c => `
        <label class="chip"><input type="checkbox" value="${{c.ts_code}}" checked />${{htmlEscape(c.company)}}</label>
      `).join('');
      els.companyPicks.querySelectorAll('input').forEach(input => {{
        input.addEventListener('change', () => {{
          if (input.checked) selectedCompanies.add(input.value);
          else selectedCompanies.delete(input.value);
          if (focusedCompany && !selectedCompanies.has(focusedCompany)) focusedCompany = '';
          renderAll();
        }});
      }});
    }}

    function populateMonths() {{
      const range = currentDateRange();
      els.month.innerHTML = '<option value="all">全部月份</option>';
      if (!els.period.value || els.period.value === 'custom') return;
      const months = uniq(marketRows.filter(d => d.t >= range[0] && d.t <= range[1]).map(d => d.date.slice(0, 7)));
      els.month.innerHTML += months.map(m => `<option value="${{m}}">${{m}}</option>`).join('');
    }}

    function updateStepState() {{
      const hasPeriod = Boolean(els.period.value);
      els.month.disabled = !hasPeriod || els.period.value === 'custom';
      els.start.disabled = !hasPeriod;
      els.end.disabled = !hasPeriod;
      const hasDate = Boolean(currentDateRange());
      els.win.disabled = !hasDate;
      const customWindow = els.win.value === 'custom' && hasDate;
      els.before.disabled = !customWindow;
      els.after.disabled = !customWindow;
      els.category.disabled = !hasDate;
      els.subtype.disabled = !hasDate || !els.category.value;
      els.search.disabled = !hasDate;
    }}

    function populateCategories() {{
      const range = currentDateRange();
      const previousCategory = els.category.value;
      const previousSubtype = els.subtype.value;
      const inRange = range ? events.filter(e => e.t >= range[0] && e.t <= range[1] && selectedCompanies.has(e.ts_code)) : [];
      const categories = uniq(inRange.map(e => e.category));
      els.category.innerHTML = '<option value="">全部事件类型</option>' + categories.map(v => `<option value="${{htmlEscape(v)}}">${{htmlEscape(v)}}</option>`).join('');
      if (categories.includes(previousCategory)) els.category.value = previousCategory;
      const subtypes = els.category.value ? uniq(inRange.filter(e => e.category === els.category.value).map(e => e.subtype)) : [];
      els.subtype.innerHTML = '<option value="">全部二级事件</option>' + subtypes.map(v => `<option value="${{htmlEscape(v)}}">${{htmlEscape(v)}}</option>`).join('');
      if (subtypes.includes(previousSubtype)) els.subtype.value = previousSubtype;
    }}

    function renderMetrics() {{
      const stats = companies.filter(c => selectedCompanies.has(c.ts_code)).map(c => companyStats(c.ts_code)).filter(Boolean);
      const evs = filteredEvents();
      const best = stats.slice().sort((a, b) => (b.ret ?? -Infinity) - (a.ret ?? -Infinity))[0];
      const worst = stats.slice().sort((a, b) => (a.ret ?? Infinity) - (b.ret ?? Infinity))[0];
      els.metrics.innerHTML = [
        ['筛选事件数', evs.length],
        ['已加入展示', basket.length],
        ['最佳区间涨幅', best ? fmtPct(best.ret) : ''],
        ['最大区间跌幅', worst ? fmtPct(worst.ret) : ''],
      ].map(([label, value]) => `<div class="metric"><div class="muted">${{label}}</div><div class="value">${{value}}</div></div>`).join('');
    }}

    function linePath(points) {{
      return points.map((p, i) => `${{i ? 'L' : 'M'}}${{p[0].toFixed(1)}},${{p[1].toFixed(1)}}`).join(' ');
    }}
    function areaPath(points, baselineY) {{
      if (!points.length) return '';
      const last = points[points.length - 1];
      const first = points[0];
      return `${{linePath(points)}} L${{last[0].toFixed(1)}},${{baselineY.toFixed(1)}} L${{first[0].toFixed(1)}},${{baselineY.toFixed(1)}} Z`;
    }}
    function sampledRows(rows, maxPoints = 90) {{
      if (rows.length <= maxPoints) return rows;
      const step = Math.ceil(rows.length / maxPoints);
      return rows.filter((_, idx) => idx % step === 0 || idx === rows.length - 1);
    }}
    function closestRow(rows, t) {{
      if (!rows.length) return null;
      let best = rows[0];
      let bestGap = Math.abs(rows[0].t - t);
      for (const row of rows) {{
        const gap = Math.abs(row.t - t);
        if (gap < bestGap) {{
          best = row;
          bestGap = gap;
        }}
      }}
      return best;
    }}
    function renderMarketHoverPoints(company, rows, xFn, yFn, color, maxPoints = 90, radius = 4) {{
      return sampledRows(rows, maxPoints).map(row => `
        <circle class="market-hover" data-company="${{htmlEscape(company.company)}}" data-date="${{htmlEscape(row.date)}}" data-value="${{fmt(row.total_mv_yi)}}" cx="${{xFn(row.t).toFixed(1)}}" cy="${{yFn(Number(row.total_mv_yi)).toFixed(1)}}" r="${{radius}}" fill="${{color}}" stroke="#fff" stroke-width="1.5"/>
      `).join('');
    }}
    function renderChart() {{
      const svg = els.chart;
      const width = svg.clientWidth || 1000;
      const height = svg.clientHeight || 620;
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      const range = currentDateRange();
      if (!range) {{
        svg.innerHTML = `<text x="24" y="48" fill="#64748b">请先选择时间期间</text>`;
        return;
      }}
      const selected = companies.filter(c => selectedCompanies.has(c.ts_code));
      if (!selected.length) {{
        svg.innerHTML = `<text x="24" y="48" fill="#64748b">请至少选择一家公司</text>`;
        return;
      }}
      const colors = ['#c0392b','#2471a3','#16a085','#8e44ad','#d35400','#2c3e50','#27ae60','#7f8c8d','#f39c12'];
      const colorByCode = Object.fromEntries(companies.map((c, i) => [c.ts_code, colors[i % colors.length]]));
      const margin = {{left: 88, right: 48, top: 34, bottom: 70}};
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const x = t => margin.left + (t - range[0]) / Math.max(1, range[1] - range[0]) * plotW;
      const eventYById = new Map();
      let body = `<defs>
        <linearGradient id="focusLineGrad" x1="${{margin.left}}" y1="0" x2="${{width - margin.right}}" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="#c0392b"/>
          <stop offset="58%" stop-color="#d35400"/>
          <stop offset="100%" stop-color="#2471a3"/>
        </linearGradient>
        <linearGradient id="focusAreaGrad" x1="0" y1="${{margin.top}}" x2="0" y2="${{height - margin.bottom}}" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="#c0392b" stop-opacity=".18"/>
          <stop offset="64%" stop-color="#c0392b" stop-opacity=".055"/>
          <stop offset="100%" stop-color="#c0392b" stop-opacity="0"/>
        </linearGradient>
        <filter id="softLineShadow" x="-5%" y="-20%" width="110%" height="150%">
          <feDropShadow dx="0" dy="4" stdDeviation="5" flood-color="#c0392b" flood-opacity=".10"/>
        </filter>
      </defs><rect x="${{margin.left}}" y="${{margin.top}}" width="${{plotW}}" height="${{plotH}}" fill="rgba(255,255,255,.72)" stroke="#f0f0f0"/>`;
      let lastTickLabelX = -Infinity;
      for (const tick of buildTimeTicks(range)) {{
        const tx = x(tick.t);
        body += `<line x1="${{tx}}" y1="${{margin.top}}" x2="${{tx}}" y2="${{height - margin.bottom}}" stroke="${{tick.major ? '#d9e2ec' : '#edf2f7'}}" stroke-width="${{tick.major ? 1.1 : .8}}"/>`;
        body += `<line x1="${{tx}}" y1="${{height - margin.bottom}}" x2="${{tx}}" y2="${{height - margin.bottom + 5}}" stroke="#94a3b8"/>`;
        const clearOfEnds = tx > margin.left + 70 && tx < width - margin.right - 76;
        if (clearOfEnds && tx - lastTickLabelX >= 76) {{
          body += `<text x="${{tx}}" y="${{height - margin.bottom + 22}}" fill="#64748b" font-size="11" text-anchor="middle">${{tick.label}}</text>`;
          lastTickLabelX = tx;
        }}
      }}
      body += `<line x1="${{margin.left}}" y1="${{height - margin.bottom}}" x2="${{width - margin.right}}" y2="${{height - margin.bottom}}" stroke="#94a3b8" stroke-width="1.2"/>`;
      body += `<text x="${{margin.left}}" y="${{height - 16}}" fill="#475569" font-size="11" font-weight="700">起 ${{dateStr(range[0])}}</text>`;
      body += `<text x="${{width - margin.right}}" y="${{height - 16}}" fill="#475569" font-size="11" font-weight="700" text-anchor="end">止 ${{dateStr(range[1])}}</text>`;

      if (chartMode === 'aligned') {{
        const selectedBasket = basket.slice(0, 8);
        if (!selectedBasket.length) {{
          svg.innerHTML = `<text x="24" y="48" fill="#64748b">请用加号加入事件后查看事件对齐视图</text>`;
          return;
        }}
        const [before, after] = windowConfig();
        const xRel = day => margin.left + (day - before) / Math.max(1, after - before) * plotW;
        body += `<line x1="${{xRel(0)}}" y1="${{margin.top}}" x2="${{xRel(0)}}" y2="${{height - margin.bottom}}" stroke="#ef4444" stroke-dasharray="4 4"/>`;
        body += `<text x="${{xRel(0)+4}}" y="${{margin.top+12}}" fill="#ef4444" font-size="12">T=0</text>`;
        let globalMin = Infinity, globalMax = -Infinity;
        const series = selectedBasket.map((event, idx) => {{
          const rows = byCompany.get(event.ts_code) || [];
          const around = rows.filter(r => r.t >= addDays(event.t, before) && r.t <= addDays(event.t, after));
          const start = around.find(r => r.t >= event.t) || around[0];
          const base = start ? Number(start.total_mv_yi) : 0;
          const points = around.map(r => {{
            const day = Math.round((r.t - event.t) / 86400000);
            const ret = base ? (Number(r.total_mv_yi) - base) / base : 0;
            globalMin = Math.min(globalMin, ret);
            globalMax = Math.max(globalMax, ret);
            return {{day, ret}};
          }});
          return {{event, idx, points}};
        }});
        if (!Number.isFinite(globalMin) || !Number.isFinite(globalMax) || globalMin === globalMax) {{ globalMin = -0.1; globalMax = 0.1; }}
        const yRel = v => margin.top + (globalMax - v) / (globalMax - globalMin) * plotH;
        body += `<text x="12" y="${{margin.top+14}}" fill="#64748b" font-size="12">事件日相对涨跌幅</text>`;
        for (const s of series) {{
          const pts = s.points.map(p => [xRel(p.day), yRel(p.ret)]);
          body += `<path d="${{linePath(pts)}}" fill="none" stroke="${{colorByCode[s.event.ts_code]}}" stroke-width="2"/>`;
          body += `<text x="${{margin.left + 8}}" y="${{margin.top + 18 + s.idx * 18}}" fill="${{colorByCode[s.event.ts_code]}}" font-size="12">E${{s.idx+1}} ${{htmlEscape(s.event.company)}}</text>`;
        }}
        svg.innerHTML = body;
        return;
      }}

      if (chartMode === 'bubble') {{
        const stats = selected.map(c => [c, companyStats(c.ts_code)]).filter(([, s]) => s);
        if (!stats.length) {{
          svg.innerHTML = `<text x="24" y="48" fill="#888">当前区间无可用市值数据</text>`;
          return;
        }}
        const xVals = stats.map(([, s]) => Number(s.ret || 0));
        const yVals = stats.map(([, s]) => Math.abs(Number(s.maxDrawdown || 0)));
        const sizeVals = stats.map(([, s]) => Number(s.end || 0));
        const minX = Math.min(...xVals, 0) - 0.08;
        const maxX = Math.max(...xVals, 0) + 0.08;
        const maxY = Math.max(...yVals, 0.05) + 0.05;
        const maxSize = Math.max(...sizeVals, 1);
        const xB = v => margin.left + (v - minX) / Math.max(0.01, maxX - minX) * plotW;
        const yB = v => margin.top + (maxY - v) / Math.max(0.01, maxY) * plotH;
        body += `<rect x="${{margin.left}}" y="${{margin.top}}" width="${{plotW}}" height="${{plotH}}" fill="#fff" stroke="#f0f0f0"/>`;
        for (let i = 0; i <= 5; i++) {{
          const gx = margin.left + plotW * i / 5;
          const gy = margin.top + plotH * i / 5;
          body += `<line x1="${{gx}}" y1="${{margin.top}}" x2="${{gx}}" y2="${{height - margin.bottom}}" stroke="#e8eef5"/>`;
          body += `<line x1="${{margin.left}}" y1="${{gy}}" x2="${{width - margin.right}}" y2="${{gy}}" stroke="#e8eef5"/>`;
        }}
        body += `<line x1="${{xB(0)}}" y1="${{margin.top}}" x2="${{xB(0)}}" y2="${{height - margin.bottom}}" stroke="#cbd5e1" stroke-dasharray="4 4"/>`;
        body += `<text x="${{margin.left + plotW / 2 - 74}}" y="${{height - 6}}" fill="#1a1a1a" font-size="12" font-weight="700">区间市值涨跌幅</text>`;
        body += `<text x="12" y="${{margin.top + 14}}" fill="#1a1a1a" font-size="12" font-weight="700">最大回撤</text>`;
        body += `<text x="${{margin.left + 8}}" y="${{margin.top + 18}}" fill="#888" font-size="11">气泡大小=期末原始市值</text>`;
        for (const [c, s] of stats.sort((a, b) => Number(a[1].end) - Number(b[1].end))) {{
          const cx = xB(Number(s.ret || 0));
          const cy = yB(Math.abs(Number(s.maxDrawdown || 0)));
          const radius = 7 + Math.sqrt(Number(s.end || 0) / maxSize) * 24;
          const isYiwei = c.ts_code === '300590.SZ';
          const color = colorByCode[c.ts_code];
          body += `<circle class="bubble-dot" data-company="${{htmlEscape(c.company)}}" data-ret="${{fmtPct(s.ret)}}" data-drawdown="${{fmtPct(s.maxDrawdown)}}" data-end="${{fmt(s.end)}}" cx="${{cx}}" cy="${{cy}}" r="${{radius}}" fill="${{color}}" fill-opacity="${{isYiwei ? .9 : .72}}" stroke="${{isYiwei ? '#991b1b' : color}}" stroke-width="${{isYiwei ? 3 : 1.2}}"/>`;
          body += `<text x="${{cx + radius + 5}}" y="${{cy + 4}}" fill="${{isYiwei ? '#991b1b' : '#1a1a1a'}}" font-size="${{isYiwei ? 13 : 11}}" font-weight="${{isYiwei ? 700 : 600}}" stroke="#fff" stroke-width="3" paint-order="stroke">${{htmlEscape(c.company)}}</text>`;
        }}
        svg.innerHTML = body;
        svg.querySelectorAll('.bubble-dot').forEach(node => {{
          node.addEventListener('mousemove', event => showTip(event, `<strong>${{htmlEscape(node.dataset.company)}}</strong><div class="line">区间涨跌幅：${{htmlEscape(node.dataset.ret)}}</div><div class="line">最大回撤：${{htmlEscape(node.dataset.drawdown)}}</div><div class="line">期末市值：${{htmlEscape(node.dataset.end)}} 亿</div>`));
          node.addEventListener('mouseleave', hideTip);
        }});
        return;
      }}

      if (chartMode === 'focus') {{
        const focus = selected.find(c => c.ts_code === focusedCompany) || selected.find(c => c.ts_code === '300590.SZ') || selected[0];
        const focusRows = selectedMarketRows(focus.ts_code);
        if (!focusRows.length) {{
          svg.innerHTML = `<text x="24" y="48" fill="#64748b">当前区间没有 ${{htmlEscape(focus.company)}} 市值数据</text>`;
          return;
        }}
        const focusMin = Math.min(...focusRows.map(r => Number(r.total_mv_yi)));
        const focusMax = Math.max(...focusRows.map(r => Number(r.total_mv_yi)));
        const yPadTop = margin.top + 24;
        const yPadBottom = height - margin.bottom - 20;
        const yFocus = v => yPadTop + (focusMax - v) / Math.max(1, focusMax - focusMin) * (yPadBottom - yPadTop);
        for (let i = 0; i <= 5; i++) {{
          const gy = yPadTop + (yPadBottom - yPadTop) * i / 5;
          const labelValue = focusMax - (focusMax - focusMin) * i / 5;
          body += `<line x1="${{margin.left}}" y1="${{gy}}" x2="${{width - margin.right}}" y2="${{gy}}" stroke="#edf2f7"/>`;
          body += `<text x="${{margin.left - 10}}" y="${{gy + 4}}" fill="#64748b" font-size="11" text-anchor="end">${{fmt(labelValue, 0)}}</text>`;
        }}
        body += `<text x="${{margin.left}}" y="${{margin.top - 10}}" fill="#991b1b" font-size="14" font-weight="700">${{htmlEscape(focus.company)}}原始总市值</text>`;
        body += `<text x="${{width - margin.right}}" y="${{margin.top - 10}}" fill="#64748b" font-size="11" text-anchor="end">单位：亿元</text>`;
        const focusPts = focusRows.map(r => [x(r.t), yFocus(Number(r.total_mv_yi))]);
        body += `<path d="${{areaPath(focusPts, yPadBottom)}}" fill="url(#focusAreaGrad)" opacity=".95"/>`;
        body += `<path d="${{linePath(focusPts)}}" fill="none" stroke="rgba(255,255,255,.88)" stroke-width="7.2" stroke-linejoin="round" stroke-linecap="round"/>`;
        body += `<path d="${{linePath(focusPts)}}" fill="none" stroke="url(#focusLineGrad)" stroke-width="3.4" stroke-linejoin="round" stroke-linecap="round" filter="url(#softLineShadow)"/>`;
        body += renderMarketHoverPoints(focus, focusRows, x, yFocus, colorByCode[focus.ts_code], 120, 4.2);
        for (const e of filteredEvents()) {{
          if (e.ts_code !== focus.ts_code) continue;
          const row = closestRow(focusRows, e.t);
          if (row) eventYById.set(e.id, yFocus(Number(row.total_mv_yi)));
        }}
      }} else if (chartMode === 'overlay') {{
        const allRows = selected.flatMap(c => selectedMarketRows(c.ts_code));
        const minY = Math.min(...allRows.map(r => Number(r.total_mv_yi)));
        const maxY = Math.max(...allRows.map(r => Number(r.total_mv_yi)));
        const y = v => margin.top + (maxY - v) / Math.max(1, maxY - minY) * plotH;
        body += `<text x="12" y="${{margin.top+14}}" fill="#64748b" font-size="12">原始总市值 亿元</text>`;
        for (const c of selected) {{
          const rows = selectedMarketRows(c.ts_code);
          const pts = rows.map(r => [x(r.t), y(Number(r.total_mv_yi))]);
          body += `<path d="${{linePath(pts)}}" fill="none" stroke="${{colorByCode[c.ts_code]}}" stroke-width="${{focusedCompany === c.ts_code ? 3 : 1.8}}" opacity="${{focusedCompany && focusedCompany !== c.ts_code ? .25 : 1}}"/>`;
          body += renderMarketHoverPoints(c, rows, x, y, colorByCode[c.ts_code], 70, 3.4);
          body += `<text x="${{width - margin.right - 96}}" y="${{margin.top + 16 + selected.indexOf(c)*18}}" fill="${{colorByCode[c.ts_code]}}" font-size="12">${{htmlEscape(c.company)}}</text>`;
        }}
      }} else {{
        const laneH = plotH / selected.length;
        selected.forEach((c, idx) => {{
          const rows = selectedMarketRows(c.ts_code);
          if (!rows.length) return;
          const top = margin.top + idx * laneH;
          const bottom = top + laneH - 12;
          const minY = Math.min(...rows.map(r => Number(r.total_mv_yi)));
          const maxY = Math.max(...rows.map(r => Number(r.total_mv_yi)));
          const y = v => bottom - (v - minY) / Math.max(1, maxY - minY) * (laneH - 34);
          body += `<line x1="${{margin.left}}" y1="${{bottom}}" x2="${{width - margin.right}}" y2="${{bottom}}" stroke="#eeeeee"/>`;
          body += `<text x="10" y="${{top + 18}}" fill="${{colorByCode[c.ts_code]}}" font-size="13" font-weight="700">${{htmlEscape(c.company)}}</text>`;
          body += `<text x="10" y="${{top + 36}}" fill="#64748b" font-size="11">${{fmt(minY,1)}}-${{fmt(maxY,1)}}亿</text>`;
          const pts = rows.map(r => [x(r.t), y(Number(r.total_mv_yi))]);
          body += `<path d="${{linePath(pts)}}" fill="none" stroke="${{colorByCode[c.ts_code]}}" stroke-width="${{focusedCompany === c.ts_code ? 3 : 1.8}}" opacity="${{focusedCompany && focusedCompany !== c.ts_code ? .25 : 1}}"/>`;
          body += renderMarketHoverPoints(c, rows, x, y, colorByCode[c.ts_code], 46, 3.2);
        }});
      }}

      const evs = filteredEvents().slice(0, 220);
      for (const e of evs) {{
        if (!selectedCompanies.has(e.ts_code)) continue;
        let y = margin.top + 16;
        if (chartMode === 'focus') {{
          y = eventYById.get(e.id) || margin.top + 28;
        }} else if (chartMode === 'lane') {{
          const idx = selected.findIndex(c => c.ts_code === e.ts_code);
          if (idx < 0) continue;
          y = margin.top + idx * (plotH / selected.length) + 18;
        }} else {{
          y = margin.top + 22 + (selected.findIndex(c => c.ts_code === e.ts_code) % 10) * 14;
        }}
        const cx = x(e.t);
        const inBasket = basket.some(item => item.id === e.id);
        const eventColor = chartMode === 'focus' ? '#c0392b' : colorByCode[e.ts_code];
        body += `<g class="event-dot" data-event-id="${{htmlEscape(e.id)}}" data-company="${{htmlEscape(e.company)}}" data-date="${{htmlEscape(e.date)}}" data-title="${{htmlEscape(e.title)}}" data-change="${{fmt(e.mv_change_20d)}}" data-evidence="${{htmlEscape(e.evidence_label)}}"><circle cx="${{cx.toFixed(1)}}" cy="${{y.toFixed(1)}}" r="${{inBasket ? 7 : 5}}" fill="#fff" stroke="${{eventColor}}" stroke-width="${{inBasket ? 2.6 : 1.8}}" opacity=".96"/><circle cx="${{cx.toFixed(1)}}" cy="${{y.toFixed(1)}}" r="2" fill="${{eventColor}}" opacity=".9"/><text x="${{cx + 7}}" y="${{y - 7}}" fill="#334155" font-size="11" font-weight="700">${{inBasket ? '+' : ''}}</text></g>`;
      }}
      for (const [idx, e] of basket.entries()) {{
        if (e.t < range[0] || e.t > range[1]) continue;
        const cx = x(e.t);
        body += `<line x1="${{cx}}" y1="${{margin.top}}" x2="${{cx}}" y2="${{height - margin.bottom}}" stroke="${{colorByCode[e.ts_code]}}" stroke-dasharray="4 4" opacity=".75"/>`;
        body += `<text x="${{cx + 4}}" y="${{margin.top + 14 + idx * 14}}" fill="${{colorByCode[e.ts_code]}}" font-size="12">E${{idx+1}}</text>`;
      }}
      svg.innerHTML = body;
      svg.querySelectorAll('.event-dot').forEach(node => {{
        node.addEventListener('click', () => {{
          const ev = events.find(item => item.id === node.dataset.eventId);
          if (ev) addEvent(ev);
        }});
        node.addEventListener('mousemove', event => showTip(event, `<strong>${{htmlEscape(node.dataset.company)}} · ${{htmlEscape(node.dataset.date)}}</strong><div>${{htmlEscape(node.dataset.title)}}</div><div class="line">20日变化：${{htmlEscape(node.dataset.change)}} 亿 · 证据：${{htmlEscape(node.dataset.evidence)}}</div>`));
        node.addEventListener('mouseleave', hideTip);
      }});
      svg.querySelectorAll('.market-hover').forEach(node => {{
        node.addEventListener('mousemove', event => showTip(event, `<strong>${{htmlEscape(node.dataset.company)}} · ${{htmlEscape(node.dataset.date)}}</strong><div class="line">原始总市值：${{htmlEscape(node.dataset.value)}} 亿</div>`));
        node.addEventListener('mouseleave', hideTip);
      }});
      svg.querySelectorAll('.bubble-dot').forEach(node => {{
        node.addEventListener('mousemove', event => showTip(event, `<strong>${{htmlEscape(node.dataset.company)}}</strong><div class="line">区间涨跌幅：${{htmlEscape(node.dataset.ret)}}</div><div class="line">最大回撤：${{htmlEscape(node.dataset.drawdown)}}</div><div class="line">期末市值：${{htmlEscape(node.dataset.end)}} 亿</div>`));
        node.addEventListener('mouseleave', hideTip);
      }});
    }}

    function sparkline(rows) {{
      if (!rows.length) return '';
      const w = 120, h = 28;
      const min = Math.min(...rows.map(r => Number(r.total_mv_yi)));
      const max = Math.max(...rows.map(r => Number(r.total_mv_yi)));
      const minT = rows[0].t, maxT = rows[rows.length - 1].t;
      const pts = rows.map(r => [
        (r.t - minT) / Math.max(1, maxT - minT) * w,
        h - (Number(r.total_mv_yi) - min) / Math.max(1, max - min) * (h - 2) - 1
      ]);
      return `<svg class="spark" viewBox="0 0 ${{w}} ${{h}}"><path d="${{linePath(pts)}}" fill="none" stroke="#0f766e" stroke-width="2"/></svg>`;
    }}

    function renderMatrix() {{
      const yiwei = companyStats('300590.SZ');
      const rows = companies.filter(c => selectedCompanies.has(c.ts_code)).map(c => [c, companyStats(c.ts_code)]).filter(([,s]) => s);
      els.matrix.innerHTML = `<table><thead><tr>
        <th style="width:92px;">公司</th><th style="width:150px;">原始走势</th><th class="num">起始市值</th><th class="num">结束市值</th><th class="num">市值变化</th><th class="num">涨跌幅</th><th class="num">相对移为</th><th class="num">最大回撤</th><th class="num">事件数</th><th class="num">强证据</th><th class="num">已加入</th>
      </tr></thead><tbody>${{rows.map(([c,s]) => {{
        const rel = yiwei && c.ts_code !== '300590.SZ' && Number.isFinite(s.ret) && Number.isFinite(yiwei.ret) ? s.ret - yiwei.ret : null;
        return `<tr class="${{focusedCompany === c.ts_code ? 'active-row' : ''}}" data-company="${{c.ts_code}}">
          <td><a href="#" class="event-link company-focus" data-company="${{c.ts_code}}">${{htmlEscape(c.company)}}</a></td>
          <td>${{sparkline(s.rows)}}</td>
          <td class="num">${{fmt(s.start)}}</td>
          <td class="num">${{fmt(s.end)}}</td>
          <td class="num ${{clsNum(s.change)}}">${{fmt(s.change)}}</td>
          <td class="num ${{clsNum(s.ret)}}">${{fmtPct(s.ret)}}</td>
          <td class="num ${{clsNum(rel)}}">${{rel === null ? '基准' : fmtPct(rel)}}</td>
          <td class="num neg">${{fmtPct(s.maxDrawdown)}}</td>
          <td class="num">${{s.eventCount}}</td>
          <td class="num">${{s.strongEvents}}</td>
          <td class="num">${{s.basketCount}}</td>
        </tr>`;
      }}).join('')}}</tbody></table>`;
      els.matrix.querySelectorAll('.company-focus').forEach(a => {{
        a.addEventListener('click', ev => {{
          ev.preventDefault();
          focusedCompany = focusedCompany === a.dataset.company ? '' : a.dataset.company;
          renderAll();
        }});
      }});
    }}

    function addEvent(event) {{
      if (!basket.some(e => e.id === event.id)) basket.push(event);
      if (basket.length > 10) basket.shift();
      selectedDetailId = event.id;
      renderAll();
    }}
    function removeEvent(id) {{
      const idx = basket.findIndex(e => e.id === id);
      if (idx >= 0) basket.splice(idx, 1);
      renderAll();
    }}

    function renderBasket() {{
      if (!basket.length) {{
        els.basket.innerHTML = '<p class="empty">用图上事件点或事件表加号加入多个事件。</p>';
        return;
      }}
      els.basket.innerHTML = basket.map((e, idx) => `<div class="event-card">
        <div class="top"><span class="event-code">E${{idx+1}}</span><button class="icon remove-event" data-id="${{htmlEscape(e.id)}}" type="button">×</button></div>
        <div><strong>${{htmlEscape(e.company)}}</strong> <span class="muted">${{htmlEscape(e.date)}} · ${{htmlEscape(e.category)}} / ${{htmlEscape(e.subtype)}}</span></div>
        <div style="margin-top:4px;">${{htmlEscape(e.title)}}</div>
        <div class="muted" style="margin-top:5px;">20日变化：<span class="${{clsNum(e.mv_change_20d)}}">${{fmt(e.mv_change_20d)}} 亿</span> · 证据：${{htmlEscape(e.evidence_label)}}</div>
      </div>`).join('');
      els.basket.querySelectorAll('.remove-event').forEach(btn => btn.addEventListener('click', () => removeEvent(btn.dataset.id)));
    }}

    function renderEvents() {{
      const evs = filteredEvents().slice(0, 300);
      if (!currentDateRange()) {{
        els.eventTable.innerHTML = '<p class="empty">请先完成时间选择。</p>';
        els.drawer.innerHTML = '';
        return;
      }}
      if (!evs.length) {{
        els.eventTable.innerHTML = '<p class="empty">当前条件下没有事件。</p>';
        els.drawer.innerHTML = '';
        return;
      }}
      els.eventTable.innerHTML = `<table><thead><tr>
        <th style="width:42px;">+</th><th style="width:88px;">日期</th><th style="width:80px;">公司</th><th style="width:100px;">事件类型</th><th style="width:120px;">二级事件</th><th>细节事件</th><th class="num" style="width:92px;">20日变化</th><th class="num" style="width:78px;">CAR</th><th style="width:84px;">证据</th><th style="width:78px;">链接</th>
      </tr></thead><tbody>${{evs.map(e => `<tr class="${{selectedDetailId === e.id ? 'active-row' : ''}}">
        <td><button class="icon add-event" data-id="${{htmlEscape(e.id)}}" type="button">+</button></td>
        <td>${{htmlEscape(e.date)}}</td>
        <td>${{htmlEscape(e.company)}}</td>
        <td>${{htmlEscape(e.category)}}</td>
        <td>${{htmlEscape(e.subtype)}}</td>
        <td><a href="#" class="event-link detail-link" data-id="${{htmlEscape(e.id)}}">${{htmlEscape(e.title)}}</a></td>
        <td class="num ${{clsNum(e.mv_change_20d)}}">${{fmt(e.mv_change_20d)}}</td>
        <td class="num ${{clsNum(e.car_20d)}}">${{fmtPct(e.car_20d)}}</td>
        <td><span class="tag ${{e.evidence_level}}">${{htmlEscape(e.evidence_label)}}</span></td>
        <td>${{e.evidence_url ? `<a class="event-link" href="${{htmlEscape(e.evidence_url)}}" target="_blank" rel="noreferrer">证据</a>` : ''}}</td>
      </tr>`).join('')}}</tbody></table>`;
      els.eventTable.querySelectorAll('.add-event').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const event = events.find(e => e.id === btn.dataset.id);
          if (event) addEvent(event);
        }});
      }});
      els.eventTable.querySelectorAll('.detail-link').forEach(a => {{
        a.addEventListener('click', ev => {{
          ev.preventDefault();
          selectedDetailId = a.dataset.id;
          renderDrawer();
          renderEvents();
        }});
      }});
      if (!selectedDetailId || !evs.some(e => e.id === selectedDetailId)) selectedDetailId = evs[0].id;
      renderDrawer();
    }}

    function renderDrawer() {{
      const e = events.find(item => item.id === selectedDetailId);
      if (!e) {{ els.drawer.innerHTML = ''; return; }}
      els.drawer.innerHTML = `
        <div>
          <h3>事件详情</h3>
          <p><strong>${{htmlEscape(e.company)}}</strong> · ${{htmlEscape(e.date)}} · ${{htmlEscape(e.category)}} / ${{htmlEscape(e.subtype)}}</p>
          <p style="margin-top:8px;">${{htmlEscape(e.title)}}</p>
          <p class="muted" style="margin-top:8px;">同组标题：${{htmlEscape(e.titles_sample || '无')}}</p>
        </div>
        <div>
          <h3>窗口与证据</h3>
          <p>5/20/60日市值变化：<span class="${{clsNum(e.mv_change_5d)}}">${{fmt(e.mv_change_5d)}}亿</span> / <span class="${{clsNum(e.mv_change_20d)}}">${{fmt(e.mv_change_20d)}}亿</span> / <span class="${{clsNum(e.mv_change_60d)}}">${{fmt(e.mv_change_60d)}}亿</span></p>
          <p>CAR[0,+20]：<span class="${{clsNum(e.car_20d)}}">${{fmtPct(e.car_20d)}}</span></p>
          <p>证据状态：<span class="tag ${{e.evidence_level}}">${{htmlEscape(e.evidence_label)}}</span> ${{htmlEscape(e.evidence_source || '')}}</p>
          <p style="margin-top:8px;">${{e.evidence_url ? `<a class="event-link" href="${{htmlEscape(e.evidence_url)}}" target="_blank" rel="noreferrer">打开证据链接</a>` : '暂无在线证据链接'}}</p>
          <p class="muted">${{e.local_path ? '本地PDF：' + htmlEscape(e.local_path) : ''}}</p>
        </div>`;
    }}

    function renderAll() {{
      updateStepState();
      populateCategories();
      updateStepState();
      renderMetrics();
      renderChart();
      renderMatrix();
      renderBasket();
      renderEvents();
    }}

    els.period.addEventListener('change', () => {{
      const maxT = Math.max(...marketRows.map(d => d.t));
      if (els.period.value === 'custom') {{
        els.start.value = dateStr(addDays(maxT, -365));
        els.end.value = dateStr(maxT);
      }} else {{
        els.start.value = '';
        els.end.value = '';
      }}
      populateMonths();
      renderAll();
    }});
    els.month.addEventListener('change', renderAll);
    els.start.addEventListener('change', renderAll);
    els.end.addEventListener('change', renderAll);
    els.win.addEventListener('change', renderAll);
    els.before.addEventListener('change', renderAll);
    els.after.addEventListener('change', renderAll);
    els.category.addEventListener('change', () => {{ els.subtype.value = ''; renderAll(); }});
    els.subtype.addEventListener('change', renderAll);
    els.search.addEventListener('input', renderAll);
    document.getElementById('clearBasket').addEventListener('click', () => {{ basket.splice(0, basket.length); renderAll(); }});
    function switchMode(mode, id) {{
      chartMode = mode;
      document.querySelectorAll('.seg button').forEach(b => b.classList.remove('active'));
      document.getElementById(id).classList.add('active');
      renderChart();
    }}
    document.getElementById('modeFocus').addEventListener('click', () => switchMode('focus', 'modeFocus'));
    document.getElementById('modeLane').addEventListener('click', () => switchMode('lane', 'modeLane'));
    document.getElementById('modeOverlay').addEventListener('click', () => switchMode('overlay', 'modeOverlay'));
    document.getElementById('modeBubble').addEventListener('click', () => switchMode('bubble', 'modeBubble'));
    document.getElementById('modeAligned').addEventListener('click', () => switchMode('aligned', 'modeAligned'));
    window.addEventListener('resize', renderChart);

    initCompanies();
    renderAll();
  </script>
</body>
</html>
"""


def main() -> int:
    payload = {
        "companies": [
            {"company": company, "ts_code": ts_code, "symbol": symbol} for company, ts_code, symbol in COMPANIES
        ],
        "marketRows": load_market_rows(),
        "events": load_event_rows(),
    }
    OUTPUT_PATH.write_text(build_html(payload), encoding="utf-8")
    sys.stdout.write(
        f"dashboard={OUTPUT_PATH}\nmarket_rows={len(payload['marketRows'])}\nevent_rows={len(payload['events'])}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

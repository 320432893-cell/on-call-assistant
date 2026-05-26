"""Build management-signal ledgers and source coverage gap tables."""

from __future__ import annotations

import math
import re
from hashlib import sha256
from pathlib import Path

import pandas as pd

RAW_DIR = Path("market-impact-study/data/raw")
TUSHARE_DIR = RAW_DIR / "tushare"
AKSHARE_DIR = RAW_DIR / "akshare"
EASTMONEY_IR_DIR = RAW_DIR / "eastmoney_ir"
PROCESSED_DIR = Path("market-impact-study/data/processed")
OUTPUT_DIR = PROCESSED_DIR / "management"

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
COMPANY_BY_NAME = {name: {"ts_code": ts_code, "symbol": symbol} for name, ts_code, symbol in COMPANIES}
COMPANY_BY_SYMBOL = {symbol.lstrip("0"): name for name, _, symbol in COMPANIES}
COMPANY_BY_TS_CODE = {ts_code: name for name, ts_code, _ in COMPANIES}

DATE_COLUMNS_BY_DATASET = {
    "eastmoney_ir": ["NOTICE_DATE", "END_DATE", "RECEIVE_START_DATE", "EITIME"],
    "irm_questions": ["更新时间", "提问时间"],
    "research_report": ["日期"],
    "stock_news": ["发布时间"],
    "individual_notice": ["公告日期"],
    "cninfo_disclosure_report": ["公告时间"],
}

SOURCE_KNOWN_LIMITS = {
    "eastmoney_ir": "东方财富机构调研/业绩说明会当前采集更偏近期，不代表上市以来全量管理层沟通。",
    "irm_questions": "互动易样本不含已失败的沪市/科创板 e 互动来源，且当前采集更偏近期。",
    "research_report": "东方财富研报可支撑卖方关注度第一版，但不代表全市场全部研报。",
    "stock_news": "东方财富个股新闻当前仅为近期少量样本，只能作为媒体传播辅助。",
    "individual_notice": "东方财富公告适合正式披露主线，但仍需结合 PDF/巨潮交叉校验。",
    "cninfo_disclosure_report": "巨潮信披适合正式披露主线，但公告正文/PDF挂接率需另看。",
}

SIGNAL_KEYWORDS = {
    "业绩说明": ["业绩说明", "业绩快报", "业绩预告", "年度报告", "半年报", "季报", "盈利", "利润", "营收"],
    "机构调研": ["调研", "机构", "接待", "路演", "投资者关系", "现场参观", "电话会议", "网络会议"],
    "互动问答": ["董秘", "投资者", "问答", "互动"],
    "战略表达": ["战略", "规划", "布局", "全球化", "海外", "国际市场", "业务拓展"],
    "产品技术": ["产品", "研发", "技术", "AI", "智能", "车联网", "物联网", "卫星", "模组", "终端"],
    "客户订单": ["客户", "订单", "中标", "合同", "合作", "项目", "在手订单"],
    "资本动作": ["回购", "分红", "股权激励", "员工持股", "定增", "募集资金", "减持", "增持", "质押"],
    "风险说明": ["问询函", "风险", "诉讼", "减值", "商誉", "存货", "应收", "异常波动"],
    "券商关注": ["评级", "买入", "增持", "研报", "盈利预测", "首次覆盖", "深度报告"],
}

MANAGEMENT_CATEGORIES = {
    "管理层/投关信号",
    "资本动作",
    "业绩信号",
    "产品/技术创新",
    "客户/订单",
    "风险事件",
}


def load_csv(path: Path, **kwargs: object) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def normalize_date(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def first_date(row: pd.Series, columns: list[str]) -> str:
    for column in columns:
        if column in row.index:
            value = normalize_date(row[column])
            if value:
                return value
    return ""


def clean_text(value: object, limit: int = 500) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if text.lower() == "nan":
        return ""
    return text[:limit]


def company_info(company: str, symbol: object = "") -> dict[str, str]:
    if company in COMPANY_BY_NAME:
        return COMPANY_BY_NAME[company]
    symbol_text = str(symbol).split(".")[0].lstrip("0")
    company_name = COMPANY_BY_SYMBOL.get(symbol_text)
    if company_name:
        return COMPANY_BY_NAME[company_name]
    return {"ts_code": "", "symbol": str(symbol)}


def load_list_dates() -> dict[str, str]:
    stock_basic = load_csv(TUSHARE_DIR / "stock_basic.csv", dtype=str)
    if stock_basic.empty:
        return {}
    selected = stock_basic[stock_basic["ts_code"].isin([ts_code for _, ts_code, _ in COMPANIES])].copy()
    selected["list_date_norm"] = selected["list_date"].map(normalize_date)
    return selected.set_index("ts_code")["list_date_norm"].to_dict()


def detect_topics(*parts: object) -> str:
    text = " ".join(clean_text(part, 2000) for part in parts if clean_text(part))
    topics = [topic for topic, words in SIGNAL_KEYWORDS.items() if any(word.lower() in text.lower() for word in words)]
    return "|".join(topics) if topics else "待归类"


def signal_group(source_type: str, category: str, topics: str) -> str:
    if source_type == "institution_survey" or "机构调研" in topics:
        return "投关沟通"
    if source_type == "irm_qa" or "互动问答" in topics:
        return "互动问答"
    if source_type == "research_report" or "券商关注" in topics:
        return "卖方认知"
    if "资本动作" in topics or category == "资本动作":
        return "资本配置/利益绑定"
    if "业绩说明" in topics or category == "业绩信号":
        return "业绩沟通"
    if "风险说明" in topics or category == "风险事件":
        return "风险沟通"
    if "产品技术" in topics or "客户订单" in topics:
        return "经营战略表达"
    return "管理层相关信息"


def make_signal_id(prefix: str, *parts: object) -> str:
    safe = "|".join(clean_text(part, 120) for part in parts)
    return f"{prefix}:{sha256(safe.encode('utf-8')).hexdigest()[:16]}"


def load_market_panel() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for _, ts_code, _ in COMPANIES:
        daily_path = TUSHARE_DIR / "daily" / f"{ts_code}.csv"
        basic_path = TUSHARE_DIR / "daily_basic" / f"{ts_code}.csv"
        if not daily_path.exists() or not basic_path.exists():
            continue
        daily = pd.read_csv(daily_path, dtype={"trade_date": str})
        basic = pd.read_csv(basic_path, dtype={"trade_date": str})
        merged = daily.merge(
            basic[["ts_code", "trade_date", "total_mv", "turnover_rate", "volume_ratio"]],
            on=["ts_code", "trade_date"],
            how="left",
        )
        merged["company"] = COMPANY_BY_TS_CODE[ts_code]
        frames.append(merged)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel["trade_dt"] = pd.to_datetime(panel["trade_date"], format="%Y%m%d", errors="coerce")
    for column in ["total_mv", "turnover_rate", "volume_ratio"]:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    return panel.sort_values(["ts_code", "trade_dt"]).reset_index(drop=True)


def build_market_lookup(panel: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], dict[str, float | str]]:
    if panel.empty:
        return {}
    stock_panels = {
        ts_code: group.sort_values("trade_dt").reset_index(drop=True) for ts_code, group in panel.groupby("ts_code")
    }
    lookup: dict[tuple[str, pd.Timestamp], dict[str, float | str]] = {}
    for ts_code, stock in stock_panels.items():
        for pos, row in stock.iterrows():
            pre_pos = max(0, pos - 1)
            pre_mv = stock.loc[pre_pos, "total_mv"]
            metrics: dict[str, float | str] = {
                "aligned_trade_date": row["trade_dt"].strftime("%Y-%m-%d"),
                "pre_total_mv_yi": pre_mv / 10000 if pd.notna(pre_mv) else math.nan,
                "event_turnover_rate": row.get("turnover_rate", math.nan),
                "event_volume_ratio": row.get("volume_ratio", math.nan),
            }
            for window in [5, 20, 60]:
                end_pos = min(len(stock) - 1, pos + window)
                end_mv = stock.loc[end_pos, "total_mv"]
                change = (end_mv - pre_mv) / 10000 if pd.notna(pre_mv) and pd.notna(end_mv) else math.nan
                ret = end_mv / pre_mv - 1 if pd.notna(pre_mv) and pre_mv else math.nan
                metrics[f"actual_mv_change_yi_p0_p{window}"] = change
                metrics[f"actual_mv_return_p0_p{window}"] = ret
                metrics[f"end_trade_date_p0_p{window}"] = stock.loc[end_pos, "trade_dt"].strftime("%Y-%m-%d")
            lookup[(ts_code, row["trade_dt"])] = metrics
    return lookup


def align_market_metrics(
    market_lookup: dict[tuple[str, pd.Timestamp], dict[str, float | str]],
    panel: pd.DataFrame,
    list_dates: dict[str, str],
    ts_code: str,
    event_date: str,
) -> dict[str, float | str]:
    if not event_date or panel.empty or not ts_code:
        return {}
    event_dt = pd.to_datetime(event_date, errors="coerce")
    if pd.isna(event_dt):
        return {}
    list_dt = pd.to_datetime(list_dates.get(ts_code, ""), errors="coerce")
    if pd.notna(list_dt) and event_dt < list_dt:
        return {"market_response_status": "pre_listing"}
    stock = panel[panel["ts_code"] == ts_code].sort_values("trade_dt").reset_index(drop=True)
    if stock.empty:
        return {"market_response_status": "missing_price"}
    first_trade_dt = stock.loc[0, "trade_dt"]
    if event_dt < first_trade_dt:
        return {"market_response_status": "before_price_coverage"}
    positions = stock.index[stock["trade_dt"] >= event_dt].tolist()
    if not positions:
        return {"market_response_status": "after_price_coverage"}
    aligned_dt = stock.loc[int(positions[0]), "trade_dt"]
    metrics = dict(market_lookup.get((ts_code, aligned_dt), {}))
    metrics["market_response_status"] = "ok"
    add_peer_metrics(metrics, market_lookup, panel, ts_code, aligned_dt)
    return metrics


def add_peer_metrics(
    metrics: dict[str, float | str],
    market_lookup: dict[tuple[str, pd.Timestamp], dict[str, float | str]],
    panel: pd.DataFrame,
    ts_code: str,
    aligned_dt: pd.Timestamp,
) -> None:
    same_day_codes = set(panel.loc[panel["trade_dt"] == aligned_dt, "ts_code"])
    for window in [5, 20, 60]:
        values: list[tuple[str, float]] = []
        for code in same_day_codes:
            code_metrics = market_lookup.get((code, aligned_dt), {})
            value = code_metrics.get(f"actual_mv_return_p0_p{window}", math.nan)
            if pd.notna(value):
                values.append((code, float(value)))
        peer_values = [value for code, value in values if code != ts_code]
        own_values = [value for code, value in values if code == ts_code]
        metrics[f"peer_avg_mv_return_p0_p{window}"] = sum(peer_values) / len(peer_values) if peer_values else math.nan
        metrics[f"peer_count_p0_p{window}"] = len(peer_values)
        if own_values:
            ranked = sorted(values, key=lambda item: item[1], reverse=True)
            rank = next((index + 1 for index, (code, _) in enumerate(ranked) if code == ts_code), math.nan)
            metrics[f"peer_rank_by_mv_return_p0_p{window}"] = rank
            metrics[f"peer_rank_total_p0_p{window}"] = len(ranked)


def market_response_label(row: dict[str, object]) -> str:
    if row.get("market_response_status") in {
        "after_price_coverage",
        "before_price_coverage",
        "pre_listing",
        "missing_price",
    }:
        return "无行情覆盖"
    ret = row.get("actual_mv_return_p0_p20", math.nan)
    peer = row.get("peer_avg_mv_return_p0_p20", math.nan)
    if pd.isna(ret):
        return "无行情覆盖"
    if pd.isna(peer):
        return "仅有自身表现"
    diff = float(ret) - float(peer)
    if diff >= 0.05:
        return "明显跑赢竞品"
    if diff <= -0.05:
        return "明显跑输竞品"
    return "接近竞品均值"


def base_record(
    *,
    source_dataset: str,
    source_type: str,
    company: str,
    event_date: str,
    occurred_date: str = "",
    disclosed_date: str = "",
    date_basis: str = "",
    title: str,
    summary: str = "",
    raw_category: str = "",
    source_url: str = "",
    local_pdf_path: str = "",
    rating: str = "",
    institution: str = "",
    institution_count: object = "",
    receptionist: str = "",
    receive_way: str = "",
    evidence_count: object = "",
) -> dict[str, object]:
    info = company_info(company)
    topics = detect_topics(title, summary, raw_category, rating, institution, receptionist, receive_way)
    group = signal_group(source_type, raw_category, topics)
    return {
        "signal_id": make_signal_id(source_type, company, event_date, title, summary),
        "source_dataset": source_dataset,
        "source_type": source_type,
        "company": company,
        "ts_code": info["ts_code"],
        "symbol": info["symbol"],
        "event_date": event_date,
        "occurred_date": occurred_date,
        "disclosed_date": disclosed_date,
        "date_basis": date_basis or "event_date",
        "management_signal_group": group,
        "management_signal_topics": topics,
        "primary_category": raw_category,
        "title": title,
        "summary": summary,
        "rating": rating,
        "institution": institution,
        "institution_count": institution_count,
        "receptionist": receptionist,
        "receive_way": receive_way,
        "source_url": source_url,
        "local_pdf_path": local_pdf_path,
        "evidence_count": evidence_count,
    }


def records_from_event_groups() -> list[dict[str, object]]:
    groups = load_csv(PROCESSED_DIR / "event_analysis_groups_scored.csv")
    if groups.empty:
        return []
    text = (
        groups["title"].fillna("")
        + " "
        + groups.get("summary", pd.Series("", index=groups.index)).fillna("")
        + " "
        + groups.get("raw_category", pd.Series("", index=groups.index)).fillna("")
    )
    topic_mask = text.map(lambda value: detect_topics(value) != "待归类")
    raw_direct_sources = {"institution_survey", "irm_qa", "research_report", "news"}
    non_direct_source_mask = ~groups["source_type"].isin(raw_direct_sources)
    category_mask = groups["primary_category"].isin(MANAGEMENT_CATEGORIES)
    selected = groups[non_direct_source_mask & (category_mask | topic_mask)].copy()
    records: list[dict[str, object]] = []
    metric_cols = [
        "analysis_group_id",
        "car_status",
        "aligned_trade_date",
        "pre_total_mv_yi",
        "event_turnover_rate",
        "event_volume_ratio",
        "actual_mv_return_p0_p5",
        "actual_mv_return_p0_p20",
        "actual_mv_return_p0_p60",
        "actual_mv_change_yi_p0_p20",
        "peer_avg_mv_return_p0_p20",
        "peer_rank_by_mv_return_p0_p20",
        "peer_rank_total_p0_p20",
        "car_p0_p20",
        "abnormal_mv_impact_yi_p0_p20",
        "group_event_count",
        "group_source_count",
        "group_evidence_count",
        "group_titles_sample",
    ]
    for _, row in selected.iterrows():
        record = base_record(
            source_dataset="event_analysis_groups_scored",
            source_type=clean_text(row.get("source_type")),
            company=clean_text(row.get("company")),
            event_date=normalize_date(row.get("event_date")),
            title=clean_text(row.get("title")),
            summary=clean_text(row.get("summary")),
            raw_category=clean_text(row.get("primary_category")),
            source_url=clean_text(row.get("source_url")),
            local_pdf_path=clean_text(row.get("local_pdf_path")),
            rating=clean_text(row.get("rating")),
            institution=clean_text(row.get("institution")),
            institution_count=row.get("institution_count", ""),
            receptionist=clean_text(row.get("receptionist")),
            evidence_count=row.get("group_evidence_count", ""),
        )
        for column in metric_cols:
            if column in row.index:
                record[column] = row[column]
        record["market_response_status"] = clean_text(row.get("car_status")) or "ok"
        records.append(record)
    return records


def records_from_eastmoney_ir(
    market_lookup: dict, panel: pd.DataFrame, list_dates: dict[str, str]
) -> list[dict[str, object]]:
    df = load_csv(EASTMONEY_IR_DIR / "all_companies_ir.csv")
    records = []
    for _, row in df.iterrows():
        company = clean_text(row.get("LOCAL_COMPANY_NAME"))
        disclosed_date = first_date(row, ["NOTICE_DATE", "EITIME"])
        occurred_date = first_date(row, ["END_DATE", "RECEIVE_START_DATE"])
        event_date = disclosed_date or occurred_date
        receive_way = clean_text(row.get("RECEIVE_WAY_EXPLAIN") or row.get("RECEIVE_WAY"))
        title = clean_text(f"{company} {receive_way} {row.get('RECEIVE_TIME_EXPLAIN', '')}", 240)
        summary = clean_text(f"{row.get('RECEIVE_OBJECT', '')} {row.get('RECEIVE_PLACE', '')}", 500)
        record = base_record(
            source_dataset="eastmoney_ir",
            source_type="institution_survey",
            company=company,
            event_date=event_date,
            occurred_date=occurred_date,
            disclosed_date=disclosed_date,
            date_basis="disclosed_date" if disclosed_date else "occurred_date",
            title=title,
            summary=summary,
            raw_category="管理层/投关信号",
            institution_count=row.get("NUMBERNEW") or row.get("NUM") or "",
            receptionist=clean_text(row.get("RECEPTIONIST")),
            receive_way=receive_way,
        )
        record.update(align_market_metrics(market_lookup, panel, list_dates, record["ts_code"], event_date))
        records.append(record)
    return records


def records_from_irm_questions(
    market_lookup: dict, panel: pd.DataFrame, list_dates: dict[str, str]
) -> list[dict[str, object]]:
    df = load_csv(AKSHARE_DIR / "cninfo_irm_questions" / "all_companies.csv")
    records = []
    for _, row in df.iterrows():
        company = clean_text(row.get("LOCAL_COMPANY_NAME"))
        event_date = first_date(row, DATE_COLUMNS_BY_DATASET["irm_questions"])
        record = base_record(
            source_dataset="cninfo_irm_questions",
            source_type="irm_qa",
            company=company,
            event_date=event_date,
            disclosed_date=event_date,
            date_basis="disclosed_date",
            title=clean_text(row.get("问题")),
            summary=clean_text(row.get("回答内容")),
            raw_category="管理层/投关信号",
            receptionist=clean_text(row.get("回答者")),
            receive_way=clean_text(row.get("来源")),
        )
        record.update(align_market_metrics(market_lookup, panel, list_dates, record["ts_code"], event_date))
        records.append(record)
    return records


def records_from_research_reports(
    market_lookup: dict, panel: pd.DataFrame, list_dates: dict[str, str]
) -> list[dict[str, object]]:
    df = load_csv(AKSHARE_DIR / "eastmoney_research_report" / "all_companies.csv")
    records = []
    for _, row in df.iterrows():
        company = clean_text(row.get("LOCAL_COMPANY_NAME"))
        event_date = first_date(row, DATE_COLUMNS_BY_DATASET["research_report"])
        summary = clean_text(
            f"评级={row.get('东财评级', '')}; 2026EPS={row.get('2026-盈利预测-收益', '')}; "
            f"2026PE={row.get('2026-盈利预测-市盈率', '')}",
            500,
        )
        record = base_record(
            source_dataset="eastmoney_research_report",
            source_type="research_report",
            company=company,
            event_date=event_date,
            disclosed_date=event_date,
            date_basis="disclosed_date",
            title=clean_text(row.get("报告名称")),
            summary=summary,
            raw_category="券商关注",
            source_url=clean_text(row.get("报告PDF链接")),
            rating=clean_text(row.get("东财评级")),
            institution=clean_text(row.get("机构")),
            institution_count=row.get("近一月个股研报数", ""),
        )
        record.update(align_market_metrics(market_lookup, panel, list_dates, record["ts_code"], event_date))
        records.append(record)
    return records


def records_from_news(market_lookup: dict, panel: pd.DataFrame, list_dates: dict[str, str]) -> list[dict[str, object]]:
    df = load_csv(AKSHARE_DIR / "eastmoney_stock_news" / "all_companies.csv")
    records = []
    for _, row in df.iterrows():
        company = clean_text(row.get("LOCAL_COMPANY_NAME"))
        event_date = first_date(row, DATE_COLUMNS_BY_DATASET["stock_news"])
        topics = detect_topics(row.get("新闻标题"), row.get("新闻内容"), row.get("关键词"), row.get("文章来源"))
        if topics == "待归类":
            continue
        record = base_record(
            source_dataset="eastmoney_stock_news",
            source_type="news",
            company=company,
            event_date=event_date,
            disclosed_date=event_date,
            date_basis="disclosed_date",
            title=clean_text(row.get("新闻标题")),
            summary=clean_text(row.get("新闻内容")),
            raw_category=clean_text(row.get("关键词")),
            source_url=clean_text(row.get("新闻链接")),
            institution=clean_text(row.get("文章来源")),
        )
        record.update(align_market_metrics(market_lookup, panel, list_dates, record["ts_code"], event_date))
        records.append(record)
    return records


def build_ledger() -> pd.DataFrame:
    panel = load_market_panel()
    list_dates = load_list_dates()
    market_lookup = build_market_lookup(panel)
    records = []
    records.extend(records_from_event_groups())
    records.extend(records_from_eastmoney_ir(market_lookup, panel, list_dates))
    records.extend(records_from_irm_questions(market_lookup, panel, list_dates))
    records.extend(records_from_research_reports(market_lookup, panel, list_dates))
    records.extend(records_from_news(market_lookup, panel, list_dates))
    ledger = pd.DataFrame(records)
    if ledger.empty:
        return ledger
    ledger["market_response_label"] = ledger.apply(lambda row: market_response_label(row.to_dict()), axis=1)
    ledger["is_subject_company"] = ledger["company"].eq("移为通信").astype(int)
    ledger["car_is_auxiliary"] = ledger["car_p0_p20"].notna().astype(int) if "car_p0_p20" in ledger else 0
    ledger = ledger.sort_values(["event_date", "company", "source_type", "title"], ascending=[False, True, True, True])
    return ledger.drop_duplicates(subset=["signal_id"]).reset_index(drop=True)


def dataset_path(dataset: str) -> Path:
    mapping = {
        "eastmoney_ir": EASTMONEY_IR_DIR / "all_companies_ir.csv",
        "irm_questions": AKSHARE_DIR / "cninfo_irm_questions" / "all_companies.csv",
        "research_report": AKSHARE_DIR / "eastmoney_research_report" / "all_companies.csv",
        "stock_news": AKSHARE_DIR / "eastmoney_stock_news" / "all_companies.csv",
        "individual_notice": AKSHARE_DIR / "eastmoney_individual_notice" / "all_companies.csv",
        "cninfo_disclosure_report": AKSHARE_DIR / "cninfo_disclosure_report" / "all_companies.csv",
    }
    return mapping[dataset]


def company_column(df: pd.DataFrame) -> str:
    for column in ["LOCAL_COMPANY_NAME", "公司简称", "股票简称", "名称", "简称"]:
        if column in df.columns:
            return column
    return ""


def coverage_assessment(dataset: str, rows: int, first: str, last: str) -> tuple[str, str, str]:
    if rows == 0:
        return "缺失", "该公司在当前汇总表无记录，不能判断该类信息是否完整", "补采交易所/数据源对应公司数据"
    first_dt = pd.to_datetime(first, errors="coerce")
    last_dt = pd.to_datetime(last, errors="coerce")
    span_days = (last_dt - first_dt).days if pd.notna(first_dt) and pd.notna(last_dt) else 0
    if dataset in {"eastmoney_ir", "irm_questions", "stock_news"} and span_days < 730:
        return (
            "部分覆盖",
            "当前采集更偏近期，不适合声称覆盖上市以来全量信息",
            "如用于长期对比，需补采历史调研/问答/新闻",
        )
    if dataset == "research_report" and rows < 5:
        return "弱覆盖", "研报数量较少，卖方关注度横向比较可能失真", "补充其他研报源或仅作方向性参考"
    return "第一版可用", "记录非空且时间跨度可支撑第一版描述，但不等于信息全量", "进入报告时仍需标注来源口径"


def build_coverage_gaps() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    list_dates = load_list_dates()
    data_as_of = pd.Timestamp.today().strftime("%Y-%m-%d")
    for dataset in DATE_COLUMNS_BY_DATASET:
        path = dataset_path(dataset)
        df = load_csv(path)
        company_col = company_column(df)
        for company, ts_code, symbol in COMPANIES:
            company_df = df[df[company_col] == company].copy() if company_col and not df.empty else pd.DataFrame()
            dates = []
            for _, row in company_df.iterrows():
                date = first_date(row, DATE_COLUMNS_BY_DATASET[dataset])
                if date:
                    dates.append(date)
            first = min(dates) if dates else ""
            last = max(dates) if dates else ""
            status, limitation, recommendation = coverage_assessment(dataset, len(company_df), first, last)
            expected_start = list_dates.get(ts_code, "")
            parse_rate = len(dates) / len(company_df) if len(company_df) else 0
            rows.append(
                {
                    "dataset": dataset,
                    "company": company,
                    "ts_code": ts_code,
                    "symbol": symbol,
                    "rows": len(company_df),
                    "first_date": first,
                    "last_date": last,
                    "expected_start_date": expected_start,
                    "expected_end_date": data_as_of,
                    "date_parse_rate": round(parse_rate, 4),
                    "source_known_limit": SOURCE_KNOWN_LIMITS.get(dataset, ""),
                    "completeness_level": "不完整/需补采"
                    if status in {"缺失", "部分覆盖", "弱覆盖"}
                    else "第一版可用/非全量承诺",
                    "coverage_status": status,
                    "limitation": limitation,
                    "recommendation": recommendation,
                    "source_path": path.as_posix(),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = build_ledger()
    gaps = build_coverage_gaps()
    ledger.to_csv(OUTPUT_DIR / "management_signal_ledger.csv", index=False, encoding="utf-8-sig")
    gaps.to_csv(OUTPUT_DIR / "management_signal_coverage_gaps.csv", index=False, encoding="utf-8-sig")
    print(f"wrote {OUTPUT_DIR / 'management_signal_ledger.csv'} rows={len(ledger)}")
    print(f"wrote {OUTPUT_DIR / 'management_signal_coverage_gaps.csv'} rows={len(gaps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

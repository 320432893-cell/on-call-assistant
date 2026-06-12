"""生成 CFO 视角的事件-市值变化-证据链主表。"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_DIR / "data/processed"
DOC_REPORTS_DIR = PROJECT_DIR / "docs/reports"

EVENTS_PATH = PROCESSED_DIR / "rag_event_group_evidence_enhanced.csv"
GROUPS_PATH = PROCESSED_DIR / "event_analysis_groups_scored.csv"
CANDIDATES_PATH = PROCESSED_DIR / "event_candidates_scored.csv"

OUTPUT_MAIN = PROCESSED_DIR / "cfo_event_evidence_chain.csv"
OUTPUT_POSITIVE = PROCESSED_DIR / "cfo_event_evidence_chain_top_positive.csv"
OUTPUT_NEGATIVE = PROCESSED_DIR / "cfo_event_evidence_chain_top_negative.csv"
OUTPUT_POSITIVE_WITH_EVIDENCE = PROCESSED_DIR / "cfo_event_evidence_chain_top_positive_with_evidence.csv"
OUTPUT_NEGATIVE_WITH_EVIDENCE = PROCESSED_DIR / "cfo_event_evidence_chain_top_negative_with_evidence.csv"
OUTPUT_PRIORITY = PROCESSED_DIR / "cfo_event_evidence_chain_priority_top.csv"
OUTPUT_SUMMARY = DOC_REPORTS_DIR / "CFO_EVENT_EVIDENCE_CHAIN_SUMMARY.md"

TOP_N = 100

WINDOWS = {
    "5日": "p0_p5",
    "20日": "p0_p20",
    "60日": "p0_p60",
}

BASE_COLUMNS = [
    "analysis_group_id",
    "event_id",
    "event_date",
    "company",
    "symbol",
    "primary_category",
    "title",
    "group_titles_sample",
    "source_type",
    "source_types",
    "group_event_count",
    "pre_total_mv_yi",
    "event_priority_score",
    "objective_change_score",
    "car_status",
    "rag_coverage_status",
    "rag_best_evidence_strength",
    "rag_best_text_source",
    "rag_best_title",
    "rag_best_publish_date",
    "rag_best_score",
    "rag_best_date_diff_days",
    "rag_best_pdf_url",
    "rag_best_local_path",
    "rag_best_page_start",
    "rag_evidence_refs",
    "rag_match_method",
    "rag_match_strength",
]

GROUP_JOIN_COLUMNS = [
    "analysis_group_id",
    "source_url",
    "pdf_url",
    "local_pdf_path",
    "raw_category",
    "category_tags",
    "is_subject_company",
    "is_peer_event",
    "is_ipo_listing_related",
    "is_market_trading_related",
    "event_turnover_rate",
    "event_volume_ratio",
    "aligned_trade_date",
    "pre_trade_date",
]

CHINESE_COLUMNS = {
    "analysis_group_id": "分析事件组ID",
    "event_id": "代表事件ID",
    "event_date": "事件日期",
    "aligned_trade_date": "对齐交易日",
    "company": "公司",
    "symbol": "股票代码",
    "primary_category": "一级分类",
    "event_subtype": "二级事件",
    "title": "代表事件标题",
    "group_titles_sample": "同组事件标题样例",
    "source_type": "代表来源类型",
    "source_types": "同组来源类型",
    "raw_category": "原始分类",
    "category_tags": "分类标签",
    "group_event_count": "同组事件数",
    "pre_total_mv_yi": "事件前市值_亿元",
    "actual_mv_change_yi_p0_p5": "5日客观市值变化_亿元",
    "actual_mv_change_yi_p0_p20": "20日客观市值变化_亿元",
    "actual_mv_change_yi_p0_p60": "60日客观市值变化_亿元",
    "actual_mv_return_p0_p5": "5日客观市值收益率",
    "actual_mv_return_p0_p20": "20日客观市值收益率",
    "actual_mv_return_p0_p60": "60日客观市值收益率",
    "peer_avg_mv_return_p0_p5": "5日竞品平均市值收益率",
    "peer_avg_mv_return_p0_p20": "20日竞品平均市值收益率",
    "peer_avg_mv_return_p0_p60": "60日竞品平均市值收益率",
    "peer_relative_return_p0_p5": "5日相对竞品收益率",
    "peer_relative_return_p0_p20": "20日相对竞品收益率",
    "peer_relative_return_p0_p60": "60日相对竞品收益率",
    "peer_relative_mv_change_yi_p0_p5": "5日相对竞品市值变化_亿元",
    "peer_relative_mv_change_yi_p0_p20": "20日相对竞品市值变化_亿元",
    "peer_relative_mv_change_yi_p0_p60": "60日相对竞品市值变化_亿元",
    "car_p0_p5": "5日CAR_辅助",
    "car_p0_p20": "20日CAR_辅助",
    "car_p0_p60": "60日CAR_辅助",
    "abnormal_mv_impact_yi_p0_p20": "20日异常市值影响_辅助_亿元",
    "event_priority_score": "事件优先级评分",
    "objective_change_score": "客观变化评分",
    "cfo_rank_score": "CFO排序评分",
    "car_status": "CAR状态",
    "evidence_level": "证据等级",
    "evidence_level_label": "证据等级标签",
    "evidence_available": "是否有证据",
    "rag_coverage_status": "RAG覆盖状态",
    "rag_best_evidence_strength": "RAG最佳证据强度",
    "rag_best_text_source": "RAG最佳文本来源",
    "rag_best_title": "最佳证据标题",
    "rag_best_publish_date": "最佳证据日期",
    "rag_best_score": "最佳证据得分",
    "rag_best_date_diff_days": "最佳证据日期差_天",
    "best_evidence_summary": "最佳证据摘要",
    "source_url": "事件来源链接",
    "pdf_url": "事件PDF链接",
    "evidence_url": "优先证据链接",
    "local_pdf_path": "事件PDF本地路径",
    "rag_best_local_path": "RAG证据本地路径",
    "rag_best_page_start": "RAG证据页码",
    "rag_match_method": "RAG匹配方法",
    "rag_match_strength": "RAG匹配强度",
    "is_subject_company": "是否移为自身",
    "is_peer_event": "是否竞品事件",
    "is_ipo_listing_related": "是否上市初期事件",
    "is_market_trading_related": "是否交易异常事件",
    "event_turnover_rate": "事件日换手率",
    "event_volume_ratio": "事件日量比",
}

OUTPUT_COLUMNS = [
    "analysis_group_id",
    "event_id",
    "event_date",
    "aligned_trade_date",
    "company",
    "symbol",
    "primary_category",
    "event_subtype",
    "title",
    "group_titles_sample",
    "source_type",
    "source_types",
    "raw_category",
    "category_tags",
    "group_event_count",
    "pre_total_mv_yi",
    "actual_mv_change_yi_p0_p5",
    "actual_mv_change_yi_p0_p20",
    "actual_mv_change_yi_p0_p60",
    "actual_mv_return_p0_p5",
    "actual_mv_return_p0_p20",
    "actual_mv_return_p0_p60",
    "peer_avg_mv_return_p0_p5",
    "peer_avg_mv_return_p0_p20",
    "peer_avg_mv_return_p0_p60",
    "peer_relative_return_p0_p5",
    "peer_relative_return_p0_p20",
    "peer_relative_return_p0_p60",
    "peer_relative_mv_change_yi_p0_p5",
    "peer_relative_mv_change_yi_p0_p20",
    "peer_relative_mv_change_yi_p0_p60",
    "car_p0_p5",
    "car_p0_p20",
    "car_p0_p60",
    "abnormal_mv_impact_yi_p0_p20",
    "event_priority_score",
    "objective_change_score",
    "cfo_rank_score",
    "car_status",
    "evidence_level",
    "evidence_level_label",
    "evidence_available",
    "rag_coverage_status",
    "rag_best_evidence_strength",
    "rag_best_text_source",
    "rag_best_title",
    "rag_best_publish_date",
    "rag_best_score",
    "rag_best_date_diff_days",
    "best_evidence_summary",
    "source_url",
    "pdf_url",
    "evidence_url",
    "local_pdf_path",
    "rag_best_local_path",
    "rag_best_page_start",
    "rag_match_method",
    "rag_match_strength",
    "is_subject_company",
    "is_peer_event",
    "is_ipo_listing_related",
    "is_market_trading_related",
    "event_turnover_rate",
    "event_volume_ratio",
]

EVIDENCE_LEVEL_ORDER = {
    "强证据": 3,
    "辅助证据": 2,
    "弱证据": 1,
    "无证据": 0,
}

NUMERIC_OUTPUT_COLUMNS = [
    "同组事件数",
    "事件前市值_亿元",
    "5日客观市值变化_亿元",
    "20日客观市值变化_亿元",
    "60日客观市值变化_亿元",
    "5日客观市值收益率",
    "20日客观市值收益率",
    "60日客观市值收益率",
    "5日竞品平均市值收益率",
    "20日竞品平均市值收益率",
    "60日竞品平均市值收益率",
    "5日相对竞品收益率",
    "20日相对竞品收益率",
    "60日相对竞品收益率",
    "5日相对竞品市值变化_亿元",
    "20日相对竞品市值变化_亿元",
    "60日相对竞品市值变化_亿元",
    "5日CAR_辅助",
    "20日CAR_辅助",
    "60日CAR_辅助",
    "20日异常市值影响_辅助_亿元",
    "事件优先级评分",
    "客观变化评分",
    "CFO排序评分",
    "证据等级",
    "最佳证据得分",
    "最佳证据日期差_天",
    "RAG证据页码",
    "事件日换手率",
    "事件日量比",
]


def read_csv(path: Path, *, usecols: list[str] | None = None) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, usecols=usecols).fillna("")


def text_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(math.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", text_value(value)).strip()


def first_evidence_excerpt(value: object, *, max_chars: int = 220) -> str:
    text = compact_text(value)
    if not text:
        return ""
    first = text.split(" || ", maxsplit=1)[0]
    first = re.sub(r"^\d{4}-\d{2}-\d{2}《[^》]+》p\d*:\s*", "", first)
    first = re.sub(r"^标题：[^ 摘要]+", "", first)
    return first[:max_chars]


def evidence_level(row: pd.Series) -> str:
    status = text_value(row.get("rag_coverage_status"))
    strength = text_value(row.get("rag_best_evidence_strength")).lower()
    source = text_value(row.get("rag_best_text_source"))
    if "strong" in strength or source in {"pdf", "notice_api"}:
        return "强证据"
    if "aux" in strength or source in {"research_report", "ir_record", "irm_qa", "news"}:
        return "辅助证据"
    if status and status != "no_rag_evidence":
        return "弱证据"
    return "无证据"


def classify_event_subtype(row: pd.Series) -> str:
    category = text_value(row.get("primary_category"))
    text = " ".join(
        compact_text(row.get(column))
        for column in ["title", "group_titles_sample", "raw_category", "category_tags", "source_type"]
    )
    rules = {
        "业绩信号": [
            ("定期报告", ("年度报告", "半年度报告", "季度报告", "一季报", "三季报")),
            ("业绩预告/快报", ("业绩预告", "业绩快报", "业绩修正")),
            ("利润/营收变化", ("利润", "营收", "收入", "亏损", "扭亏")),
        ],
        "资本动作": [
            ("分红/权益分派", ("分红", "权益分派", "利润分配")),
            ("股份回购", ("回购股份", "股份回购", "回购公司股份", "回购报告书", "集中竞价交易方式回购")),
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
            ("车联网/物联网", ("车联网", "物联网", "智能终端", "AIoT")),
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
            ("异常波动/停复牌", ("异常波动", "停牌", "复牌")),
        ],
    }
    for subtype, keywords in rules.get(category, []):
        if any(keyword in text for keyword in keywords):
            return subtype
    if "research" in text_value(row.get("source_type")):
        return "研报事件"
    if "ir" in text_value(row.get("source_type")):
        return "调研/投关事件"
    if "announcement" in text_value(row.get("source_type")):
        return "公告事件"
    return "其他事件"


def load_group_details() -> pd.DataFrame:
    columns = pd.read_csv(GROUPS_PATH, nrows=0).columns.tolist()
    wanted = [column for column in GROUP_JOIN_COLUMNS if column in columns]
    for label, suffix in WINDOWS.items():
        _ = label
        wanted.extend(
            column
            for column in [
                f"peer_avg_mv_return_{suffix}",
                f"peer_rank_by_mv_return_{suffix}",
                f"peer_rank_total_{suffix}",
                f"peer_percentile_by_mv_return_{suffix}",
            ]
            if column in columns
        )
    return read_csv(GROUPS_PATH, usecols=wanted).drop_duplicates("analysis_group_id")


def load_link_lookup() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in [GROUPS_PATH, CANDIDATES_PATH]:
        columns = pd.read_csv(path, nrows=0).columns.tolist()
        wanted = [column for column in ["event_id", "source_url", "pdf_url", "local_pdf_path"] if column in columns]
        if "event_id" not in wanted:
            continue
        frames.append(read_csv(path, usecols=wanted))
    if not frames:
        return pd.DataFrame(columns=["event_id", "source_url_lookup", "pdf_url_lookup", "local_pdf_path_lookup"])
    links = pd.concat(frames, ignore_index=True)
    rows: list[dict[str, str]] = []
    for event_id, group in links.groupby("event_id", sort=False):
        row = {"event_id": text_value(event_id)}
        for column in ["source_url", "pdf_url", "local_pdf_path"]:
            values = [text_value(value) for value in group[column].tolist() if text_value(value)]
            row[f"{column}_lookup"] = values[0] if values else ""
        rows.append(row)
    return pd.DataFrame(rows)


def attach_peer_relative_columns(frame: pd.DataFrame) -> pd.DataFrame:
    pre_mv = numeric(frame, "pre_total_mv_yi")
    for suffix in WINDOWS.values():
        actual_return = numeric(frame, f"actual_mv_return_{suffix}")
        peer_return = numeric(frame, f"peer_avg_mv_return_{suffix}")
        relative_return = actual_return - peer_return
        frame[f"peer_relative_return_{suffix}"] = relative_return
        frame[f"peer_relative_mv_change_yi_{suffix}"] = pre_mv * relative_return
    return frame


def normalize_output_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    for column in NUMERIC_OUTPUT_COLUMNS:
        if column not in frame.columns:
            continue
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    precision = {
        "同组事件数": 0,
        "证据等级": 0,
        "RAG证据页码": 0,
        "最佳证据日期差_天": 0,
        "事件前市值_亿元": 4,
        "5日客观市值变化_亿元": 4,
        "20日客观市值变化_亿元": 4,
        "60日客观市值变化_亿元": 4,
        "5日相对竞品市值变化_亿元": 4,
        "20日相对竞品市值变化_亿元": 4,
        "60日相对竞品市值变化_亿元": 4,
        "20日异常市值影响_辅助_亿元": 4,
        "5日客观市值收益率": 6,
        "20日客观市值收益率": 6,
        "60日客观市值收益率": 6,
        "5日竞品平均市值收益率": 6,
        "20日竞品平均市值收益率": 6,
        "60日竞品平均市值收益率": 6,
        "5日相对竞品收益率": 6,
        "20日相对竞品收益率": 6,
        "60日相对竞品收益率": 6,
        "5日CAR_辅助": 6,
        "20日CAR_辅助": 6,
        "60日CAR_辅助": 6,
        "事件优先级评分": 4,
        "客观变化评分": 4,
        "CFO排序评分": 4,
        "最佳证据得分": 4,
        "事件日换手率": 4,
        "事件日量比": 4,
    }
    for column, digits in precision.items():
        if column in frame.columns:
            frame[column] = frame[column].round(digits)
    return frame


def build_chain() -> pd.DataFrame:
    events = read_csv(
        EVENTS_PATH,
        usecols=BASE_COLUMNS
        + [
            column
            for suffix in WINDOWS.values()
            for column in [
                f"actual_mv_change_yi_{suffix}",
                f"actual_mv_return_{suffix}",
                f"car_{suffix}",
            ]
        ]
        + ["abnormal_mv_impact_yi_p0_p20"],
    )
    groups = load_group_details()
    links = load_link_lookup()
    frame = events.merge(groups, on="analysis_group_id", how="left", suffixes=("", "_group"))
    frame = frame.merge(links, on="event_id", how="left")

    for column in ["source_url", "pdf_url", "local_pdf_path"]:
        lookup = f"{column}_lookup"
        if column not in frame.columns:
            frame[column] = ""
        if lookup in frame.columns:
            frame[column] = frame[column].where(frame[column].astype(str).str.len() > 0, frame[lookup])

    frame["event_subtype"] = frame.apply(classify_event_subtype, axis=1)
    frame["evidence_level_label"] = frame.apply(evidence_level, axis=1)
    frame["evidence_level"] = frame["evidence_level_label"].map(EVIDENCE_LEVEL_ORDER).fillna(0).astype(int)
    frame["evidence_available"] = frame["evidence_level"].gt(0).map({True: "是", False: "否"})
    frame["best_evidence_summary"] = frame["rag_evidence_refs"].map(first_evidence_excerpt)
    frame["evidence_url"] = frame["rag_best_pdf_url"]
    frame["evidence_url"] = frame["evidence_url"].where(
        frame["evidence_url"].astype(str).str.len() > 0, frame["pdf_url"]
    )
    frame["evidence_url"] = frame["evidence_url"].where(
        frame["evidence_url"].astype(str).str.len() > 0, frame["source_url"]
    )
    frame = attach_peer_relative_columns(frame)

    abs_objective = numeric(frame, "actual_mv_change_yi_p0_p20").abs().fillna(0)
    priority = numeric(frame, "event_priority_score").fillna(0)
    evidence_bonus = frame["evidence_level"].astype(float) * 5
    frame["cfo_rank_score"] = abs_objective + priority + evidence_bonus

    for column in OUTPUT_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    output = frame[OUTPUT_COLUMNS].copy()
    output = output.sort_values(
        ["cfo_rank_score", "evidence_level", "event_priority_score"], ascending=[False, False, False]
    )
    output = output.rename(columns=CHINESE_COLUMNS)
    return normalize_output_numbers(output)


def write_outputs(chain: pd.DataFrame) -> None:
    chain.to_csv(OUTPUT_MAIN, index=False, encoding="utf-8-sig")

    objective_change = pd.to_numeric(chain["20日客观市值变化_亿元"], errors="coerce")
    positive = chain[objective_change > 0].copy()
    positive = positive.sort_values(["20日客观市值变化_亿元", "证据等级"], ascending=[False, False]).head(TOP_N)
    positive.to_csv(OUTPUT_POSITIVE, index=False, encoding="utf-8-sig")

    negative = chain[objective_change < 0].copy()
    negative = negative.sort_values(["20日客观市值变化_亿元", "证据等级"], ascending=[True, False]).head(TOP_N)
    negative.to_csv(OUTPUT_NEGATIVE, index=False, encoding="utf-8-sig")

    with_evidence = chain[pd.to_numeric(chain["证据等级"], errors="coerce") > 0].copy()
    positive_with_evidence = with_evidence[pd.to_numeric(with_evidence["20日客观市值变化_亿元"], errors="coerce") > 0]
    positive_with_evidence = positive_with_evidence.sort_values(
        ["20日客观市值变化_亿元", "证据等级", "事件优先级评分"], ascending=[False, False, False]
    ).head(TOP_N)
    positive_with_evidence.to_csv(OUTPUT_POSITIVE_WITH_EVIDENCE, index=False, encoding="utf-8-sig")

    negative_with_evidence = with_evidence[pd.to_numeric(with_evidence["20日客观市值变化_亿元"], errors="coerce") < 0]
    negative_with_evidence = negative_with_evidence.sort_values(
        ["20日客观市值变化_亿元", "证据等级", "事件优先级评分"], ascending=[True, False, False]
    ).head(TOP_N)
    negative_with_evidence.to_csv(OUTPUT_NEGATIVE_WITH_EVIDENCE, index=False, encoding="utf-8-sig")

    priority = chain.sort_values(["CFO排序评分", "证据等级"], ascending=[False, False]).head(TOP_N)
    priority.to_csv(OUTPUT_PRIORITY, index=False, encoding="utf-8-sig")

    write_summary(chain, positive, negative, positive_with_evidence, negative_with_evidence, priority)


def format_pct(value: float) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:.2%}"


def write_summary(
    chain: pd.DataFrame,
    positive: pd.DataFrame,
    negative: pd.DataFrame,
    positive_with_evidence: pd.DataFrame,
    negative_with_evidence: pd.DataFrame,
    priority: pd.DataFrame,
) -> None:
    evidence_counts = chain["证据等级标签"].value_counts()
    total = len(chain)
    with_evidence = int((chain["是否有证据"] == "是").sum())
    subject = int((chain["公司"] == "移为通信").sum())
    positive_top = positive.head(1).to_dict(orient="records")
    negative_top = negative.head(1).to_dict(orient="records")
    positive_evidence_top = positive_with_evidence.head(1).to_dict(orient="records")
    negative_evidence_top = negative_with_evidence.head(1).to_dict(orient="records")

    def top_line(rows: list[dict[str, object]]) -> str:
        if not rows:
            return "无"
        row = rows[0]
        return (
            f"{row.get('事件日期', '')} {row.get('公司', '')}《{row.get('代表事件标题', '')}》"
            f"，20日客观市值变化 {row.get('20日客观市值变化_亿元', '')} 亿元，"
            f"证据={row.get('证据等级标签', '')}"
        )

    lines = [
        "# CFO 事件-市值变化-证据链主表摘要",
        "",
        f"- 主表事件组数：{total}",
        f"- 移为通信自身事件组：{subject}",
        f"- 有 RAG/结构化证据事件组：{with_evidence}，覆盖率 {format_pct(with_evidence / total if total else math.nan)}",
        "- 证据等级分布：" + "；".join(f"{label}={count}" for label, count in evidence_counts.items()),
        f"- 正向 Top1：{top_line(positive_top)}",
        f"- 负向 Top1：{top_line(negative_top)}",
        f"- 有证据正向 Top1：{top_line(positive_evidence_top)}",
        f"- 有证据负向 Top1：{top_line(negative_evidence_top)}",
        "",
        "## 输出文件",
        "",
        f"- `{OUTPUT_MAIN.relative_to(PROJECT_DIR)}`：全量中文主表，CAR 放在辅助列。",
        f"- `{OUTPUT_POSITIVE.relative_to(PROJECT_DIR)}`：20日客观市值变化正向 Top{len(positive)}。",
        f"- `{OUTPUT_NEGATIVE.relative_to(PROJECT_DIR)}`：20日客观市值变化负向 Top{len(negative)}。",
        f"- `{OUTPUT_POSITIVE_WITH_EVIDENCE.relative_to(PROJECT_DIR)}`：有证据的 20日客观市值变化正向 Top{len(positive_with_evidence)}。",
        f"- `{OUTPUT_NEGATIVE_WITH_EVIDENCE.relative_to(PROJECT_DIR)}`：有证据的 20日客观市值变化负向 Top{len(negative_with_evidence)}。",
        f"- `{OUTPUT_PRIORITY.relative_to(PROJECT_DIR)}`：按客观变化绝对值、事件优先级和证据等级综合排序 Top{len(priority)}。",
        "",
        "## 口径",
        "",
        "- 客观市值变化使用事件窗口后的总市值变化，单位为亿元。",
        "- 相对竞品变化 = 事件公司市值收益率 - 同期竞品平均市值收益率，并按事件前市值换算为亿元。",
        "- CAR 和异常市值影响只作为辅助列，不作为主排序口径。",
        "- 证据等级保留强证据、辅助证据、弱证据、无证据；弱证据不应直接写入结论。",
    ]
    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    chain = build_chain()
    write_outputs(chain)
    print(f"wrote {OUTPUT_MAIN}")
    print(f"rows={len(chain)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

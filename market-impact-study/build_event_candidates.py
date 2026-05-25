"""Build a unified event candidate table from collected public datasets."""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

RAW_DIR = Path("market-impact-study/data/raw")
DOC_MANIFEST = Path("market-impact-study/data/documents/eastmoney_notice_pdf_manifest.csv")
OUTPUT_DIR = Path("market-impact-study/data/processed")

COMPANY_CODE_MAP = {
    "300590": ("移为通信", "300590.SZ"),
    "603236": ("移远通信", "603236.SH"),
    "300098": ("高新兴", "300098.SZ"),
    "300638": ("广和通", "300638.SZ"),
    "002313": ("日海智能", "002313.SZ"),
    "002970": ("锐明技术", "002970.SZ"),
    "688159": ("有方科技", "688159.SH"),
    "002881": ("美格智能", "002881.SZ"),
    "301608": ("博实结", "301608.SZ"),
}

KEYWORD_RULES = {
    "风险事件": [
        "问询函",
        "关注函",
        "监管函",
        "警示函",
        "风险提示",
        "诉讼",
        "仲裁",
        "处罚",
        "违规",
        "立案",
        "调查",
        "减值",
        "商誉",
        "存货",
        "应收",
        "退市",
        "特别处理",
    ],
    "资本动作": [
        "回购",
        "分红",
        "权益分派",
        "股权激励",
        "限制性股票",
        "员工持股",
        "定增",
        "非公开发行",
        "增发",
        "可转债",
        "并购",
        "收购",
        "重组",
        "减持",
        "增持",
        "解禁",
        "质押",
    ],
    "业绩信号": [
        "业绩预告",
        "业绩快报",
        "年度报告",
        "半年度报告",
        "季度报告",
        "一季度报告",
        "三季度报告",
        "预增",
        "预减",
        "扭亏",
        "亏损",
        "净利润",
        "营业收入",
    ],
    "管理层/投关信号": [
        "投资者关系",
        "调研",
        "业绩说明会",
        "路演",
        "机构调研",
        "现场参观",
        "电话会议",
        "媒体采访",
        "董秘",
        "董事长",
        "总经理",
        "财务总监",
    ],
    "产品/技术创新": [
        "新产品",
        "产品",
        "研发",
        "技术",
        "AI",
        "人工智能",
        "卫星通信",
        "车联网",
        "智能网联",
        "AIoT",
        "物联网",
        "两轮车",
        "视频车联网",
        "工业路由器",
        "动物溯源",
        "认证",
        "专利",
    ],
    "客户/订单": ["客户", "订单", "中标", "合同", "战略合作", "合作协议", "框架协议", "供应商", "主机厂", "海外客户"],
    "政策/行业": ["政策", "新国标", "关税", "出口", "地缘", "行业", "补贴", "监管", "车路云"],
}

SOURCE_WEIGHTS = {
    "announcement": 4,
    "announcement_tushare": 3,
    "forecast": 5,
    "express": 5,
    "repurchase": 5,
    "research_report": 3,
    "news": 2,
    "institution_survey": 4,
    "irm_qa": 3,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def normalize_date(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    compact_match = re.match(r"^(\d{4})(\d{2})(\d{2})$", value[:8])
    if compact_match:
        year, month, day = compact_match.groups()
        return f"{year}-{month}-{day}"
    match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return ""


def clean_title(title: str, company: str = "", symbol: str = "") -> str:
    title = str(title or "").strip()
    for prefix in [f"{company}:", f"{symbol}{company}", f"{symbol}", f"{company}：", f"{company}:"]:
        if prefix and title.startswith(prefix):
            title = title[len(prefix) :].strip()
    return title


def classify(text: str) -> tuple[str, str, int]:
    matched: list[str] = []
    score = 0
    for category, keywords in KEYWORD_RULES.items():
        hits = [keyword for keyword in keywords if keyword.lower() in text.lower()]
        if hits:
            matched.append(category)
            score += min(len(hits), 5)
    primary = matched[0] if matched else "其他"
    return primary, "|".join(matched), score


def event_id(row: dict[str, Any]) -> str:
    key = "|".join(
        [
            str(row.get("symbol", "")),
            str(row.get("event_date", "")),
            str(row.get("source_type", "")),
            str(row.get("title", "")),
            str(row.get("source_url", "")),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def load_pdf_manifest() -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    for row in read_csv(DOC_MANIFEST):
        source_url = row.get("source_url", "")
        code = row.get("announcement_code", "")
        if source_url:
            mapping[source_url] = row
        if code:
            mapping[code] = row
    return mapping


def make_row(
    *,
    company: str,
    ts_code: str,
    symbol: str,
    event_date: str,
    source_type: str,
    title: str,
    summary: str = "",
    source_url: str = "",
    raw_category: str = "",
    extra: dict[str, Any] | None = None,
    pdf_mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    title = clean_title(title, company, symbol)
    event_date = normalize_date(event_date)
    text = f"{title} {summary} {raw_category}"
    primary, categories, keyword_score = classify(text)
    pdf_row: dict[str, str] = {}
    if pdf_mapping:
        code_match = re.search(r"(AN\d+)", source_url)
        if source_url in pdf_mapping:
            pdf_row = pdf_mapping[source_url]
        elif code_match and code_match.group(1) in pdf_mapping:
            pdf_row = pdf_mapping[code_match.group(1)]
    row: dict[str, Any] = {
        "event_id": "",
        "company": company,
        "ts_code": ts_code,
        "symbol": symbol,
        "event_date": event_date,
        "source_type": source_type,
        "title": title,
        "summary": summary,
        "source_url": source_url,
        "raw_category": raw_category,
        "primary_category": primary,
        "category_tags": categories,
        "keyword_score": keyword_score,
        "source_weight": SOURCE_WEIGHTS.get(source_type, 1),
        "signal_strength": 1,
        "strength_reason": "",
        "is_subject_company": "1" if symbol == "300590" else "0",
        "is_peer_event": "0" if symbol == "300590" else "1",
        "pdf_url": pdf_row.get("pdf_url", ""),
        "local_pdf_path": pdf_row.get("local_path", ""),
        "has_pdf": "1" if pdf_row.get("local_path") else "0",
    }
    if extra:
        row.update(extra)
    row["event_id"] = event_id(row)
    return row


def add_announcement_rows(rows: list[dict[str, Any]], pdf_mapping: dict[str, dict[str, str]]) -> None:
    for path in sorted((RAW_DIR / "akshare/eastmoney_individual_notice").glob("*.csv")):
        if path.name == "all_companies.csv":
            continue
        for item in read_csv(path):
            symbol = str(item.get("LOCAL_SYMBOL") or item.get("代码") or "").zfill(6)
            company, ts_code = COMPANY_CODE_MAP.get(symbol, (item.get("LOCAL_COMPANY_NAME", ""), ""))
            rows.append(
                make_row(
                    company=company,
                    ts_code=ts_code,
                    symbol=symbol,
                    event_date=item.get("公告日期", ""),
                    source_type="announcement",
                    title=item.get("公告标题", ""),
                    source_url=item.get("网址", ""),
                    raw_category=item.get("公告类型", ""),
                    pdf_mapping=pdf_mapping,
                )
            )


def add_research_rows(rows: list[dict[str, Any]]) -> None:
    for path in sorted((RAW_DIR / "akshare/eastmoney_research_report").glob("*.csv")):
        if path.name == "all_companies.csv":
            continue
        for item in read_csv(path):
            symbol = str(item.get("LOCAL_SYMBOL") or item.get("股票代码") or "").zfill(6)
            company, ts_code = COMPANY_CODE_MAP.get(symbol, (item.get("LOCAL_COMPANY_NAME", ""), ""))
            summary = f"机构={item.get('机构', '')}; 评级={item.get('东财评级', '')}; 行业={item.get('行业', '')}"
            rows.append(
                make_row(
                    company=company,
                    ts_code=ts_code,
                    symbol=symbol,
                    event_date=item.get("日期", ""),
                    source_type="research_report",
                    title=item.get("报告名称", ""),
                    summary=summary,
                    source_url=item.get("报告PDF链接", ""),
                    raw_category="研报",
                    extra={"rating": item.get("东财评级", ""), "institution": item.get("机构", "")},
                )
            )


def add_news_rows(rows: list[dict[str, Any]]) -> None:
    for path in sorted((RAW_DIR / "akshare/eastmoney_stock_news").glob("*.csv")):
        if path.name == "all_companies.csv":
            continue
        for item in read_csv(path):
            symbol = str(item.get("LOCAL_SYMBOL") or "").zfill(6)
            company, ts_code = COMPANY_CODE_MAP.get(symbol, (item.get("LOCAL_COMPANY_NAME", ""), ""))
            rows.append(
                make_row(
                    company=company,
                    ts_code=ts_code,
                    symbol=symbol,
                    event_date=item.get("发布时间", ""),
                    source_type="news",
                    title=item.get("新闻标题", ""),
                    summary=item.get("新闻内容", ""),
                    source_url=item.get("新闻链接", ""),
                    raw_category=item.get("文章来源", ""),
                )
            )


def add_ir_rows(rows: list[dict[str, Any]]) -> None:
    source_path = RAW_DIR / "eastmoney_ir/all_companies_ir.csv"
    source_rows = read_csv(source_path)
    if not source_rows:
        for path in sorted((RAW_DIR / "eastmoney_ir").glob("*.csv")):
            if path.name.startswith("_") or path.name == "all_companies_ir.csv":
                continue
            source_rows.extend(read_csv(path))

    grouped: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = {}
    for item in source_rows:
        symbol = str(item.get("SECURITY_CODE") or "").zfill(6)
        event_date = normalize_date(item.get("NOTICE_DATE", "") or item.get("RECEIVE_START_DATE", ""))
        key = (
            symbol,
            event_date,
            item.get("RECEIVE_WAY_EXPLAIN", ""),
            item.get("RECEIVE_TIME_EXPLAIN", ""),
            item.get("RECEPTIONIST", ""),
        )
        grouped.setdefault(key, []).append(item)

    for (symbol, event_date, receive_way, receive_time, receptionist), items in grouped.items():
        first = items[0]
        company, ts_code = COMPANY_CODE_MAP.get(
            symbol, (first.get("LOCAL_COMPANY_NAME", ""), first.get("SECUCODE", ""))
        )
        title = f"{first.get('SECURITY_NAME_ABBR', company)} {receive_way} {receive_time}".strip()
        objects = sorted({item.get("RECEIVE_OBJECT", "") for item in items if item.get("RECEIVE_OBJECT", "")})
        places = sorted({item.get("RECEIVE_PLACE", "") for item in items if item.get("RECEIVE_PLACE", "")})
        institution_count = max(len(objects), len(items))
        summary = (
            f"对象={';'.join(objects[:8])}; 接待={receptionist}; "
            f"机构明细数={institution_count}; 地点={';'.join(places[:3])}"
        )
        rows.append(
            make_row(
                company=company,
                ts_code=ts_code,
                symbol=symbol,
                event_date=event_date,
                source_type="institution_survey",
                title=title,
                summary=summary,
                source_url="",
                raw_category=receive_way,
                extra={
                    "institution_count": institution_count,
                    "receptionist": receptionist,
                    "signal_strength": min(institution_count, 100),
                    "strength_reason": f"机构调研明细数={institution_count}",
                },
            )
        )


def add_irm_rows(rows: list[dict[str, Any]]) -> None:
    for path in sorted((RAW_DIR / "akshare/cninfo_irm_questions").glob("*.csv")):
        if path.name == "all_companies.csv":
            continue
        for item in read_csv(path):
            symbol = str(item.get("LOCAL_SYMBOL") or item.get("股票代码") or "").zfill(6)
            company, ts_code = COMPANY_CODE_MAP.get(symbol, (item.get("LOCAL_COMPANY_NAME", ""), ""))
            question = item.get("问题", "")
            answer = item.get("回答内容", "")
            rows.append(
                make_row(
                    company=company,
                    ts_code=ts_code,
                    symbol=symbol,
                    event_date=item.get("更新时间", "") or item.get("提问时间", ""),
                    source_type="irm_qa",
                    title=question[:120],
                    summary=answer,
                    source_url="",
                    raw_category="互动易问答",
                )
            )


def add_tushare_event_rows(rows: list[dict[str, Any]]) -> None:
    for dataset, source_type, title_builder in [
        ("anns_d", "announcement_tushare", lambda item: item.get("title", "")),
        ("forecast", "forecast", lambda item: f"{item.get('type', '')} {item.get('summary', '')}".strip()),
        (
            "express",
            "express",
            lambda item: f"业绩快报 营收={item.get('revenue', '')} 净利润={item.get('n_income', '')}".strip(),
        ),
        ("repurchase", "repurchase", lambda item: f"回购 {item.get('proc', '')} 金额={item.get('amount', '')}".strip()),
        (
            "dividend",
            "announcement",
            lambda item: f"分红送转 cash_div={item.get('cash_div', '')} proc={item.get('div_proc', '')}".strip(),
        ),
    ]:
        for path in sorted((RAW_DIR / f"tushare/{dataset}").glob("*.csv")):
            for item in read_csv(path):
                ts_code = item.get("ts_code", "")
                if not item.get("ann_date", ""):
                    continue
                symbol = ts_code.split(".")[0]
                company, mapped_ts_code = COMPANY_CODE_MAP.get(symbol, ("", ts_code))
                rows.append(
                    make_row(
                        company=company,
                        ts_code=mapped_ts_code,
                        symbol=symbol,
                        event_date=item.get("ann_date", ""),
                        source_type=source_type,
                        title=title_builder(item),
                        summary=item.get("change_reason", ""),
                        source_url="",
                        raw_category=dataset,
                    )
                )


def main() -> int:
    pdf_mapping = load_pdf_manifest()
    rows: list[dict[str, Any]] = []
    add_announcement_rows(rows, pdf_mapping)
    add_research_rows(rows)
    add_news_rows(rows)
    add_ir_rows(rows)
    add_irm_rows(rows)
    add_tushare_event_rows(rows)

    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = "|".join([str(row["symbol"]), str(row["event_date"]), str(row["source_type"]), str(row["title"])])
        existing = dedup.get(key)
        if not existing or int(row.get("has_pdf", 0)) > int(existing.get("has_pdf", 0)):
            dedup[key] = row
    output_rows = sorted(
        dedup.values(),
        key=lambda item: (item.get("event_date", ""), item.get("symbol", ""), item.get("source_type", "")),
        reverse=True,
    )

    fieldnames = [
        "event_id",
        "company",
        "ts_code",
        "symbol",
        "event_date",
        "source_type",
        "title",
        "summary",
        "source_url",
        "raw_category",
        "primary_category",
        "category_tags",
        "keyword_score",
        "source_weight",
        "signal_strength",
        "strength_reason",
        "is_subject_company",
        "is_peer_event",
        "pdf_url",
        "local_pdf_path",
        "has_pdf",
        "rating",
        "institution",
        "institution_count",
        "receptionist",
    ]
    write_csv(OUTPUT_DIR / "event_candidates.csv", output_rows, fieldnames)
    sys.stdout.write(f"rows={len(output_rows)} path={OUTPUT_DIR / 'event_candidates.csv'}\n")
    by_source: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for row in output_rows:
        by_source[row["source_type"]] = by_source.get(row["source_type"], 0) + 1
        by_category[row["primary_category"]] = by_category.get(row["primary_category"], 0) + 1
    sys.stdout.write(f"by_source {by_source}\n")
    sys.stdout.write(f"by_category {by_category}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""补全市场影响研究的用户检索 query。"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

COMPANY_ALIASES = {
    "移为通信": ["移为通信", "移为", "300590"],
    "移远通信": ["移远通信", "移远", "603236"],
    "高新兴": ["高新兴", "300098"],
    "广和通": ["广和通", "300638"],
    "日海智能": ["日海智能", "日海", "002313"],
    "锐明技术": ["锐明技术", "锐明", "002970"],
    "有方科技": ["有方科技", "有方", "688159"],
    "美格智能": ["美格智能", "美格", "002881"],
    "博实结": ["博实结", "301608"],
}

INTENT_TERMS = {
    "回购": ["回购", "股份回购", "集中竞价", "回购方案", "回购进展"],
    "分红": ["分红", "权益分派", "利润分配", "现金分红", "除权除息"],
    "股权激励": ["股权激励", "限制性股票", "股票期权", "员工持股", "激励计划"],
    "定增": ["定增", "非公开发行", "向特定对象发行", "募集资金", "再融资"],
    "业绩": ["业绩", "业绩预告", "业绩快报", "净利润", "营业收入", "毛利率"],
    "订单": ["订单", "客户", "中标", "合同", "战略合作", "供应商"],
    "产品": ["产品", "新产品", "研发", "技术", "车联网", "物联网", "卫星通信", "AI"],
    "调研": ["调研", "机构调研", "投资者关系", "业绩说明会", "路演"],
    "风险": ["风险", "问询函", "关注函", "诉讼", "仲裁", "处罚", "减值", "异常波动"],
}

METRIC_TERMS = ["市值变化", "市场反应", "CAR", "异常收益", "成交额", "换手率", "机构关注"]


def detect_companies(query: str) -> list[str]:
    companies: list[str] = []
    for company, aliases in COMPANY_ALIASES.items():
        if any(alias and alias in query for alias in aliases):
            companies.append(company)
    return companies


def detect_intents(query: str) -> list[str]:
    intents: list[str] = []
    for intent, terms in INTENT_TERMS.items():
        if any(term and term in query for term in terms):
            intents.append(intent)
    return intents


def detect_years(query: str) -> list[str]:
    return sorted(set(re.findall(r"20\d{2}", query)))


def unique_extend(values: list[str], additions: list[str]) -> None:
    for value in additions:
        if value and value not in values:
            values.append(value)


def enrich_query(query: str) -> dict[str, Any]:
    query = " ".join(query.split())
    companies = detect_companies(query)
    intents = detect_intents(query)
    years = detect_years(query)

    terms = [query]
    for company in companies:
        unique_extend(terms, COMPANY_ALIASES[company])
    for intent in intents:
        unique_extend(terms, INTENT_TERMS[intent])
    if re.search(r"市值|股价|市场|反应|影响|涨|跌|买账", query):
        unique_extend(terms, METRIC_TERMS)
    unique_extend(terms, years)

    filters: dict[str, list[str]] = {}
    if companies:
        filters["company"] = companies
        filters["symbol"] = [COMPANY_ALIASES[company][-1] for company in companies]
    if years:
        filters["year"] = years

    return {
        "raw_query": query,
        "expanded_query": " ".join(terms),
        "companies": companies,
        "intents": intents,
        "years": years,
        "filters": filters,
        "terms": terms,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(enrich_query(args.query), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Probe public/free data sources that can reduce manual event collection.

Only standard library modules are used. The goal is not full ingestion, but a
reproducible availability snapshot for sources that may complement Tushare.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TODAY = date.today().strftime("%Y-%m-%d")
OUTPUT_DIR = Path("market-impact-study/data/public_source_probe")

COMPANIES = [
    {"name": "移为通信", "ts_code": "300590.SZ", "symbol": "300590", "market_num": "0"},
    {"name": "移远通信", "ts_code": "603236.SH", "symbol": "603236", "market_num": "1"},
    {"name": "高新兴", "ts_code": "300098.SZ", "symbol": "300098", "market_num": "0"},
    {"name": "广和通", "ts_code": "300638.SZ", "symbol": "300638", "market_num": "0"},
    {"name": "日海智能", "ts_code": "002313.SZ", "symbol": "002313", "market_num": "0"},
    {"name": "锐明技术", "ts_code": "002970.SZ", "symbol": "002970", "market_num": "0"},
    {"name": "有方科技", "ts_code": "688159.SH", "symbol": "688159", "market_num": "1"},
    {"name": "美格智能", "ts_code": "002881.SZ", "symbol": "002881", "market_num": "0"},
    {"name": "博实结", "ts_code": "301608.SZ", "symbol": "301608", "market_num": "0"},
]


@dataclass
class SourceResult:
    source: str
    dataset: str
    scope: str
    status: str
    row_count: int = 0
    url: str = ""
    sample: Any = None
    message: str = ""


def http_request(
    url: str,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, str]:
    default_headers = {
        "User-Agent": "Mozilla/5.0 market-impact-study/0.1",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.eastmoney.com/",
    }
    if headers:
        default_headers.update(headers)
    request = Request(url, data=data, headers=default_headers)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, response.read().decode(charset, errors="replace")


def http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[int, str]:
    return http_request(url, headers=headers, timeout=timeout)


def json_from_possible_callback(text: str) -> Any:
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    match = re.search(r"\((.*)\)\s*;?\s*$", text, flags=re.S)
    if match:
        return json.loads(match.group(1))
    raise ValueError("Response is not JSON or JSONP")


def safe_probe(source: str, dataset: str, scope: str, url: str, parser) -> SourceResult:
    try:
        _, text = http_get(url)
        parsed = parser(text)
        row_count, sample = parsed
        return SourceResult(source, dataset, scope, "ok" if row_count else "empty", row_count, url, sample)
    except HTTPError as exc:
        return SourceResult(source, dataset, scope, "error", url=url, message=f"HTTPError {exc.code}: {exc.reason}")
    except URLError as exc:
        return SourceResult(source, dataset, scope, "error", url=url, message=f"URLError: {exc.reason}")
    except Exception as exc:  # noqa: BLE001 - probe should continue across sources
        return SourceResult(source, dataset, scope, "error", url=url, message=f"{type(exc).__name__}: {exc}")


def safe_post_probe(
    source: str,
    dataset: str,
    scope: str,
    url: str,
    form: dict[str, str],
    parser,
    headers: dict[str, str] | None = None,
) -> SourceResult:
    try:
        post_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        }
        if headers:
            post_headers.update(headers)
        _, text = http_request(url, headers=post_headers, data=urlencode(form).encode("utf-8"))
        parsed = parser(text)
        row_count, sample = parsed
        return SourceResult(source, dataset, scope, "ok" if row_count else "empty", row_count, url, sample)
    except HTTPError as exc:
        return SourceResult(source, dataset, scope, "error", url=url, message=f"HTTPError {exc.code}: {exc.reason}")
    except URLError as exc:
        return SourceResult(source, dataset, scope, "error", url=url, message=f"URLError: {exc.reason}")
    except Exception as exc:  # noqa: BLE001
        return SourceResult(source, dataset, scope, "error", url=url, message=f"{type(exc).__name__}: {exc}")


def parse_eastmoney_list(text: str) -> tuple[int, list[dict[str, Any]]]:
    data = json_from_possible_callback(text)
    rows = ((data or {}).get("result") or {}).get("data") or []
    return len(rows), rows[:3]


def parse_eastmoney_quote(text: str) -> tuple[int, list[dict[str, Any]]]:
    data = json_from_possible_callback(text)
    rows = ((data or {}).get("data") or {}).get("diff") or []
    return len(rows), rows[:3]


def parse_cninfo(text: str) -> tuple[int, list[dict[str, Any]]]:
    data = json.loads(text)
    rows = data.get("announcements") or []
    return len(rows), rows[:3]


def parse_json_rows(rows_key: str):
    def parser(text: str) -> tuple[int, Any]:
        data = json_from_possible_callback(text)
        cursor: Any = data
        for key in rows_key.split("."):
            cursor = (cursor or {}).get(key)
        rows = cursor or []
        return len(rows), rows[:3] if isinstance(rows, list) else rows

    return parser


def eastmoney_notice_url(symbol: str) -> str:
    params = {
        "cb": "",
        "sr": "-1",
        "page_size": "5",
        "page_index": "1",
        "ann_type": "A",
        "client_source": "web",
        "stock_list": f"{symbol},",
    }
    return "https://np-anotice-stock.eastmoney.com/api/security/ann?" + urlencode(params)


def eastmoney_research_url(symbol: str) -> str:
    params = {
        "reportName": "RPT_RESEARCHREPORT_DET",
        "columns": "ALL",
        "pageNumber": "1",
        "pageSize": "5",
        "sortTypes": "-1",
        "sortColumns": "REPORT_DATE",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(SECURITY_CODE="{symbol}")',
    }
    return "https://datacenter-web.eastmoney.com/api/data/v1/get?" + urlencode(params)


def eastmoney_jgdy_url(symbol: str) -> str:
    params = {
        "reportName": "RPT_ORG_SURVEYNEW",
        "columns": "ALL",
        "pageNumber": "1",
        "pageSize": "5",
        "sortTypes": "-1",
        "sortColumns": "NOTICE_DATE",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(SECURITY_CODE="{symbol}")',
    }
    return "https://datacenter-web.eastmoney.com/api/data/v1/get?" + urlencode(params)


def eastmoney_news_url(symbol: str) -> str:
    params = {
        "appId": "1",
        "pageIndex": "1",
        "pageSize": "5",
        "stock": symbol,
    }
    return "https://search-api-web.eastmoney.com/search/jsonp?" + urlencode(params)


def eastmoney_quote_url() -> str:
    fields = "f12,f14,f2,f3,f5,f6,f20,f21,f8,f9,f10"
    params = {
        "pn": "1",
        "pz": "20",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": fields,
    }
    return "https://push2.eastmoney.com/api/qt/clist/get?" + urlencode(params)


def cninfo_notice_url(symbol: str, org_id: str = "") -> str:
    # cninfo web endpoint accepts POST in normal usage; this GET probe often
    # still returns a structured error or empty result, which is enough to
    # decide whether a dedicated crawler is needed.
    params = {
        "stock": symbol,
        "searchkey": "",
        "plate": "sz" if not symbol.startswith(("6", "9")) else "sh",
        "category": "",
        "trade": "",
        "column": "szse" if not symbol.startswith(("6", "9")) else "sse",
        "columnTitle": "历史公告查询",
        "pageNum": "1",
        "pageSize": "5",
        "tabName": "fulltext",
        "sortName": "",
        "sortType": "",
        "limit": "",
        "seDate": "",
        "orgId": org_id,
    }
    return "https://www.cninfo.com.cn/new/hisAnnouncement/query?" + urlencode(params)


def cninfo_notice_form(symbol: str) -> dict[str, str]:
    return {
        "stock": symbol,
        "searchkey": "",
        "plate": "sz" if not symbol.startswith(("6", "9")) else "sh",
        "category": "",
        "trade": "",
        "column": "szse" if not symbol.startswith(("6", "9")) else "sse",
        "pageNum": "1",
        "pageSize": "5",
        "tabName": "fulltext",
        "seDate": "",
    }


def policy_search_url(keyword: str) -> str:
    return "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?" + urlencode({"t": "zhengcelibrary", "q": keyword})


def flatten(result: SourceResult) -> dict[str, Any]:
    return {
        "source": result.source,
        "dataset": result.dataset,
        "scope": result.scope,
        "status": result.status,
        "row_count": result.row_count,
        "url": result.url,
        "message": result.message,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[SourceResult] = []

    results.append(
        safe_probe(
            "东方财富",
            "A股实时行情列表",
            "all_a",
            eastmoney_quote_url(),
            parse_eastmoney_quote,
        )
    )

    for company in COMPANIES:
        scope = f"{company['name']}:{company['symbol']}"
        symbol = company["symbol"]
        results.extend(
            [
                safe_probe("东方财富", "个股公告", scope, eastmoney_notice_url(symbol), parse_eastmoney_list),
                safe_probe("东方财富", "个股研报", scope, eastmoney_research_url(symbol), parse_eastmoney_list),
                safe_probe("东方财富", "机构调研", scope, eastmoney_jgdy_url(symbol), parse_eastmoney_list),
                safe_probe("东方财富", "个股新闻搜索", scope, eastmoney_news_url(symbol), parse_json_rows("data")),
                safe_probe("巨潮资讯", "历史公告查询_GET", scope, cninfo_notice_url(symbol), parse_cninfo),
                safe_post_probe(
                    "巨潮资讯",
                    "历史公告查询_POST",
                    scope,
                    "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                    cninfo_notice_form(symbol),
                    parse_cninfo,
                ),
            ]
        )
        time.sleep(0.25)

    for keyword in ["车联网", "物联网", "智能网联汽车", "两轮车新国标", "移动物联网"]:
        results.append(
            safe_probe(
                "中国政府网",
                "政策搜索页面",
                keyword,
                policy_search_url(keyword),
                lambda text, search_keyword=keyword: (1 if search_keyword in text else 0, text[:300]),
            )
        )

    payload = {
        "generated_at": TODAY,
        "results": [flatten(result) for result in results],
        "samples": [
            {
                "source": result.source,
                "dataset": result.dataset,
                "scope": result.scope,
                "status": result.status,
                "sample": result.sample,
                "message": result.message,
                "url": result.url,
            }
            for result in results
            if result.status == "ok"
        ],
    }
    (OUTPUT_DIR / "public_source_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        OUTPUT_DIR / "public_source_matrix.csv",
        [flatten(result) for result in results],
        ["source", "dataset", "scope", "status", "row_count", "url", "message"],
    )

    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    print(json.dumps(status_counts, ensure_ascii=False))
    print(f"output_dir={OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

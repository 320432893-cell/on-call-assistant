"""Collect Eastmoney organization survey / IR activity records."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUTPUT_DIR = Path("market-impact-study/data/raw/eastmoney_ir")

COMPANIES = [
    {"name": "移为通信", "symbol": "300590"},
    {"name": "移远通信", "symbol": "603236"},
    {"name": "高新兴", "symbol": "300098"},
    {"name": "广和通", "symbol": "300638"},
    {"name": "日海智能", "symbol": "002313"},
    {"name": "锐明技术", "symbol": "002970"},
    {"name": "有方科技", "symbol": "688159"},
    {"name": "美格智能", "symbol": "002881"},
    {"name": "博实结", "symbol": "301608"},
]


def request_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 market-impact-study/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://data.eastmoney.com/",
        },
    )
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def build_url(symbol: str, page: int, page_size: int = 500) -> str:
    params = {
        "reportName": "RPT_ORG_SURVEYNEW",
        "columns": "ALL",
        "pageNumber": str(page),
        "pageSize": str(page_size),
        "sortTypes": "-1",
        "sortColumns": "NOTICE_DATE",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(SECURITY_CODE="{symbol}")',
    }
    return "https://datacenter-web.eastmoney.com/api/data/v1/get?" + urlencode(params)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    if not fieldnames:
        fieldnames = ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def collect_company(symbol: str) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = request_json(build_url(symbol, page))
        result = data.get("result") or {}
        page_rows = result.get("data") or []
        rows.extend(page_rows)
        pages = int(result.get("pages") or 1)
        if page >= pages or not page_rows:
            break
        page += 1
        time.sleep(0.2)
    return rows, ""


def main() -> int:
    statuses = []
    all_rows: list[dict[str, Any]] = []
    for company in COMPANIES:
        path = OUTPUT_DIR / f"{company['symbol']}.csv"
        try:
            rows, message = collect_company(company["symbol"])
            for row in rows:
                row["LOCAL_COMPANY_NAME"] = company["name"]
            write_csv(path, rows)
            all_rows.extend(rows)
            statuses.append(
                {
                    "company": company["name"],
                    "symbol": company["symbol"],
                    "status": "ok" if rows else "empty",
                    "rows": len(rows),
                    "path": str(path),
                    "message": message,
                }
            )
        except HTTPError as exc:
            statuses.append(
                {
                    "company": company["name"],
                    "symbol": company["symbol"],
                    "status": "error",
                    "rows": 0,
                    "path": str(path),
                    "message": f"HTTPError {exc.code}: {exc.reason}",
                }
            )
        except URLError as exc:
            statuses.append(
                {
                    "company": company["name"],
                    "symbol": company["symbol"],
                    "status": "error",
                    "rows": 0,
                    "path": str(path),
                    "message": f"URLError: {exc.reason}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            statuses.append(
                {
                    "company": company["name"],
                    "symbol": company["symbol"],
                    "status": "error",
                    "rows": 0,
                    "path": str(path),
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
        time.sleep(0.2)

    write_csv(OUTPUT_DIR / "all_companies_ir.csv", all_rows)
    write_csv(OUTPUT_DIR / "_collection_summary.csv", statuses)
    print(
        f"ok={sum(s['status'] == 'ok' for s in statuses)} empty={sum(s['status'] == 'empty' for s in statuses)} error={sum(s['status'] == 'error' for s in statuses)} rows={len(all_rows)}"
    )
    print(f"summary={OUTPUT_DIR / '_collection_summary.csv'}")
    return 0 if not any(s["status"] == "error" for s in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())

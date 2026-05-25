"""Create a lightweight quality snapshot for probed Tushare interfaces."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

BASE_DIR = Path("market-impact-study/data/tushare_probe")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    matrix = load_csv(BASE_DIR / "probe_matrix.csv")
    companies = load_csv(BASE_DIR / "company_resolution.csv")
    summary = json.loads((BASE_DIR / "probe_summary.json").read_text(encoding="utf-8"))

    status_counts = Counter(row["status"] for row in matrix)
    empty_or_error = [
        {
            "api_name": row["api_name"],
            "scope": row["scope"],
            "status": row["status"],
            "message": row["message"],
        }
        for row in matrix
        if row["status"] != "ok"
    ]

    latest_by_api = defaultdict(list)
    for row in matrix:
        if row["status"] == "ok" and row["max_date"]:
            latest_by_api[row["api_name"]].append(row["max_date"])

    coverage_rows: list[dict[str, object]] = []
    by_scope: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in matrix:
        by_scope[row["scope"]][row["api_name"]] = row

    for company in companies:
        if company.get("resolved") != "yes":
            continue
        scope = f"{company['name']}:{company['ts_code']}"
        daily = by_scope[scope].get("daily", {})
        daily_basic = by_scope[scope].get("daily_basic", {})
        anns = by_scope[scope].get("anns_d", {})
        income = by_scope[scope].get("income", {})
        coverage_rows.append(
            {
                "name": company["name"],
                "ts_code": company["ts_code"],
                "list_date": company["list_date"],
                "daily_rows": daily.get("row_count", ""),
                "daily_start": daily.get("min_date", ""),
                "daily_end": daily.get("max_date", ""),
                "daily_matches_list_date": daily.get("min_date") == company["list_date"],
                "daily_basic_rows": daily_basic.get("row_count", ""),
                "daily_basic_end": daily_basic.get("max_date", ""),
                "income_rows": income.get("row_count", ""),
                "ann_title_rows": anns.get("row_count", ""),
                "ann_title_start": anns.get("min_date", ""),
                "ann_title_end": anns.get("max_date", ""),
            }
        )

    sample_rows = []
    for item in summary.get("samples", []):
        api_name = item.get("api_name")
        if api_name not in {"daily_basic", "income", "fina_indicator", "forecast", "repurchase"}:
            continue
        for row in item.get("sample") or []:
            row = dict(row)
            row["api_name"] = api_name
            row["scope"] = item.get("scope")
            sample_rows.append(row)

    daily_basic_samples = [row for row in sample_rows if row.get("api_name") == "daily_basic"]
    total_mv_values = [float(row["total_mv"]) for row in daily_basic_samples if row.get("total_mv") is not None]
    pe_values = [float(row["pe"]) for row in daily_basic_samples if row.get("pe") is not None]
    pb_values = [float(row["pb"]) for row in daily_basic_samples if row.get("pb") is not None]

    risk_notes = []
    if status_counts.get("error", 0):
        risk_notes.append("存在接口错误，需先处理权限或网络问题。")
    if status_counts.get("empty", 0):
        risk_notes.append("存在空接口，空值多与上市时间短或无对应事项有关，不能直接当作数据缺失。")
    if len(companies) != 9 or any(row.get("resolved") != "yes" for row in companies):
        risk_notes.append("公司代码未完整解析。")
    if total_mv_values and median(total_mv_values) > 10000:
        risk_notes.append("daily_basic.total_mv/circ_mv 为万元口径，财务报表为元口径，市值金额必须统一单位。")
    if any(value < 0 for value in pe_values):
        risk_notes.append("PE 存在负值，说明部分样本亏损；估值对比应保留 PE 缺失/负值处理规则。")
    if any(value <= 0 for value in pb_values):
        risk_notes.append("PB 存在非正值，需要核查净资产异常。")
    if not risk_notes:
        risk_notes.append("未在探测样例中发现明显单位或覆盖异常；后续完整建库仍需做全量字段级校验。")

    report = {
        "status_counts": dict(status_counts),
        "empty_or_error": empty_or_error,
        "latest_by_api": {api: sorted(set(values)) for api, values in latest_by_api.items()},
        "risk_notes": risk_notes,
        "first_version_reliable": [
            "stock_basic",
            "daily",
            "daily_basic",
            "adj_factor",
            "income",
            "balancesheet",
            "cashflow",
            "fina_indicator",
            "forecast",
            "express",
            "dividend",
            "repurchase",
            "pledge_stat",
            "stk_holdernumber",
            "anns_d",
            "index_daily",
        ],
        "manual_supplement_needed": [
            "产品/技术创新事件需要从公告标题、投资者关系记录、年报管理层讨论中人工筛选。",
            "客户/订单事件需要人工判定金额、客户重要性和是否可披露。",
            "竞品创新动作需要人工归类为可学习/不可复制/仅观察。",
            "政策与行业事件不适合全量抓取，第一版只做精选事件。",
        ],
    }
    (BASE_DIR / "quality_snapshot.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        BASE_DIR / "coverage_by_company.csv",
        coverage_rows,
        [
            "name",
            "ts_code",
            "list_date",
            "daily_rows",
            "daily_start",
            "daily_end",
            "daily_matches_list_date",
            "daily_basic_rows",
            "daily_basic_end",
            "income_rows",
            "ann_title_rows",
            "ann_title_start",
            "ann_title_end",
        ],
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

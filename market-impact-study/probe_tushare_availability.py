"""Probe Tushare data availability for the market impact study.

The script intentionally uses only the Python standard library so it can run in
an isolated environment before project dependencies are installed.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://api.tushare.pro"
DEFAULT_START = "19900101"
TODAY = date.today().strftime("%Y%m%d")

COMPANY_NAMES = [
    "移为通信",
    "移远通信",
    "高新兴",
    "广和通",
    "日海智能",
    "锐明技术",
    "有方科技",
    "美格智能",
    "博实结",
]


@dataclass
class ProbeResult:
    api_name: str
    scope: str
    status: str
    row_count: int = 0
    fields: list[str] | None = None
    sample: list[dict[str, Any]] | None = None
    min_trade_date: str | None = None
    max_trade_date: str | None = None
    message: str = ""


def call_tushare(token: str, api_name: str, params: dict[str, Any], fields: str = "") -> dict[str, Any]:
    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields,
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(API_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return {"code": -9001, "msg": f"HTTPError {exc.code}: {exc.reason}"}
    except URLError as exc:
        return {"code": -9002, "msg": f"URLError: {exc.reason}"}
    except TimeoutError:
        return {"code": -9003, "msg": "Timeout"}


def rows_from_response(response: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    data = response.get("data") or {}
    fields = data.get("fields") or []
    items = data.get("items") or []
    rows = [dict(zip(fields, item, strict=False)) for item in items]
    return fields, rows


def probe(
    token: str,
    api_name: str,
    scope: str,
    params: dict[str, Any],
    fields: str,
    sleep_seconds: float = 0.22,
) -> ProbeResult:
    response = call_tushare(token, api_name, params, fields)
    time.sleep(sleep_seconds)
    if response.get("code") != 0:
        return ProbeResult(
            api_name=api_name,
            scope=scope,
            status="error",
            message=str(response.get("msg", "")),
        )
    field_names, rows = rows_from_response(response)
    if not rows:
        return ProbeResult(
            api_name=api_name,
            scope=scope,
            status="empty",
            row_count=0,
            fields=field_names,
        )

    trade_dates = [str(row.get("trade_date") or row.get("ann_date") or row.get("end_date") or "") for row in rows]
    trade_dates = [value for value in trade_dates if value]
    return ProbeResult(
        api_name=api_name,
        scope=scope,
        status="ok",
        row_count=len(rows),
        fields=field_names,
        sample=rows[:3],
        min_trade_date=min(trade_dates) if trade_dates else None,
        max_trade_date=max(trade_dates) if trade_dates else None,
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def flatten_probe(result: ProbeResult) -> dict[str, Any]:
    return {
        "api_name": result.api_name,
        "scope": result.scope,
        "status": result.status,
        "row_count": result.row_count,
        "min_date": result.min_trade_date or "",
        "max_date": result.max_trade_date or "",
        "field_count": len(result.fields or []),
        "fields": ",".join(result.fields or []),
        "message": result.message,
    }


def main() -> int:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        print("TUSHARE_TOKEN is required in the environment.", file=sys.stderr)
        return 2

    output_dir = Path("market-impact-study/data/tushare_probe")
    output_dir.mkdir(parents=True, exist_ok=True)

    probes: list[ProbeResult] = []

    stock_basic_fields = "ts_code,symbol,name,area,industry,market,exchange,list_date"
    stock_basic_result = probe(
        token,
        "stock_basic",
        "all_listed",
        {"exchange": "", "list_status": "L"},
        stock_basic_fields,
    )
    probes.append(stock_basic_result)

    company_rows: list[dict[str, Any]] = []
    if stock_basic_result.status == "ok" and stock_basic_result.sample is not None:
        _, all_stock_rows = rows_from_response(
            call_tushare(
                token,
                "stock_basic",
                {"exchange": "", "list_status": "L"},
                stock_basic_fields,
            )
        )
        name_to_row = {str(row.get("name")): row for row in all_stock_rows}
        for name in COMPANY_NAMES:
            row = name_to_row.get(name, {"name": name})
            row["resolved"] = "yes" if "ts_code" in row else "no"
            company_rows.append(row)
    else:
        company_rows = [{"name": name, "resolved": "no"} for name in COMPANY_NAMES]

    write_csv(
        output_dir / "company_resolution.csv",
        company_rows,
        [
            "name",
            "resolved",
            "ts_code",
            "symbol",
            "area",
            "industry",
            "market",
            "exchange",
            "list_date",
        ],
    )

    resolved = [row for row in company_rows if row.get("resolved") == "yes"]

    common_fields = {
        "daily": "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
        "daily_basic": "ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pb,ps,total_mv,circ_mv",
        "adj_factor": "ts_code,trade_date,adj_factor",
        "income": "ts_code,ann_date,f_ann_date,end_date,report_type,total_revenue,revenue,operate_profit,total_profit,n_income,n_income_attr_p",
        "balancesheet": "ts_code,ann_date,f_ann_date,end_date,total_assets,total_liab,total_hldr_eqy_inc_min_int,total_cur_assets,total_cur_liab",
        "cashflow": "ts_code,ann_date,f_ann_date,end_date,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,c_cash_equ_end_period",
        "fina_indicator": "ts_code,ann_date,end_date,roe,roa,grossprofit_margin,netprofit_margin,rd_exp,rd_exp_to_revenue,ocfps,bps",
        "forecast": "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,summary,change_reason",
        "express": "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps",
        "dividend": "ts_code,ann_date,end_date,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date,div_proc",
        "repurchase": "ts_code,ann_date,end_date,proc,exp_date,vol,amount,high_limit,low_limit",
        "pledge_stat": "ts_code,end_date,pledge_count,unrest_pledge,rest_pledge,total_share,pledge_ratio",
        "stk_holdernumber": "ts_code,ann_date,end_date,holder_num",
        "anns_d": "ts_code,ann_date,title,rec_time",
    }

    for row in resolved:
        ts_code = str(row["ts_code"])
        list_date = str(row.get("list_date") or DEFAULT_START)
        scope = f"{row.get('name')}:{ts_code}"
        probes.extend(
            [
                probe(
                    token,
                    "daily",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["daily"],
                ),
                probe(
                    token,
                    "daily_basic",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["daily_basic"],
                ),
                probe(
                    token,
                    "adj_factor",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["adj_factor"],
                ),
                probe(
                    token,
                    "income",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["income"],
                ),
                probe(
                    token,
                    "balancesheet",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["balancesheet"],
                ),
                probe(
                    token,
                    "cashflow",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["cashflow"],
                ),
                probe(
                    token,
                    "fina_indicator",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["fina_indicator"],
                ),
                probe(
                    token,
                    "forecast",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["forecast"],
                ),
                probe(
                    token,
                    "express",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["express"],
                ),
                probe(token, "dividend", scope, {"ts_code": ts_code}, common_fields["dividend"]),
                probe(
                    token,
                    "repurchase",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["repurchase"],
                ),
                probe(token, "pledge_stat", scope, {"ts_code": ts_code}, common_fields["pledge_stat"]),
                probe(
                    token,
                    "stk_holdernumber",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["stk_holdernumber"],
                ),
                probe(
                    token,
                    "anns_d",
                    scope,
                    {"ts_code": ts_code, "start_date": list_date, "end_date": TODAY},
                    common_fields["anns_d"],
                ),
            ]
        )

    index_fields = "ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount"
    for ts_code in ["399006.SZ", "000300.SH", "000905.SH", "000852.SH"]:
        probes.append(
            probe(
                token,
                "index_daily",
                ts_code,
                {"ts_code": ts_code, "start_date": "20100101", "end_date": TODAY},
                index_fields,
            )
        )

    summary = {
        "generated_at": date.today().isoformat(),
        "company_names": COMPANY_NAMES,
        "resolved_count": len(resolved),
        "unresolved_names": [row["name"] for row in company_rows if row.get("resolved") != "yes"],
        "probe_results": [flatten_probe(result) for result in probes],
        "samples": [
            {
                "api_name": result.api_name,
                "scope": result.scope,
                "sample": result.sample,
                "message": result.message,
            }
            for result in probes
            if result.status in {"ok", "error"} and (result.sample or result.message)
        ],
    }
    (output_dir / "probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        output_dir / "probe_matrix.csv",
        [flatten_probe(result) for result in probes],
        ["api_name", "scope", "status", "row_count", "min_date", "max_date", "field_count", "fields", "message"],
    )

    ok_count = sum(1 for result in probes if result.status == "ok")
    empty_count = sum(1 for result in probes if result.status == "empty")
    error_count = sum(1 for result in probes if result.status == "error")
    print(f"resolved_companies={len(resolved)}/{len(COMPANY_NAMES)}")
    print(f"probe_ok={ok_count} empty={empty_count} error={error_count}")
    print(f"output_dir={output_dir}")
    return 0 if resolved else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Collect Tushare datasets for the market impact study.

Uses Tushare HTTP API directly via the Python standard library. The token must
be provided through TUSHARE_TOKEN and is never written to disk.
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
TODAY = date.today().strftime("%Y%m%d")
OUTPUT_DIR = Path("market-impact-study/data/raw/tushare")

COMPANIES = [
    {"name": "移为通信", "ts_code": "300590.SZ", "list_date": "20170111"},
    {"name": "移远通信", "ts_code": "603236.SH", "list_date": "20190716"},
    {"name": "高新兴", "ts_code": "300098.SZ", "list_date": "20100728"},
    {"name": "广和通", "ts_code": "300638.SZ", "list_date": "20170413"},
    {"name": "日海智能", "ts_code": "002313.SZ", "list_date": "20091203"},
    {"name": "锐明技术", "ts_code": "002970.SZ", "list_date": "20191217"},
    {"name": "有方科技", "ts_code": "688159.SH", "list_date": "20200123"},
    {"name": "美格智能", "ts_code": "002881.SZ", "list_date": "20170622"},
    {"name": "博实结", "ts_code": "301608.SZ", "list_date": "20240801"},
]

INDEXES = [
    {"name": "创业板指", "ts_code": "399006.SZ", "start_date": "20100101"},
    {"name": "沪深300", "ts_code": "000300.SH", "start_date": "20100101"},
    {"name": "中证500", "ts_code": "000905.SH", "start_date": "20100101"},
    {"name": "中证1000", "ts_code": "000852.SH", "start_date": "20100101"},
]

DATASETS = {
    "daily": "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    "daily_basic": "ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pb,ps,total_mv,circ_mv",
    "adj_factor": "ts_code,trade_date,adj_factor",
    "income": "ts_code,ann_date,f_ann_date,end_date,report_type,total_revenue,revenue,operate_profit,total_profit,n_income,n_income_attr_p",
    "balancesheet": "ts_code,ann_date,f_ann_date,end_date,total_assets,total_liab,total_hldr_eqy_inc_min_int,total_cur_assets,total_cur_liab",
    "cashflow": "ts_code,ann_date,f_ann_date,end_date,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,c_cash_equ_end_period",
    "fina_indicator": "ts_code,ann_date,end_date,roe,roa,grossprofit_margin,netprofit_margin,rd_exp,ocfps,bps",
    "forecast": "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,summary,change_reason",
    "express": "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps",
    "dividend": "ts_code,ann_date,end_date,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date,div_proc",
    "repurchase": "ts_code,ann_date,end_date,proc,exp_date,vol,amount,high_limit,low_limit",
    "pledge_stat": "ts_code,end_date,pledge_count,unrest_pledge,rest_pledge,total_share,pledge_ratio",
    "stk_holdernumber": "ts_code,ann_date,end_date,holder_num",
    "anns_d": "ts_code,ann_date,title,rec_time",
}


@dataclass
class CollectStatus:
    dataset: str
    scope: str
    status: str
    rows: int
    path: str
    message: str = ""


def call_tushare(token: str, api_name: str, params: dict[str, Any], fields: str) -> dict[str, Any]:
    payload = {"api_name": api_name, "token": token, "params": params, "fields": fields}
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def response_rows(response: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    data = response.get("data") or {}
    fields = data.get("fields") or []
    rows = [dict(zip(fields, item, strict=False)) for item in data.get("items") or []]
    return fields, rows


def write_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def collect_one(
    token: str,
    dataset: str,
    scope: str,
    params: dict[str, Any],
    fields: str,
    path: Path,
) -> CollectStatus:
    try:
        response = call_tushare(token, dataset, params, fields)
        if response.get("code") != 0:
            return CollectStatus(dataset, scope, "error", 0, str(path), str(response.get("msg", "")))
        field_names, rows = response_rows(response)
        write_rows(path, field_names, rows)
        return CollectStatus(dataset, scope, "ok" if rows else "empty", len(rows), str(path))
    except HTTPError as exc:
        return CollectStatus(dataset, scope, "error", 0, str(path), f"HTTPError {exc.code}: {exc.reason}")
    except URLError as exc:
        return CollectStatus(dataset, scope, "error", 0, str(path), f"URLError: {exc.reason}")
    except Exception as exc:  # noqa: BLE001
        return CollectStatus(dataset, scope, "error", 0, str(path), f"{type(exc).__name__}: {exc}")
    finally:
        time.sleep(0.22)


def main() -> int:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        print("TUSHARE_TOKEN is required.", file=sys.stderr)
        return 2

    statuses: list[CollectStatus] = []
    stock_basic = collect_one(
        token,
        "stock_basic",
        "all_listed",
        {"exchange": "", "list_status": "L"},
        "ts_code,symbol,name,area,industry,market,exchange,list_date",
        OUTPUT_DIR / "stock_basic.csv",
    )
    statuses.append(stock_basic)

    for company in COMPANIES:
        for dataset, fields in DATASETS.items():
            params: dict[str, Any] = {"ts_code": company["ts_code"]}
            if dataset not in {"dividend", "pledge_stat"}:
                params.update({"start_date": company["list_date"], "end_date": TODAY})
            path = OUTPUT_DIR / dataset / f"{company['ts_code']}.csv"
            statuses.append(
                collect_one(
                    token,
                    dataset,
                    f"{company['name']}:{company['ts_code']}",
                    params,
                    fields,
                    path,
                )
            )

    index_fields = "ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount"
    for index in INDEXES:
        statuses.append(
            collect_one(
                token,
                "index_daily",
                f"{index['name']}:{index['ts_code']}",
                {"ts_code": index["ts_code"], "start_date": index["start_date"], "end_date": TODAY},
                index_fields,
                OUTPUT_DIR / "index_daily" / f"{index['ts_code']}.csv",
            )
        )

    summary_path = OUTPUT_DIR / "_collection_summary.csv"
    write_rows(
        summary_path,
        ["dataset", "scope", "status", "rows", "path", "message"],
        [status.__dict__ for status in statuses],
    )
    print(
        f"ok={sum(s.status == 'ok' for s in statuses)} empty={sum(s.status == 'empty' for s in statuses)} error={sum(s.status == 'error' for s in statuses)}"
    )
    print(f"summary={summary_path}")
    return 0 if not any(status.status == "error" for status in statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())

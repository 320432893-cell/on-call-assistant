"""Comprehensive tushare pull: full financial indicators + statements + employees + main-business (overseas)."""

# 职责：用 2000 积分 token 把能拉的全拉,补齐当初只采7字段的缺口 = INV-035。每家公司全历史:
#       ① fina_indicator 完整(108字段:速动/应收周转/固定资产周转/EBITDA/FCFF/净负债/扣非...);
#       ② income/balancesheet/cashflow 完整(三费/利润总额/存货/应收/筹资CF...);
#       ③ stock_company(员工数→人均指标);④ fina_mainbz 按地区(海外收入占比)。
# 不做什么：不建特征/不建模;只落原始 CSV 到 data/raw/tushare/*_full/。token 走环境变量 TS_TOKEN。
# 允许依赖层：标准库、pandas、tushare、peer_universe。
# 谁不应该 import：建模脚本不应 import 本入口。
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import tushare as ts
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
PERIODS = [f"{y}1231" for y in range(2015, 2025)]  # 主营构成按年


def safe(fn, *, tries: int = 5, pause: float = 0.6):
    for k in range(tries):
        try:
            d = fn()
            time.sleep(pause)
            return d
        except Exception as e:  # noqa: BLE001 - 网络/限频统一重试
            wait = 2.0 * (k + 1)
            print(f"  retry {k + 1}/{tries} ({str(e)[:60]}) wait {wait}s")
            time.sleep(wait)
    return None


def main() -> None:
    ts.set_token(os.environ["TS_TOKEN"])
    pro = ts.pro_api()
    codes = [c["ts_code"] for c in load_companies()]
    # 全历史单调用接口:一次拉完整字段全历史
    full = {
        "fina_indicator_full": lambda c: pro.fina_indicator(ts_code=c),
        "income_full": lambda c: pro.income(ts_code=c),
        "balancesheet_full": lambda c: pro.balancesheet(ts_code=c),
        "cashflow_full": lambda c: pro.cashflow(ts_code=c),
    }
    for sub, fn in full.items():
        outdir = RAW / sub
        outdir.mkdir(parents=True, exist_ok=True)
        ok = 0
        for c in codes:
            d = safe(lambda c=c: fn(c))
            if d is not None and len(d):
                d.to_csv(outdir / f"{c}.csv", index=False)
                ok += 1
        print(f"[{sub}] {ok}/{len(codes)} 家  字段示例:", list(d.columns)[:8] if d is not None else "-")

    # stock_company(员工/注册地/主营):14 家合一表
    rows = []
    for c in codes:
        d = safe(lambda c=c: pro.stock_company(ts_code=c))
        if d is not None and len(d):
            rows.append(d)
    if rows:
        sc = pd.concat(rows, ignore_index=True)
        sc.to_csv(RAW / "stock_company.csv", index=False)
        emp = sc.set_index("ts_code")["employees"].to_dict() if "employees" in sc.columns else {}
        print(f"[stock_company] {len(sc)} 家  员工数样例:", dict(list(emp.items())[:4]))

    # fina_mainbz 按地区(海外收入占比):每家逐年
    mbdir = RAW / "fina_mainbz"
    mbdir.mkdir(parents=True, exist_ok=True)
    okm = 0
    for c in codes:
        parts = []
        for p in PERIODS:
            d = safe(lambda c=c, p=p: pro.fina_mainbz(ts_code=c, period=p, type="D"), tries=3, pause=0.4)
            if d is not None and len(d):
                d["period"] = p
                parts.append(d)
        if parts:
            pd.concat(parts, ignore_index=True).to_csv(mbdir / f"{c}.csv", index=False)
            okm += 1
    print(f"[fina_mainbz·地区] {okm}/{len(codes)} 家")
    print("DONE")


if __name__ == "__main__":
    main()

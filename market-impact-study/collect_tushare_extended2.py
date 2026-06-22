"""Extended tushare pull (round 2): re-fetch missing full tables + ownership/foreign/leverage/flow interfaces."""
# 职责：补 INV-035 缺口 = INV-036:① 重拉缺失的 fina_indicator_full(6家)/cashflow_full(2家);
#       ② 新增市值相关接口全14家:北向持股 hk_hold、融资融券 margin_detail、股东人数 stk_holdernumber、
#       前十大流通股东 top10_floatholders、资金流 moneyflow。日频接口按年循环防截断。token 走 TS_TOKEN。
# 不做什么：不建特征/不建模;只落原始 CSV。report_rc/cyq_perf 无权限,跳过。
# 允许依赖层：标准库、pandas、tushare、peer_universe。
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import tushare as ts
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
YEARS = list(range(2016, 2026))


def safe(fn, *, tries: int = 5, pause: float = 0.5):
    for k in range(tries):
        try:
            d = fn()
            time.sleep(pause)
            return d
        except Exception as e:  # noqa: BLE001 - 网络/限频统一重试
            time.sleep(1.5 * (k + 1))
            if k == tries - 1:
                print(f"  give up ({str(e)[:50]})")
    return None


def daily_by_year(pro_fn, code: str) -> pd.DataFrame:
    parts = []
    for y in YEARS:
        d = safe(lambda y=y: pro_fn(ts_code=code, start_date=f"{y}0101", end_date=f"{y}1231"), tries=3, pause=0.35)
        if d is not None and len(d):
            parts.append(d)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main() -> None:
    ts.set_token(os.environ["TS_TOKEN"])
    pro = ts.pro_api()
    codes = [c["ts_code"] for c in load_companies()]

    # ① 补缺失的 full 表
    for sub, fn in [("fina_indicator_full", pro.fina_indicator), ("cashflow_full", pro.cashflow)]:
        outdir = RAW / sub
        miss = [c for c in codes if not (outdir / f"{c}.csv").exists()]
        for c in miss:
            d = safe(lambda c=c: fn(ts_code=c))
            if d is not None and len(d):
                d.to_csv(outdir / f"{c}.csv", index=False)
        print(f"[补 {sub}] 原缺 {len(miss)} → 现有 {len(list(outdir.glob('*.csv')))}/{len(codes)}")

    # ② 季频/不定期接口(单调用全历史)
    for sub, fn in [("stk_holdernumber", pro.stk_holdernumber), ("top10_floatholders", pro.top10_floatholders)]:
        outdir = RAW / sub
        outdir.mkdir(parents=True, exist_ok=True)
        ok = 0
        for c in codes:
            d = safe(lambda c=c: fn(ts_code=c, start_date="20100101", end_date="20251231"))
            if d is not None and len(d):
                d.to_csv(outdir / f"{c}.csv", index=False)
                ok += 1
        print(f"[{sub}] {ok}/{len(codes)} 家")

    # ③ 日频接口(按年循环)
    for sub, fn in [("hk_hold", pro.hk_hold), ("margin_detail", pro.margin_detail), ("moneyflow", pro.moneyflow)]:
        outdir = RAW / sub
        outdir.mkdir(parents=True, exist_ok=True)
        ok = 0
        for c in codes:
            d = daily_by_year(fn, c)
            if len(d):
                d.to_csv(outdir / f"{c}.csv", index=False)
                ok += 1
        print(f"[{sub}] {ok}/{len(codes)} 家")
    print("DONE2")


if __name__ == "__main__":
    main()

"""Factor-model CAR: upgrade 异常反应 from naive peer-demean to estimated-beta factor-adjusted residual."""

# 职责：把事件异常反应从"剔同行等权(默认β=1/α=0)"升级为因子模型 CAR = INV-023:
#       估计窗回归 dret_i ~ 市场(创业板指) + 行业(剔自身同行) 得 α/β,事件窗 CAR=去掉因子暴露后的特异反应;
#       并把每个反应分解为 系统(因子暴露) vs 特异(CAR),对比旧口径。让"异常"二字站得住(账本缺口#5)。
# 不做什么：不重训因果(本步是测量地基);产出供后续解释/稳健性复用。
# 允许依赖层：标准库、numpy/pandas、peer_universe、data/raw 行情+指数、cate_14firm 产物。
# 谁不应该 import：建模脚本不应 import 本入口,应读其产物。
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
CATE = Path("market-impact-study/data/processed/modeling/cate_14firm/cate_panel_14firm.csv")
OUT_DIR = Path("market-impact-study/data/processed/modeling/cate_14firm")
MKT_INDEX = "399006.SZ"  # 创业板指(14家多在创业板/科创,作市场因子)
EST_WIN, GAP, EVENT_WIN = 250, 21, 20  # 估计窗长 / 估计窗与事件间隔 / 事件窗[0,+20]
MIN_EST = 80  # 估计窗最少有效天数


def daily_returns(codes: list[str]) -> pd.DataFrame:
    """Wide df: index=trade_date, cols=ts_code, values=daily total_mv return."""
    cols = {}
    for c in codes:
        d = pd.read_csv(RAW / "daily_basic" / f"{c}.csv")
        d.columns = [x.lstrip("﻿") for x in d.columns]
        d["trade_date"] = d["trade_date"].astype(int)
        s = d.sort_values("trade_date").set_index("trade_date")["total_mv"].astype(float)
        cols[c] = s / s.shift(1) - 1
    return pd.DataFrame(cols)


def market_return() -> pd.Series:
    d = pd.read_csv(RAW / "index_daily" / f"{MKT_INDEX}.csv")
    d.columns = [x.lstrip("﻿") for x in d.columns]
    d["trade_date"] = d["trade_date"].astype(int)
    d = d.sort_values("trade_date")
    return (pd.to_numeric(d["close"], errors="coerce") / pd.to_numeric(d["pre_close"], errors="coerce") - 1).set_axis(
        d["trade_date"]
    )


def factor_car(ret: pd.DataFrame, mkt: pd.Series, code: str, event_day: int) -> dict | None:
    s = ret[code].dropna()
    dates = s.index.to_numpy()
    pos = int(np.searchsorted(dates, event_day))
    if pos >= len(dates) or dates[pos] != event_day:
        pos = int(np.searchsorted(dates, event_day))  # first trading day >= event
        if pos >= len(dates):
            return None
    est_lo = pos - GAP - EST_WIN
    est_hi = pos - GAP
    if est_lo < 0:
        est_lo = 0
    est_dates = dates[est_lo:est_hi]
    ev_dates = dates[pos : pos + EVENT_WIN]
    if len(est_dates) < MIN_EST or len(ev_dates) < EVENT_WIN // 2:
        return None
    peer = ret.drop(columns=[code]).mean(axis=1)  # equal-weight ex-self sector factor
    # estimation-window design
    ye = s.reindex(est_dates).to_numpy()
    xe = np.column_stack(
        [np.ones(len(est_dates)), mkt.reindex(est_dates).to_numpy(), peer.reindex(est_dates).to_numpy()]
    )
    ok = ~np.isnan(ye) & ~np.isnan(xe).any(axis=1)
    if ok.sum() < MIN_EST:
        return None
    beta, *_ = np.linalg.lstsq(xe[ok], ye[ok], rcond=None)
    # event window
    yv = s.reindex(ev_dates).to_numpy()
    xv = np.column_stack([np.ones(len(ev_dates)), mkt.reindex(ev_dates).to_numpy(), peer.reindex(ev_dates).to_numpy()])
    okv = ~np.isnan(yv) & ~np.isnan(xv).any(axis=1)
    pred = xv[okv] @ beta
    ar = yv[okv] - pred
    systematic = xv[okv, 1:] @ beta[1:]  # market+sector explained part (excl alpha)
    return {
        "car_factor": float(ar.sum()),
        "raw_ret": float(yv[okv].sum()),
        "systematic": float(systematic.sum()),
        "alpha_sum": float(beta[0] * okv.sum()),
        "beta_mkt": float(beta[1]),
        "beta_sector": float(beta[2]),
        "est_n": int(ok.sum()),
    }


def main() -> None:
    codes = [c["ts_code"] for c in load_companies()]
    ret = daily_returns(codes)
    mkt = market_return()
    panel = pd.read_csv(CATE)
    ev = panel[panel["D"] == 1].copy()

    recs = []
    for r in ev.itertuples(index=False):
        fc = factor_car(ret, mkt, r.ts_code, int(r.trade_date))
        if fc:
            fc.update(
                {"ts_code": r.ts_code, "subtype": r.subtype, "trade_date": int(r.trade_date), "rel_old": float(r.rel)}
            )
            recs.append(fc)
    out = pd.DataFrame(recs)
    out.to_csv(OUT_DIR / "factor_car_events.csv", index=False)

    # per-subtype: old vs factor-CAR + systematic/idiosyncratic split
    rows = []
    for s, g in out.groupby("subtype"):
        rows.append(
            {
                "subtype": s,
                "n": len(g),
                "rel_old_%": round(g["rel_old"].mean() * 100, 2),
                "car_factor_%": round(g["car_factor"].mean() * 100, 2),
                "raw_%": round(g["raw_ret"].mean() * 100, 2),
                "systematic_%": round(g["systematic"].mean() * 100, 2),
                "idio_share": round(float((g["car_factor"].abs() / (g["raw_ret"].abs() + 1e-9)).median()), 2),
                "beta_mkt_med": round(float(g["beta_mkt"].median()), 2),
                "corr_old_new": round(float(g[["rel_old", "car_factor"]].corr().iloc[0, 1]), 2),
            }
        )
    summ = pd.DataFrame(rows).sort_values("car_factor_%", ascending=False)
    summ.to_csv(OUT_DIR / "factor_car_summary.csv", index=False)
    print(f"events with factor-CAR: {len(out)} / {len(ev)}")
    print(summ.to_string(index=False))
    print(f"\nsaved -> {OUT_DIR}/factor_car_events.csv , factor_car_summary.csv")


if __name__ == "__main__":
    main()

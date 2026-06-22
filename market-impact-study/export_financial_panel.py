"""Export company x year financial panel (revenue/net-profit/market-cap + CAGR) for the dashboard finance section."""

# 职责：导出 14 家公司 × 年份的财务面板(营收/净利/年末市值,亿元)+ 全程 CAGR/市值倍数 + 固定配色 = INV-029,
#       供仪表板财务对比段(逐年柱时间轴动画 + 增长气泡象限)。移为固定深红。
# 不做什么：不做估计/不可视化;只产数据 JSON。
# 允许依赖层：标准库、pandas/numpy、peer_universe、data/raw 行情/财务。
# 谁不应该 import：建模脚本不应 import 本入口。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
OUT = Path("market-impact-study/data/processed/modeling/financial_panel.json")
YIWEI = "300590.SZ"
# 固定配色:移为深红,其余区分度高的稳重色
PALETTE = [
    "#2563eb",
    "#16a34a",
    "#f59e0b",
    "#7c3aed",
    "#0891b2",
    "#ca8a04",
    "#9333ea",
    "#0ea5e9",
    "#65a30d",
    "#e11d48",
    "#475569",
    "#b45309",
    "#0d9488",
]


def annual(code: str) -> pd.DataFrame:
    inc = pd.read_csv(RAW / "income" / f"{code}.csv")
    inc.columns = [c.lstrip("﻿") for c in inc.columns]
    inc = inc[pd.to_numeric(inc["end_date"], errors="coerce").notna()].copy()
    inc["end_date"] = inc["end_date"].astype(int)
    inc = inc[inc["end_date"] % 10000 == 1231].copy()
    inc["yr"] = inc["end_date"] // 10000
    inc["rev"] = pd.to_numeric(inc["revenue"], errors="coerce") / 1e8
    inc["ni"] = pd.to_numeric(inc["n_income_attr_p"], errors="coerce") / 1e8
    return inc.sort_values(["yr", "ann_date"]).groupby("yr").last()[["rev", "ni"]]


def mv_by_year(code: str) -> pd.Series:
    db = pd.read_csv(RAW / "daily_basic" / f"{code}.csv")
    db.columns = [c.lstrip("﻿") for c in db.columns]
    db["trade_date"] = db["trade_date"].astype(int)
    db["yr"] = db["trade_date"] // 10000
    return db.sort_values("trade_date").groupby("yr")["total_mv"].last() / 1e4


def cagr(series: pd.Series) -> float:
    s = series.dropna()
    if len(s) < 3 or s.iloc[0] <= 0 or s.iloc[-1] <= 0:
        return float("nan")
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / (len(s) - 1)) - 1) * 100


def main() -> None:
    companies = load_companies()
    years = list(range(2016, 2027))
    out_companies = []
    palette_i = 0
    for c in companies:
        code, name = c["ts_code"], c["name"]
        fin = annual(code)
        mv = mv_by_year(code)
        by_year = []
        for y in years:
            rev = float(fin.loc[y, "rev"]) if y in fin.index and pd.notna(fin.loc[y, "rev"]) else None
            ni = float(fin.loc[y, "ni"]) if y in fin.index and pd.notna(fin.loc[y, "ni"]) else None
            mvv = float(mv[y]) if y in mv.index and pd.notna(mv[y]) else None
            by_year.append(
                {
                    "yr": y,
                    "rev": round(rev, 2) if rev is not None else None,
                    "ni": round(ni, 3) if ni is not None else None,
                    "mv": round(mvv, 1) if mvv is not None else None,
                }
            )
        rev_s = fin["rev"]
        revc = cagr(rev_s)
        nic = cagr(fin["ni"])
        mv_v = mv.dropna()
        mult = round(float(mv_v.iloc[-1] / mv_v.iloc[0]), 1) if len(mv_v) >= 2 and mv_v.iloc[0] > 0 else None
        latest_rev = float(rev_s.dropna().iloc[-1]) if rev_s.notna().any() else None
        color = YIWEI_COLOR if code == YIWEI else PALETTE[palette_i % len(PALETTE)]
        if code != YIWEI:
            palette_i += 1
        out_companies.append(
            {
                "code": code,
                "name": name,
                "color": color,
                "is_yiwei": code == YIWEI,
                "by_year": by_year,
                "rev_cagr": round(revc, 1) if not np.isnan(revc) else None,
                "ni_cagr": round(nic, 1) if not np.isnan(nic) else None,
                "mult": mult,
                "latest_rev": round(latest_rev, 1) if latest_rev else None,
            }
        )
    # 按市值倍数排序(主对象移为置顶便于图例)
    out_companies.sort(key=lambda x: (not x["is_yiwei"], -(x["mult"] or 0)))
    OUT.write_text(json.dumps({"years": years, "companies": out_companies}, ensure_ascii=False), encoding="utf-8")
    print(f"companies={len(out_companies)} years={years[0]}-{years[-1]}  saved -> {OUT}")
    for c in out_companies[:6]:
        print(
            f"  {c['name']:6s} 市值倍数={c['mult']} 营收CAGR={c['rev_cagr']}% 净利CAGR={c['ni_cagr']}% 色={c['color']}"
        )


YIWEI_COLOR = "#c0392b"

if __name__ == "__main__":
    main()

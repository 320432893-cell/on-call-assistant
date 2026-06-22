"""Build the 14-firm capital-action heterogeneity panel and within-firm valuation x subtype table."""

# 职责：在 14 家 universe 上,按"公司内全历史 PE 估值分位 × 资本动作子类 → 20 日剔同行异常反应"
#       做异质性描述统计(INV-013 的 9 家结论在更大样本/更干净事件定义下的 robustness 复核 = INV-015)。
# 不做什么：不训练模型/不做因果推断/不建特征宽表；基准沿用 calculate_event_car 口径(剔自身 universe 均值),不引入新口径。
# 允许依赖层：标准库、pandas/numpy/scipy、peer_universe(口径/基准)、data/raw 行情、data/processed 9 家公告分类宽表。
# 谁不应该 import：建模/特征脚本不应 import 本入口;它们应读本脚本产物。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from peer_universe import load_companies
from scipy import stats

RAW_TUSHARE = Path("market-impact-study/data/raw/tushare")
PROCESSED = Path("market-impact-study/data/processed")
V3_WIDE = PROCESSED / "modeling" / "modeling_dataset_enhanced_v3.csv"
OUT_DIR = PROCESSED / "modeling" / "heterogeneity_14firm"

HORIZON = 20  # 交易日,与 calculate_event_car p0_p20 窗口一致
# 回购"首发/决策"阶段关键词(只取决策事件,剔进展/完成/实施等机械跟随公告)
REPO_INIT_KEYS = ("预案", "股东大会", "提议", "方案", "报告书")
# 14 家全覆盖的 tushare 结构化资本动作源
STRUCTURED = [
    ("repurchase", "股份回购(首发)", REPO_INIT_KEYS),
    ("dividend", "分红/权益分派", None),
    ("forecast", "业绩预告", None),
    ("express", "业绩快报", None),
]
# 9 家公告分类子类(无 tushare 结构化对应,仅原 9 家有公告文本)
ANNOUNCEMENT_ONLY = ["定增/再融资", "股东增减持/限售流通", "股权激励/员工持股"]


def build_panels(codes: list[str]) -> dict[str, pd.DataFrame]:
    """Per-firm daily panel: total_mv, pe, forward-20d mv_return, prior-day pe."""
    panels: dict[str, pd.DataFrame] = {}
    for code in codes:
        path = RAW_TUSHARE / "daily_basic" / f"{code}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        frame.columns = [c.lstrip("﻿") for c in frame.columns]
        frame = frame[["trade_date", "total_mv", "pe"]].copy()
        frame["trade_date"] = frame["trade_date"].astype(int)
        frame = frame.sort_values("trade_date").reset_index(drop=True)
        frame["total_mv"] = pd.to_numeric(frame["total_mv"], errors="coerce")
        frame["pe"] = pd.to_numeric(frame["pe"], errors="coerce")
        mv = frame["total_mv"].to_numpy()
        size = len(frame)
        pre = np.array([mv[max(0, i - 1)] for i in range(size)])
        end = np.array([mv[min(size - 1, i + HORIZON)] for i in range(size)])
        with np.errstate(invalid="ignore", divide="ignore"):
            frame["mv_ret20"] = np.where((pre > 0) & ~np.isnan(end), end / pre - 1, np.nan)
        frame["pe_pre"] = frame["pe"].shift(1)
        panels[code] = frame
    return panels


def peer_relative(panels: dict[str, pd.DataFrame]) -> dict[tuple[str, int], float]:
    """relative reaction = own 20d mv_return - all-but-self mean over same calendar date."""
    long = pd.concat(
        [p[["trade_date", "mv_ret20"]].assign(ts_code=c) for c, p in panels.items()],
        ignore_index=True,
    ).dropna(subset=["mv_ret20"])
    grp = long.groupby("trade_date")["mv_ret20"]
    long["tot"] = grp.transform("sum")
    long["cnt"] = grp.transform("count")
    long = long[long["cnt"] >= 2].copy()
    long["peer_avg"] = (long["tot"] - long["mv_ret20"]) / (long["cnt"] - 1)
    long["rel"] = long["mv_ret20"] - long["peer_avg"]
    return {(r.ts_code, int(r.trade_date)): float(r.rel) for r in long.itertuples(index=False)}


def make_pe_ranker(panels: dict[str, pd.DataFrame]):
    """within-firm valuation percentile = event-day PE within firm's full positive-PE daily history."""
    base = {c: np.sort(p.loc[p["pe_pre"] > 0, "pe_pre"].to_numpy()) for c, p in panels.items()}

    def val_pct(code: str, pe: float) -> float:
        arr = base.get(code)
        if arr is None or len(arr) < 20 or pd.isna(pe) or pe <= 0:
            return np.nan
        return float(np.searchsorted(arr, pe, side="right") / len(arr))

    return val_pct


def event_day(panels: dict[str, pd.DataFrame], code: str, ann: int) -> int | None:
    arr = panels[code]["trade_date"].to_numpy() if code in panels else None
    if arr is None:
        return None
    idx = int(np.searchsorted(arr, ann, side="left"))
    return int(arr[idx]) if idx < len(arr) else None


def collect_events(codes: set[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for folder, subtype, init_keys in STRUCTURED:
        for path in (RAW_TUSHARE / folder).glob("*.csv"):
            code = path.stem
            if code not in codes or path.stat().st_size == 0:
                continue
            frame = pd.read_csv(path)
            frame.columns = [c.lstrip("﻿") for c in frame.columns]
            if "ann_date" not in frame.columns or len(frame) == 0:
                continue
            frame["ann_date"] = pd.to_numeric(frame["ann_date"], errors="coerce")
            frame = frame.dropna(subset=["ann_date"])
            if init_keys and "proc" in frame.columns:
                mask = frame["proc"].astype(str).apply(lambda p, keys=init_keys: any(k in p for k in keys))
                frame = frame[mask]
            for ann in frame["ann_date"].astype(int).unique():
                rows.append({"ts_code": code, "ann_date": int(ann), "subtype": subtype, "scope": "14firm"})

    wide = pd.read_csv(V3_WIDE, low_memory=False)
    datecol = next(c for c in ("event_date", "trade_date", "anchor_date", "group_event_date") if c in wide.columns)
    for subtype in ANNOUNCEMENT_ONLY:
        sub = wide[wide["capital_action_subtype"] == subtype].copy()
        sub["ann_date"] = pd.to_datetime(sub[datecol], errors="coerce").dt.strftime("%Y%m%d")
        sub = sub.dropna(subset=["ann_date"])
        for row in sub.itertuples(index=False):
            rows.append({"ts_code": row.ts_code, "ann_date": int(row.ann_date), "subtype": subtype, "scope": "9firm"})
    return pd.DataFrame(rows)


def tcell(values: pd.Series) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 8:
        return {"mean_pct": float(arr.mean() * 100) if len(arr) else float("nan"), "p": float("nan"), "n": len(arr)}
    test = stats.ttest_1samp(arr, 0.0)
    return {"mean_pct": float(arr.mean() * 100), "p": float(test.pvalue), "n": len(arr)}


def main() -> None:
    companies = load_companies()
    codes = [c["ts_code"] for c in companies]
    names = {c["ts_code"]: c["name"] for c in companies}
    panels = build_panels(codes)
    rel = peer_relative(panels)
    val_pct = make_pe_ranker(panels)

    events = collect_events(set(codes))
    events = events[events["ts_code"].isin(codes)].drop_duplicates(["ts_code", "ann_date", "subtype"])
    events["event_day"] = [event_day(panels, c, a) for c, a in zip(events["ts_code"], events["ann_date"], strict=False)]
    events = events.dropna(subset=["event_day"])
    events["event_day"] = events["event_day"].astype(int)
    events["rel"] = [rel.get((c, d)) for c, d in zip(events["ts_code"], events["event_day"], strict=False)]
    pe_lookup = {c: dict(zip(p["trade_date"], p["pe_pre"], strict=False)) for c, p in panels.items()}
    events["pe_pre"] = [
        pe_lookup.get(c, {}).get(d) for c, d in zip(events["ts_code"], events["event_day"], strict=False)
    ]
    events = events.dropna(subset=["rel"])
    events["val_pct"] = [val_pct(c, pe) for c, pe in zip(events["ts_code"], events["pe_pre"], strict=False)]
    events["firm"] = events["ts_code"].map(names)

    summary_rows: list[dict[str, object]] = []
    for subtype, group in events.groupby("subtype"):
        withpe = group[group["val_pct"].notna()]
        t1 = withpe[withpe["val_pct"] <= 1 / 3]["rel"]
        t2 = withpe[(withpe["val_pct"] > 1 / 3) & (withpe["val_pct"] <= 2 / 3)]["rel"]
        t3 = withpe[withpe["val_pct"] > 2 / 3]["rel"]
        slope = float("nan")
        slope_p = float("nan")
        if len(withpe) >= 15:
            reg = stats.linregress(withpe["val_pct"], withpe["rel"] * 100)
            slope, slope_p = float(reg.slope), float(reg.pvalue)
        summary_rows.append(
            {
                "subtype": subtype,
                "scope": group["scope"].iloc[0],
                "n": len(group),
                "firms": int(group["ts_code"].nunique()),
                "all": tcell(group["rel"]),
                "T1_low": tcell(t1),
                "T2_mid": tcell(t2),
                "T3_high": tcell(t3),
                "pe_slope": slope,
                "pe_slope_p": slope_p,
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events.to_csv(OUT_DIR / "heterogeneity_panel_14firm.csv", index=False)
    flat = []
    for row in summary_rows:
        flat.append(
            {
                "subtype": row["subtype"],
                "scope": row["scope"],
                "n": row["n"],
                "firms": row["firms"],
                "all_pct": round(row["all"]["mean_pct"], 2),
                "all_p": round(row["all"]["p"], 3),
                "T1_low_pct": round(row["T1_low"]["mean_pct"], 2),
                "T1_low_p": round(row["T1_low"]["p"], 3),
                "T2_mid_pct": round(row["T2_mid"]["mean_pct"], 2),
                "T3_high_pct": round(row["T3_high"]["mean_pct"], 2),
                "T3_high_p": round(row["T3_high"]["p"], 3),
                "pe_slope": round(row["pe_slope"], 2),
                "pe_slope_p": round(row["pe_slope_p"], 3),
            }
        )
    table = pd.DataFrame(flat).sort_values(["scope", "subtype"]).reset_index(drop=True)
    table.to_csv(OUT_DIR / "heterogeneity_summary_14firm.csv", index=False)
    (OUT_DIR / "heterogeneity_summary_14firm.json").write_text(
        json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"events with reaction: {len(events)} | firms: {events['ts_code'].nunique()}")
    print(table.to_string(index=False))
    print(f"\nsaved -> {OUT_DIR}/")


if __name__ == "__main__":
    main()

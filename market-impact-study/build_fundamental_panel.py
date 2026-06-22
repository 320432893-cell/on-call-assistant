"""Build a point-in-time fundamental feature panel (profitability/quality/leverage/growth) for the causal model."""

# 职责：把 tushare 四张财务表(fina_indicator/income/balancesheet/cashflow)按报告期合并成
#       PIT 基本面面板 = INV-031:每行一个(公司,报告期),以 ann_date(披露日)为可用时点,
#       供因果面板按 merge_asof 接入任意 firm-day(处理/对照都能接)。把"早就算好却没接进因果"的
#       基本面(ROE/盈利质量/杠杆/现金流/成长)正式喂给 DML 的混淆控制 W 与因果森林效应修饰 X。
# 不做什么：不做估值分位(留给消费方按 pe→pb→ps 兜底)、不做估计/可视化;只产 PIT 特征表。
# 防泄漏：只用 ann_date(实际披露日);消费方 merge_asof(direction=backward) 取事件前最近一期。
# 允许依赖层：标准库、numpy/pandas、peer_universe、data/raw/tushare。
# 谁不应该 import：建模/因果脚本不应 import 本入口,只读其输出 CSV。
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
OUT = Path("market-impact-study/data/processed/modeling/fundamental_panel.csv")


def _read(table: str, code: str, cols: list[str]) -> pd.DataFrame:
    path = RAW / table / f"{code}.csv"
    if not path.exists():
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(path)
    d.columns = [c.lstrip("﻿") for c in d.columns]
    keep = [c for c in cols if c in d.columns]
    d = d[keep].copy()
    for c in ("ann_date", "end_date"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d[d["end_date"].notna()] if "end_date" in d.columns else d


def _latest_per_period(d: pd.DataFrame) -> pd.DataFrame:
    # 同一报告期可能多次披露(修正),取 ann_date 最晚的一条
    if d.empty:
        return d
    return d.sort_values(["end_date", "ann_date"]).groupby("end_date", as_index=False).last()


def firm_panel(code: str) -> pd.DataFrame:
    fi = _latest_per_period(
        _read(
            "fina_indicator",
            code,
            ["ann_date", "end_date", "roe", "roa", "grossprofit_margin", "netprofit_margin", "rd_exp", "ocfps", "bps"],
        )
    )
    inc = _latest_per_period(
        _read("income", code, ["ann_date", "end_date", "revenue", "n_income_attr_p", "operate_profit"])
    )
    bal = _latest_per_period(
        _read(
            "balancesheet",
            code,
            [
                "ann_date",
                "end_date",
                "total_assets",
                "total_liab",
                "total_hldr_eqy_inc_min_int",
                "total_cur_assets",
                "total_cur_liab",
            ],
        )
    )
    cf = _latest_per_period(
        _read(
            "cashflow", code, ["ann_date", "end_date", "n_cashflow_act", "n_cashflow_inv_act", "c_cash_equ_end_period"]
        )
    )
    if inc.empty:
        return pd.DataFrame()
    # 以 income 报告期为骨架,其余表按 end_date 左接;ann_date 取各表最晚(全部披露后才可用)
    m = inc.rename(columns={"ann_date": "ann_inc"})
    for part, suf in ((fi, "fi"), (bal, "bal"), (cf, "cf")):
        if not part.empty:
            m = m.merge(part.rename(columns={"ann_date": f"ann_{suf}"}), on="end_date", how="left")
    ann_cols = [c for c in m.columns if c.startswith("ann_")]
    m["ann_date"] = m[ann_cols].max(axis=1)
    m = m[m["ann_date"].notna()].copy()
    m["ts_code"] = code

    rev = pd.to_numeric(m.get("revenue"), errors="coerce")
    ni = pd.to_numeric(m.get("n_income_attr_p"), errors="coerce")
    ta = pd.to_numeric(m.get("total_assets"), errors="coerce")
    tl = pd.to_numeric(m.get("total_liab"), errors="coerce")
    cur_a = pd.to_numeric(m.get("total_cur_assets"), errors="coerce")
    cur_l = pd.to_numeric(m.get("total_cur_liab"), errors="coerce")
    ocf = pd.to_numeric(m.get("n_cashflow_act"), errors="coerce")
    icf = pd.to_numeric(m.get("n_cashflow_inv_act"), errors="coerce")
    cash = pd.to_numeric(m.get("c_cash_equ_end_period"), errors="coerce")
    rd = pd.to_numeric(m.get("rd_exp"), errors="coerce")
    op = pd.to_numeric(m.get("operate_profit"), errors="coerce")
    eq_rep = pd.to_numeric(m.get("total_hldr_eqy_inc_min_int"), errors="coerce")
    equity = eq_rep.where(eq_rep.notna(), (ta - tl))  # 优先报表净资产,缺则资产−负债

    out = pd.DataFrame({"ts_code": code, "end_date": m["end_date"].astype(int), "ann_date": m["ann_date"].astype(int)})
    # 盈利能力:优先 fina_indicator,缺则用原始报表直接算(净利/净资产 等),少依赖预算字段
    out["f_roe"] = pd.to_numeric(m.get("roe"), errors="coerce").fillna((ni / equity * 100).where(equity > 0))
    out["f_roa"] = pd.to_numeric(m.get("roa"), errors="coerce").fillna((ni / ta * 100).where(ta > 0))
    out["f_gross_margin"] = pd.to_numeric(m.get("grossprofit_margin"), errors="coerce")
    out["f_net_margin"] = pd.to_numeric(m.get("netprofit_margin"), errors="coerce").fillna(
        (ni / rev * 100).where(rev > 0)
    )
    out["f_op_margin"] = (op / rev * 100).where(rev > 0)  # 营业利润率
    # 质量:研发强度 / 经营现金流含金量 / 自由现金流
    out["f_rd_intensity"] = (rd / rev * 100).where(rev > 0)
    out["f_ocf_to_rev"] = (ocf / rev * 100).where(rev > 0)
    out["f_ocf_to_assets"] = (ocf / ta * 100).where(ta > 0)
    out["f_fcf_to_rev"] = ((ocf + icf) / rev * 100).where(rev > 0)  # 自由现金流/营收(经营+投资)
    out["f_cash_to_assets"] = (cash / ta * 100).where(ta > 0)  # 现金充裕度
    # 杠杆 / 流动性 / 效率
    out["f_debt_to_assets"] = (tl / ta * 100).where(ta > 0)
    out["f_current_ratio"] = (cur_a / cur_l).where(cur_l > 0)
    out["f_equity_mult"] = (ta / equity).where(equity > 0)  # 权益乘数(财务杠杆)
    out["f_asset_turn"] = (rev / ta).where(ta > 0)  # 资产周转率(效率)
    out["f_bps"] = pd.to_numeric(m.get("bps"), errors="coerce")
    out["_rev"] = rev
    out["_ni"] = ni
    return out


def _growth(out: pd.DataFrame) -> pd.DataFrame:
    # 成长:年报口径(end_date 年末)算 YoY/CAGR2/CAGR3,再前向填充给各期(消费方取事件前最近一期)
    out = out.sort_values("end_date").reset_index(drop=True)
    ann = out[out["end_date"] % 10000 == 1231].copy().sort_values("end_date")
    ann["yr"] = ann["end_date"] // 10000

    def cagr(s: pd.Series, n: int) -> pd.Series:
        prev = s.shift(n)
        with np.errstate(invalid="ignore"):
            g = (s / prev) ** (1 / n) - 1
        return (g * 100).where((s > 0) & (prev > 0))

    g = pd.DataFrame({"end_date": ann["end_date"].to_numpy()})
    g["f_rev_yoy"] = ((ann["_rev"] / ann["_rev"].shift(1) - 1) * 100).where(ann["_rev"].shift(1) > 0).to_numpy()
    g["f_ni_yoy"] = ((ann["_ni"] / ann["_ni"].shift(1) - 1) * 100).where(ann["_ni"].shift(1).abs() > 0).to_numpy()
    g["f_rev_cagr2"] = cagr(ann["_rev"], 2).to_numpy()
    g["f_rev_cagr3"] = cagr(ann["_rev"], 3).to_numpy()
    # 兜底成长:CAGR3→CAGR2→YoY 第一个非空(降缺失,CAGR 仍单独保留)
    g["f_rev_growth"] = g["f_rev_cagr3"].fillna(g["f_rev_cagr2"]).fillna(g["f_rev_yoy"])
    out = out.merge(g, on="end_date", how="left")
    gcols = ["f_rev_yoy", "f_ni_yoy", "f_rev_cagr2", "f_rev_cagr3", "f_rev_growth"]
    out[gcols] = out[gcols].ffill()  # 各报告期carry最近年报成长
    # 水平类(盈利/质量/杠杆)前向填充:研发等只在年报披露,季报carry最近一期已披露值(PIT安全)
    lvl = [
        "f_roe",
        "f_roa",
        "f_gross_margin",
        "f_net_margin",
        "f_op_margin",
        "f_rd_intensity",
        "f_ocf_to_rev",
        "f_ocf_to_assets",
        "f_fcf_to_rev",
        "f_cash_to_assets",
        "f_debt_to_assets",
        "f_current_ratio",
        "f_equity_mult",
        "f_asset_turn",
        "f_bps",
    ]
    out[lvl] = out[lvl].ffill()
    return out.drop(columns=["_rev", "_ni"])


# fina_indicator 完整版(108字段)里现成的比率 → 面板列名(INV-036:直接用 tushare 算好的,免重算)
FULL_MAP = {
    "roic": "f_roic",
    "roe_dt": "f_roe_dt",
    "quick_ratio": "f_quick_ratio",
    "cash_ratio": "f_cash_ratio",
    "ar_turn": "f_ar_turn",
    "fa_turn": "f_fa_turn",
    "assets_turn": "f_assets_turn",
    "saleexp_to_gr": "f_saleexp_ratio",
    "adminexp_of_gr": "f_adminexp_ratio",
    "finaexp_of_gr": "f_finaexp_ratio",
    "or_yoy": "f_or_yoy",
    "dt_netprofit_yoy": "f_dt_ni_yoy",
    "ocf_yoy": "f_ocf_yoy",
    "op_of_gr": "f_op_to_gr",
    "debt_to_eqt": "f_debt_to_eqt",
}


def _full_ratios(code: str) -> pd.DataFrame:
    p = RAW / "fina_indicator_full" / f"{code}.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p)
    d.columns = [c.lstrip("﻿") for c in d.columns]
    d["end_date"] = pd.to_numeric(d["end_date"], errors="coerce")
    d = d.dropna(subset=["end_date"])
    d["end_date"] = d["end_date"].astype(int)
    d = d.sort_values(["end_date", "ann_date"]).groupby("end_date", as_index=False).last()
    cols = ["end_date", *[c for c in FULL_MAP if c in d.columns]]
    out = d[cols].rename(columns=FULL_MAP)
    out["ts_code"] = code
    return out


def _overseas(code: str) -> pd.DataFrame:
    p = RAW / "fina_mainbz" / f"{code}.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p).dropna(subset=["bz_item", "bz_sales"])
    if d.empty:
        return pd.DataFrame()
    it = d["bz_item"].astype(str)
    d["_dom"] = pd.to_numeric(d["bz_sales"], errors="coerce").where(it.str.contains("大陆|境内|国内|中国大陆"), 0)
    d["_ovs"] = pd.to_numeric(d["bz_sales"], errors="coerce").where(
        it.str.contains("国外|境外|海外|北美|南美|欧洲|非洲|美洲|亚洲|外销|出口"), 0
    )
    g = d.groupby("end_date").agg(dom=("_dom", "sum"), ovs=("_ovs", "sum")).reset_index()
    g["f_overseas_share"] = (g["ovs"] / (g["dom"] + g["ovs"]) * 100).where((g["dom"] + g["ovs"]) > 0)
    g["ts_code"] = code
    return g[["ts_code", "end_date", "f_overseas_share"]]


def _employees() -> dict[str, float]:
    p = RAW / "stock_company.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p)
    return dict(zip(d["ts_code"], pd.to_numeric(d.get("employees"), errors="coerce"), strict=False))


def _latest_rev_ni(code: str) -> tuple[float, float]:
    p = RAW / "income_full" / f"{code}.csv"
    if not p.exists():
        return (float("nan"), float("nan"))
    d = pd.read_csv(p)
    d["end_date"] = pd.to_numeric(d["end_date"], errors="coerce")
    d = d[(d["end_date"] % 10000 == 1231)].dropna(subset=["end_date"]).sort_values("end_date")
    if d.empty:
        return (float("nan"), float("nan"))
    return (
        pd.to_numeric(d["revenue"], errors="coerce").iloc[-1],
        pd.to_numeric(d["n_income_attr_p"], errors="coerce").iloc[-1],
    )


def enrich(panel: pd.DataFrame) -> pd.DataFrame:
    emp = _employees()
    parts_full, parts_ovs, percap = [], [], []
    for code in panel["ts_code"].unique():
        parts_full.append(_full_ratios(code))
        parts_ovs.append(_overseas(code))
        rev, ni = _latest_rev_ni(code)
        e = emp.get(code)
        percap.append(
            {
                "ts_code": code,
                "f_rev_per_emp": round(float(rev / e / 1e4), 1) if e and e > 0 and pd.notna(rev) else None,  # 万元/人
                "f_ni_per_emp": round(float(ni / e / 1e4), 1) if e and e > 0 and pd.notna(ni) else None,
            }
        )
    full = (
        pd.concat([p for p in parts_full if not p.empty], ignore_index=True)
        if any(not p.empty for p in parts_full)
        else pd.DataFrame()
    )
    ovs = (
        pd.concat([p for p in parts_ovs if not p.empty], ignore_index=True)
        if any(not p.empty for p in parts_ovs)
        else pd.DataFrame()
    )
    if not full.empty:
        panel = panel.merge(full, on=["ts_code", "end_date"], how="left")
    if not ovs.empty:
        panel = panel.merge(ovs, on=["ts_code", "end_date"], how="left")
        panel["f_overseas_share"] = panel.groupby("ts_code")["f_overseas_share"].ffill()  # 年报口径,季报carry
    panel = panel.merge(pd.DataFrame(percap), on="ts_code", how="left")  # 人均为静态公司特征(当前员工)
    return panel


def main() -> None:
    frames = []
    for c in load_companies():
        fp = firm_panel(c["ts_code"])
        if not fp.empty:
            frames.append(_growth(fp))
    panel = pd.concat(frames, ignore_index=True).sort_values(["ts_code", "ann_date"])
    panel = enrich(panel)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(OUT, index=False)
    feats = [c for c in panel.columns if c.startswith("f_")]
    miss = (panel[feats].isna().mean() * 100).round(0)
    print(f"PIT 基本面面板:{len(panel)} 行 × {panel['ts_code'].nunique()} 家,{len(feats)} 个特征")
    print("特征缺失%:", {k: int(v) for k, v in miss.items()})
    print("saved ->", OUT)


if __name__ == "__main__":
    main()

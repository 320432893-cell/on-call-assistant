"""Explain market-cap CHANGES (主功能,非预测):3-channel identity decomposition + within-firm re-rating drivers."""

# 职责：解释"市值为什么变"= INV-039。① 恒等分解(100%精确):Δln市值 = Δln营收(经营通道) + Δln(PS)(估值再定价);
#       ② 公司内回归:估值再定价(ΔlnPS)由哪些经营指标变化驱动 → 强解释性(样本内 R² + 归因,非预测);
#       ③ 逐家:这些年市值×N倍,经营 vs 估值 各贡献多少、再定价主因是谁。
# 不做什么：不做样本外预测(那是建议层);不做事件因果(analyze_capital_action_cate)。
# 允许依赖层：标准库、numpy/pandas、statsmodels、peer_universe、income_full/daily_basic/fundamental_panel。
# 谁不应该 import：仪表板/建模脚本只读其 JSON。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from peer_universe import load_companies

RAW = Path("market-impact-study/data/raw/tushare")
MAINBZ = RAW / "fina_mainbz"
FUND = Path("market-impact-study/data/processed/modeling/fundamental_panel.csv")
OUT = Path("market-impact-study/data/processed/modeling/cate_14firm/mcap_attribution.json")
OVERSEAS_KW = ("国外", "境外", "海外", "外销", "出口", "亚洲", "欧洲", "美洲", "非洲", "国际", "其他国家", "境内外")
DOMESTIC_KW = ("中国", "大陆", "境内", "国内", "内销")
# 解释再定价(ΔlnPS)的经营指标变化。剔除"营收增速":营收在 Y=ln(市值)−ln(营收) 分母里,会机械造负相关(伪)。
# 净利增速/利润率/ROE/杠杆/研发/海外/周转 都不在 PS 分母,干净。
DRV = {
    "d_gross_margin": "Δ毛利率",
    "d_net_margin": "Δ净利率",
    "d_roe": "ΔROE",
    "f_ni_yoy": "净利增速",
    "d_debt": "Δ资产负债率",
    "d_rd": "Δ研发强度",
    "d_overseas": "Δ海外占比",
    "d_asset_turn": "Δ资产周转",
}


def annual_firm(code: str) -> pd.DataFrame:
    pi = RAW / "income_full" / f"{code}.csv"
    pd_ = RAW / "daily_basic" / f"{code}.csv"
    if not pi.exists() or not pd_.exists():
        return pd.DataFrame()
    inc = pd.read_csv(pi)
    inc.columns = [c.lstrip("﻿") for c in inc.columns]
    inc = inc[(pd.to_numeric(inc["end_date"], errors="coerce") % 10000 == 1231)].copy()
    inc["end_date"] = inc["end_date"].astype(int)
    if "report_type" in inc.columns:
        inc = inc[pd.to_numeric(inc["report_type"], errors="coerce") == 1]
    inc["yr"] = inc["end_date"] // 10000
    inc["rev"] = pd.to_numeric(inc["revenue"], errors="coerce") / 1e8
    inc["ni"] = pd.to_numeric(inc["n_income_attr_p"], errors="coerce") / 1e8
    inc = inc.sort_values(["yr", "end_date"]).groupby("yr").last()[["rev", "ni"]].reset_index()

    db = pd.read_csv(pd_)
    db.columns = [c.lstrip("﻿") for c in db.columns]
    db["trade_date"] = db["trade_date"].astype(int)
    db["yr"] = db["trade_date"] // 10000
    mv = (db.sort_values("trade_date").groupby("yr")["total_mv"].last() / 1e4).reset_index(name="mv")  # 亿

    a = inc.merge(mv, on="yr", how="inner")
    a = a[(a["rev"] > 0) & (a["mv"] > 0)].copy()
    a["ps"] = a["mv"] / a["rev"]  # 市销率(估值倍数,亏损不破)
    a["ts_code"] = code
    return a.sort_values("yr").reset_index(drop=True)


def mainbz_strategic(code: str) -> dict:
    # 战略画像(主营构成 fina_mainbz):海外营收占比/趋势/增速 + 国内增速 + 业务集中度HHI + 战略标签
    p = MAINBZ / f"{code}.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p)
    d.columns = [c.lstrip("﻿") for c in d.columns]
    d["end_date"] = pd.to_numeric(d.get("end_date"), errors="coerce")
    d["bz_sales"] = pd.to_numeric(d.get("bz_sales"), errors="coerce")
    d = d[(d["end_date"] % 10000 == 1231) & d["bz_sales"].notna() & (d["bz_sales"] > 0)].copy()
    if d.empty:
        return {}
    d["item"] = d["bz_item"].astype(str)
    pat_ov, pat_dom = "|".join(OVERSEAS_KW), "|".join(DOMESTIC_KW)
    d["is_ov"] = d["item"].str.contains(pat_ov)
    d["is_dom"] = d["item"].str.contains(pat_dom)
    reg = d[d["is_ov"] | d["is_dom"]]
    out: dict = {}
    if not reg.empty:  # 按地区披露:算海外占比与增速
        periods = sorted(reg["end_date"].unique())
        ov_sh, ov_sales, dom_sales = {}, {}, {}
        for pr in periods:
            sub = reg[reg["end_date"] == pr]
            tot = sub["bz_sales"].sum()
            ov = sub.loc[sub["is_ov"], "bz_sales"].sum()
            ov_sh[pr] = ov / tot * 100 if tot > 0 else np.nan
            ov_sales[pr] = ov
            dom_sales[pr] = sub.loc[sub["is_dom"], "bz_sales"].sum()
        p0, p1 = periods[0], periods[-1]
        yrs = max(1, (p1 - p0) // 10000)
        out["overseas_share"] = round(float(ov_sh[p1]), 0)
        out["overseas_share_chg"] = round(float(ov_sh[p1] - ov_sh[p0]), 0)
        if ov_sales[p0] > 0 and ov_sales[p1] > 0:
            out["overseas_cagr"] = round(((ov_sales[p1] / ov_sales[p0]) ** (1 / yrs) - 1) * 100, 0)
        if dom_sales[p0] > 0 and dom_sales[p1] > 0:
            out["domestic_cagr"] = round(((dom_sales[p1] / dom_sales[p0]) ** (1 / yrs) - 1) * 100, 0)
        sh = out["overseas_share"]
        out["strategy_tag"] = (
            "纯出口型" if sh >= 80 else "出海主导" if sh >= 50 else "内需主导" if sh < 30 else "内外均衡"
        )
    else:  # 按产品披露:算业务集中度(最新一期 HHI / 头部占比)
        last = d[d["end_date"] == d["end_date"].max()]
        sh = (last["bz_sales"] / last["bz_sales"].sum()).to_numpy()
        out["top_seg_share"] = round(float(sh.max()) * 100, 0)
        out["n_segments"] = len(sh)
        out["seg_hhi"] = round(float((sh**2).sum()), 2)
        out["strategy_tag"] = "单一业务" if sh.max() >= 0.7 else "多元业务" if len(sh) >= 4 else "双主业"
    return out


def _fl(s: pd.Series) -> tuple[float, float]:
    # 首/末有效值(看轨迹起点→终点)
    s = s.dropna()
    return (float(s.iloc[0]), float(s.iloc[-1])) if len(s) else (np.nan, np.nan)


def _r(v: float) -> float | None:
    return round(float(v), 1) if v == v else None


def main() -> None:
    names = {c["ts_code"]: c["name"] for c in load_companies()}
    fund = pd.read_csv(FUND)
    fund = fund[fund["end_date"] % 10000 == 1231].copy()
    fund["yr"] = fund["end_date"] // 10000
    parts, per_firm = [], []
    for code in names:
        a = annual_firm(code)
        if len(a) < 3:
            continue
        a["dln_mv"] = np.log(a["mv"]).diff()
        a["dln_rev"] = np.log(a["rev"]).diff()
        a["dln_ps"] = np.log(a["ps"]).diff()  # 恒等:dln_mv = dln_rev + dln_ps
        # 逐家整段乘法分解(首→末年):市值倍数 = 营收倍数 × PS倍数(恒等,精确)
        rev_mult = float(a["rev"].iloc[-1] / a["rev"].iloc[0])
        ps_mult = float(a["ps"].iloc[-1] / a["ps"].iloc[0])
        mcap_mult = float(a["mv"].iloc[-1] / a["mv"].iloc[0])
        years = max(1, int(a["yr"].iloc[-1] - a["yr"].iloc[0]))
        # 接基本面年度,造 Δ 驱动 + 经营轨迹
        fc = fund[fund["ts_code"] == code][
            [
                "yr",
                "f_gross_margin",
                "f_net_margin",
                "f_roe",
                "f_rev_yoy",
                "f_ni_yoy",
                "f_debt_to_assets",
                "f_rd_intensity",
                "f_overseas_share",
                "f_asset_turn",
            ]
        ]
        m = a.merge(fc, on="yr", how="left").sort_values("yr")
        for lvl, dd in [
            ("f_gross_margin", "d_gross_margin"),
            ("f_net_margin", "d_net_margin"),
            ("f_roe", "d_roe"),
            ("f_debt_to_assets", "d_debt"),
            ("f_rd_intensity", "d_rd"),
            ("f_overseas_share", "d_overseas"),
            ("f_asset_turn", "d_asset_turn"),
        ]:
            m[dd] = m[lvl].diff()
        parts.append(m)
        # 逐家经营轨迹(全 13 家老对手都看):营收CAGR、利润率起→终、研发、海外、ROE
        nm0, nm1 = _fl(m["f_net_margin"])
        gm0, gm1 = _fl(m["f_gross_margin"])
        ov0, ov1 = _fl(m["f_overseas_share"])
        per_firm.append(
            {
                "firm": names[code],
                "code": code,
                "y0": int(a["yr"].iloc[0]),
                "y1": int(a["yr"].iloc[-1]),
                "mcap_mult": round(mcap_mult, 2),
                "rev_mult": round(rev_mult, 2),
                "ps_mult": round(ps_mult, 2),
                "driver": "经营" if abs(np.log(max(rev_mult, 1e-6))) >= abs(np.log(max(ps_mult, 1e-6))) else "估值",
                "rev_cagr": round((rev_mult ** (1 / years) - 1) * 100, 1),
                "net_margin0": _r(nm0),
                "net_margin1": _r(nm1),
                "gross_margin1": _r(gm1),
                "rd_mean": _r(m["f_rd_intensity"].mean()),
                "overseas0": _r(ov0),
                "overseas1": _r(ov1),
                "roe_mean": _r(m["f_roe"].mean()),
                **mainbz_strategic(code),  # 战略画像:海外结构/增速/集中度/标签(主营构成)
            }
        )
    panel = pd.concat(parts, ignore_index=True).dropna(subset=["dln_ps"])

    # 公司内回归解释 ΔlnPS(估值再定价):firm FE + 聚类SE,样本内解释性
    cols = list(DRV)
    reg = panel.dropna(subset=[*cols, "dln_ps"]).copy()
    yv = reg["dln_ps"].to_numpy()
    xz = (reg[cols] - reg[cols].mean()) / reg[cols].std(ddof=0)
    firm = reg["ts_code"]
    # 带公司哑变量(FE)
    xfe = pd.concat(
        [xz.reset_index(drop=True), pd.get_dummies(firm.reset_index(drop=True), prefix="f", dtype=float)], axis=1
    )
    ols = sm.OLS(yv, sm.add_constant(xfe)).fit(cov_type="cluster", cov_kwds={"groups": firm})
    r2_fe = float(ols.rsquared)
    # 不带FE(纯Δ驱动解释力)
    ols0 = sm.OLS(yv, sm.add_constant(xz.reset_index(drop=True))).fit(cov_type="cluster", cov_kwds={"groups": firm})
    r2_drv = float(ols0.rsquared)
    drivers = sorted(
        [
            {"feat": DRV[c], "coef": round(float(ols0.params[c]), 3), "p": round(float(ols0.pvalues[c]), 3)}
            for c in cols
        ],
        key=lambda z: -abs(z["coef"]),
    )

    # 干净检验:市值对营收弹性 β(ΔlnMV ~ ΔlnREV + 公司FE),营收只在右边,无机械污染。
    # β vs 1 才是"成长是否被去估值":β<1=市场给成长打折,β≈1=1:1传导,β>1=奖励再定价。
    ed = panel.dropna(subset=["dln_mv", "dln_rev"]).copy()
    xe = pd.concat(
        [
            ed["dln_rev"].reset_index(drop=True),
            pd.get_dummies(ed["ts_code"].reset_index(drop=True), prefix="g", dtype=float),
        ],
        axis=1,
    )
    oe = sm.OLS(ed["dln_mv"].to_numpy(), sm.add_constant(xe)).fit(
        cov_type="cluster", cov_kwds={"groups": ed["ts_code"]}
    )
    beta, bse = float(oe.params["dln_rev"]), float(oe.bse["dln_rev"])
    lo, hi = beta - 1.64 * bse, beta + 1.64 * bse
    # 加年度FE(剔除全行业同步de-rating的时间趋势):β 仍<1 才是真"成长被打折",否则只是时间假象
    xe2 = pd.concat([xe, pd.get_dummies(ed["yr"].reset_index(drop=True), prefix="y", dtype=float)], axis=1)
    oe2 = sm.OLS(ed["dln_mv"].to_numpy(), sm.add_constant(xe2)).fit(
        cov_type="cluster", cov_kwds={"groups": ed["ts_code"]}
    )
    b2, s2 = float(oe2.params["dln_rev"]), float(oe2.bse["dln_rev"])
    lo2, hi2 = b2 - 1.64 * s2, b2 + 1.64 * s2
    elasticity = {
        "beta_firmFE": round(beta, 2),
        "ci90_firmFE": [round(lo, 2), round(hi, 2)],
        "beta_2wayFE": round(b2, 2),
        "ci90_2wayFE": [round(lo2, 2), round(hi2, 2)],
        "verdict": (
            "成长被打折稳健(加年度FE后 β 仍<1)"
            if hi2 < 1
            else "成长打折大部分是时间趋势(年度FE后 β 不再<1)"
            if lo2 <= 1 <= hi2 or lo2 > 1
            else "不定"
        ),
    }

    # 整体:市值变动里经营 vs 估值(按 |Δln| 加权)
    tot_rev = panel["dln_rev"].abs().sum()
    tot_ps = panel["dln_ps"].abs().sum()
    overall = {
        "经营通道占比": round(tot_rev / (tot_rev + tot_ps) * 100, 0),
        "估值通道占比": round(tot_ps / (tot_rev + tot_ps) * 100, 0),
    }

    per_firm.sort(key=lambda z: -z["mcap_mult"])
    yiwei = next((p for p in per_firm if p["code"] == "300590.SZ"), None)

    out = {
        "n_firms": len(per_firm),
        "n_obs": len(reg),
        "decomp_identity": "Δln市值 = Δln营收(经营) + Δln(PS)(估值再定价),恒等分解100%精确",
        "overall_channel": overall,
        "mcap_rev_elasticity": elasticity,  # 干净:市值对营收弹性 β(替代被污染的"成长去估值")
        "rerating_r2_drivers_only": round(r2_drv, 3),
        "rerating_r2_with_firm_fe": round(r2_fe, 3),
        "rerating_drivers": drivers,
        "yiwei": yiwei,
        "per_firm": per_firm,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"市值变动分解:{len(per_firm)}家 | 整体 经营{overall['经营通道占比']}% / 估值{overall['估值通道占比']}%")
    print(f"再定价(ΔlnPS)解释性:纯Δ驱动 R²={r2_drv:.3f} | 加公司FE R²={r2_fe:.3f}")
    print("再定价主驱动:", [(d["feat"], d["coef"], f"p{d['p']}") for d in drivers[:5]])
    print("\n逐家全画像(13 家老对手):市值=营收×倍数 | 营收CAGR | 净利率起→终 | 研发 | 海外起→终 | ROE")
    for p in per_firm:
        print(
            f"  {p['firm']:6s} 市值×{p['mcap_mult']:.1f}=营收×{p['rev_mult']:.1f}×倍数×{p['ps_mult']:.2f} | "
            f"CAGR{p['rev_cagr']}% | 净利{p['net_margin0']}→{p['net_margin1']}% | 研发{p['rd_mean']}% | "
            f"海外{p['overseas0']}→{p['overseas1']}% | ROE{p['roe_mean']}%"
        )
    print(
        f"\n市值对营收弹性:公司FE β={elasticity['beta_firmFE']}{elasticity['ci90_firmFE']} | "
        f"+年度FE β={elasticity['beta_2wayFE']}{elasticity['ci90_2wayFE']} → {elasticity['verdict']}"
    )
    print("\n逐家战略画像(主营构成):")
    for p in per_firm:
        tag = p.get("strategy_tag", "—")
        ovc = p.get("overseas_cagr")
        dmc = p.get("domestic_cagr")
        extra = (
            f"海外占比{p.get('overseas_share', '—')}% 海外增速{ovc}% 国内增速{dmc}%"
            if "overseas_share" in p
            else f"头部业务{p.get('top_seg_share', '—')}% 业务数{p.get('n_segments', '—')}"
        )
        print(f"  {p['firm']:6s} [{tag}] {extra}")
    print("saved ->", OUT)


if __name__ == "__main__":
    main()

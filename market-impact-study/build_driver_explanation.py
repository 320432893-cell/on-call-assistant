"""Contamination-aware explanation layer: counterfactual what-if + dependence shapes + per-firm narrative + re-rating triggers."""

# 职责：把"什么驱动估值"从静态归因升级为可读、可操作的解释层 = INV-044。回应"解释层不够 + 解释要带污染意识"。
#   ① 反事实/可操作:只在【干净+三角验证过+CFO可动】的杠杆上,用已训 GBT 模拟"调到同行中位/最优档→超额估值变多少"
#      (估值水平层);市值层用已验证弹性 β≈0.58 模拟"营收增速调到赢家档→市值倍数"(成长被打折,诚实折算)。
#   ② 依赖形状:对干净杠杆画 partial dependence 曲线 + 每家落点(看低杠杆在什么区间被奖励、移为在哪)。
#   ③ 逐家自然语言:从严谨归因瀑布 + 分组判定 + 污染标签生成每家"为什么贵/便宜",可信部分与算术污染分开讲。
#   ④ 再定价触发:把 ΔlnPS 的驱动按干净/污染拆开,只把干净触发当真信号。
# 不做什么：不重训/不重调参(复用 build_valuation_model 的部署参数与面板);不在污染特征上做反事实(算术假象,明确拒绝)；不下因果断言(关联级,GBT 反事实=ceteris paribus 模型隐含)。
# 允许依赖层：标准库、numpy/pandas、build_valuation_model(复用面板/模型);读 valuation_model/attribution_rigorous/mcap_attribution/drivers_triangulation JSON。
# 谁不应该 import：仪表板/其它建模脚本只读其 JSON。
from __future__ import annotations

import json
import math
from pathlib import Path

import build_mcap_attribution as M  # noqa: N812
import build_valuation_model as V  # noqa: N812
import numpy as np
import pandas as pd

C = Path("market-impact-study/data/processed/modeling/cate_14firm")
OUT = C / "driver_explanation.json"

# CFO 可动的资产负债表结构杠杆(干净公式、非反向因果的流动性/筹码);主验证杠杆 = 资产负债率(H2 5/5 + FE真)
ACTIONABLE = {
    "f_debt_to_assets",
    "f_current_ratio",
    "f_equity_mult",
    "f_debt_to_eqt",
    "f_quick_ratio",
    "f_cash_ratio",
    "f_cash_to_assets",
}
PRIMARY = "f_debt_to_assets"


def _load() -> tuple[dict, dict, dict, dict]:
    val = json.loads((C / "valuation_model.json").read_text(encoding="utf-8"))
    rig = json.loads((C / "attribution_rigorous.json").read_text(encoding="utf-8"))
    mc = json.loads((C / "mcap_attribution.json").read_text(encoding="utf-8"))
    tri = json.loads((C / "drivers_triangulation.json").read_text(encoding="utf-8"))
    return val, rig, mc, tri


def _predict(gbt, cols: list[str], row: pd.Series) -> float:
    return float(gbt.predict(pd.DataFrame([row], columns=cols))[0])


def counterfactual_level(df, x, gbt, cols, contam) -> dict:
    # 估值水平层反事实:只在干净+可动杠杆上,把该公司均值行的单个杠杆调到 {同行中位, 同行最优档},预测超额估值变化。
    firms = {}
    for code in df["ts_code"].unique():
        m = (df["ts_code"] == code).to_numpy()
        base = x[m].mean(axis=0)
        base_pred = _predict(gbt, cols, base)
        levers = []
        for k in cols:
            if k not in ACTIONABLE or contam.get(V.DRIVERS[k][0]) != "干净":
                continue
            dirn = V.DRIVERS[k][1]
            med = float(x[k].median())
            best = float(x[k].quantile(0.9 if dirn > 0 else 0.1)) if dirn else med
            scen = []
            for tname, tv in (("同行中位", med), ("同行最优档", best)):
                r = base.copy()
                r[k] = tv
                scen.append(
                    {"target": tname, "to": round(tv, 3), "d_excess": round(_predict(gbt, cols, r) - base_pred, 3)}
                )
            levers.append(
                {
                    "lever": V.DRIVERS[k][0],
                    "current": round(float(base[k]), 3),
                    "dir": dirn,
                    "verified": k == PRIMARY,
                    "scenarios": scen,
                }
            )
        firms[df.loc[m, "firm"].iloc[0]] = {"base_excess": round(base_pred, 3), "levers": levers}
    return {
        "note": "只对【干净公式 + 可调整】杠杆做反事实;杠杆=资产负债率经三角验证 H2 5/5。其余含营收/含市值特征=算术假象,拒绝模拟(见 refused)。这是 ceteris paribus 模型隐含,关联级非因果。",
        "by_firm": firms,
    }


def counterfactual_mcap(mc) -> dict:
    # 市值层反事实:移为营收增速调到同行赢家/中位档,按已验证弹性 β(成长被打折<1)折算市值倍数。
    beta = mc["mcap_rev_elasticity"]["beta_2wayFE"]
    peers = [p for p in mc["per_firm"] if p["code"] != V.YIWEI and p.get("rev_cagr") is not None]
    yw = next(p for p in mc["per_firm"] if p["code"] == V.YIWEI)
    yrs = yw["y1"] - yw["y0"]
    cagrs = sorted(p["rev_cagr"] for p in peers)
    winner = float(np.median([c for c in cagrs if c >= np.quantile(cagrs, 0.75)]))
    median_c = float(np.median(cagrs))
    rev_act, mcap_act = yw["rev_mult"], yw["mcap_mult"]
    scen = []
    for tname, g in (("同行赢家档", winner), ("同行中位档", median_c), ("移为实际", yw["rev_cagr"])):
        rev_cf = (1 + g / 100) ** yrs
        mcap_cf = mcap_act * math.exp(beta * (math.log(rev_cf) - math.log(rev_act)))
        scen.append(
            {"scenario": tname, "rev_cagr": round(g, 1), "rev_mult": round(rev_cf, 2), "mcap_mult": round(mcap_cf, 2)}
        )
    return {
        "note": f"市值层唯一已验证可操作引擎=营收成长(H1 成长被打折 5/5,弹性 β={beta}<1 已折算)。移为实际 CAGR {yw['rev_cagr']}%、市值×{mcap_act};若做到赢家档,市值倍数见下(已按 β 打折,非线性外推)。",
        "beta": beta,
        "years": yrs,
        "scenarios": scen,
    }


def dependence(x, gbt, cols, df, y) -> dict:
    # 干净杠杆的 partial dependence 曲线 + 每家落点(自身均值杠杆 vs 自身均值超额估值)。
    out = {}
    base = x.median()
    for k in cols:
        if k not in ACTIONABLE or k != PRIMARY:  # 只对主验证杠杆画(其余干净杠杆可扩,默认精简)
            continue
        grid = np.quantile(x[k].to_numpy(), np.linspace(0.05, 0.95, 12))
        curve = []
        for v in grid:
            r = base.copy()
            r[k] = float(v)
            curve.append({"x": round(float(v), 3), "y": round(_predict(gbt, cols, r), 3)})
        pos = []
        for code in df["ts_code"].unique():
            m = (df["ts_code"] == code).to_numpy()
            pos.append(
                {
                    "firm": df.loc[m, "firm"].iloc[0],
                    "is_yiwei": code == V.YIWEI,
                    "x": round(float(x[m][k].mean()), 3),
                    "y": round(float(y[m].mean()), 3),
                }
            )
        out[V.DRIVERS[k][0]] = {
            "curve": curve,
            "firms": pos,
            "note": "曲线=其它特征固定在中位、只动该杠杆的模型隐含响应(单调约束→低杠杆段更高估值);点=各家真实落点。关联级。",
        }
    return out


def firm_narratives(rig) -> list[dict]:
    # 逐家自然语言:可信组(干净+稳)与污染组分开讲,污染明确标注不作真驱动。
    gv = rig["group_verdict"]
    out = []
    for wf in rig["firm_waterfall"]:
        groups = wf["groups"]
        excess = wf["excess_actual"]
        trust = sorted(
            [(g, v) for g, v in groups.items() if "可信关联" in gv.get(g, {}).get("verdict", "")],
            key=lambda z: -abs(z[1]),
        )
        contam = sorted(
            [(g, v) for g, v in groups.items() if "污染" in gv.get(g, {}).get("verdict", "") and abs(v) >= 0.05],
            key=lambda z: -abs(z[1]),
        )
        side = "溢价" if excess > 0 else "折让"
        parts = [f"{wf['firm']}超额估值{excess:+.2f}({side})。"]
        if trust:
            parts.append(
                "能信的部分:"
                + "、".join(f"{g}{v:+.2f}" for g, v in trust)
                + "(干净公式 + 公司层自助稳 + 三角验证,但仍是关联非因果)。"
            )
        else:
            parts.append("无可信组主导(干净组贡献都很小)。")
        if contam:
            parts.append(
                "⚠️ 名义贡献里 "
                + "、".join(f"{g}{v:+.2f}" for g, v in contam[:2])
                + " 含营收/市值算术成分(盈利类 H3 已证伪),不作真驱动看。"
            )
        out.append(
            {
                "firm": wf["firm"],
                "code": wf["code"],
                "excess": excess,
                "text": "".join(parts),
                "trust": [[g, round(v, 3)] for g, v in trust],
                "contaminated": [[g, round(v, 3)] for g, v in contam[:3]],
            }
        )
    return sorted(out, key=lambda z: -z["excess"])


def rerating_triggers(mc, contam) -> dict:
    # 把已算的 ΔlnPS 再定价驱动按干净/污染拆开:只把干净触发当真信号。
    norm = {
        "资产周转": "资产周转率",
        "海外占比": "海外收入占比",
        "净利增速": "净利同比",
        "资产负债率": "资产负债率",
        "毛利率": "毛利率",
        "研发强度": "研发强度",
        "ROE": "ROE",
        "净利率": "净利率",
    }
    clean, dirty = [], []
    for d in mc["rerating_drivers"]:
        base = d["feat"].lstrip("Δ")
        tag = contam.get(norm.get(base, base), "未知")
        rec = {"feat": d["feat"], "coef": d["coef"], "p": d["p"], "contam": tag, "sig": d["p"] < 0.10}
        (clean if tag == "干净" else dirty).append(rec)
    sig_clean = [r for r in clean if r["sig"]]
    return {
        "r2_with_fe": mc["rerating_r2_with_firm_fe"],
        "clean_triggers": sorted(clean, key=lambda z: -abs(z["coef"])),
        "contaminated_triggers": sorted(dirty, key=lambda z: -abs(z["coef"])),
        "note": f"再定价(ΔlnPS)整体可解释 R²={mc['rerating_r2_with_firm_fe']}(其余是情绪/叙事)。干净触发里显著的:{'、'.join(r['feat'] for r in sig_clean) or '无'};名义最强的 Δ资产周转/Δ毛利率含营收(PS 分母里就有营收→机械),不算真触发。",
    }


def per_firm_analysis(mc: dict) -> dict:
    # A1:把"移为独享"的 ① 市值反事实(营收成长→市值,β折算)② 时序通道路径(逐年 ln(x_t/x_0))扩到全 13 家;次新股(年数<6)标 caveat。
    beta = mc["mcap_rev_elasticity"]["beta_2wayFE"]
    cagrs = sorted(p["rev_cagr"] for p in mc["per_firm"] if p.get("rev_cagr") is not None)
    winner = float(np.median([c for c in cagrs if c >= np.quantile(cagrs, 0.75)]))
    median_c = float(np.median(cagrs))
    firms = []
    for p in mc["per_firm"]:
        code = p["code"]
        yrs = p["y1"] - p["y0"]
        rev_act, mcap_act = p.get("rev_mult"), p.get("mcap_mult")
        cf = {}
        if rev_act and mcap_act and rev_act > 0 and mcap_act > 0 and yrs > 0:
            for tname, g in (("赢家档", winner), ("中位档", median_c)):
                rev_cf = (1 + g / 100) ** yrs
                cf[tname] = round(mcap_act * math.exp(beta * (math.log(rev_cf) - math.log(rev_act))), 2)
        a = M.annual_firm(code).sort_values("yr").reset_index(drop=True)
        path = []
        if len(a) >= 3:
            r0, ps0, m0 = a["rev"].iloc[0], a["ps"].iloc[0], a["mv"].iloc[0]
            for _, row in a.iterrows():
                path.append(
                    {
                        "yr": int(row["yr"]),
                        "cum_rev": round(float(math.log(row["rev"] / r0)), 3),
                        "cum_ps": round(float(math.log(row["ps"] / ps0)), 3),
                        "cum_mv": round(float(math.log(row["mv"] / m0)), 3),
                    }
                )
        n = len(a)
        firms.append(
            {
                "firm": p["firm"],
                "code": code,
                "is_yiwei": code == V.YIWEI,
                "actual_cagr": p.get("rev_cagr"),
                "mcap_mult": mcap_act,
                "rev_mult": rev_act,
                "ps_mult": p.get("ps_mult"),
                "channel": p.get("driver"),
                "cf_mcap": cf,
                "n_years": n,
                "short_history": n < 6,
                "path": path,
            }
        )
    return {
        "note": "全 13 家:① 逐年通道路径(累积 ln 分解,营收 vs 估值)=稳健逐家产物;② 市值反事实(若营收做到赢家/中位档→市值,按已验证 β 折算)。"
        "⚠️ 反事实诚实边界:对移为(焦点公司、11年)最有意义;长历史公司(高新兴16年等)按赢家CAGR复利会机械放大到不现实(看相对方向、不看绝对值);次新股(年数<6)short_history=true,路径/反事实都仅供参考。",
        "benchmarks": {"beta": beta, "winner_cagr": round(winner, 1), "median_cagr": round(median_c, 1)},
        "firms": sorted(firms, key=lambda z: -(z["mcap_mult"] or 0)),
    }


def main() -> None:
    val, rig, mc, tri = _load()
    contam = rig["feature_contamination_tags"]
    params = val["gbt_params"]

    df = V.build_panel()
    cols_all = list(V.DRIVERS)
    for c in cols_all:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ps"]).reset_index(drop=True)
    med = df[cols_all].median()
    x_full = df[cols_all].fillna(med).fillna(0.0)
    y = V.excess_valuation(df)
    groups = df["ts_code"]
    cols = V.select_features(x_full, y, groups, cols_all)
    x = x_full[cols]
    gbt = V.fit_gbt(x, y, cols, params)

    refused = sorted(
        {V.DRIVERS[k][0]: contam.get(V.DRIVERS[k][0]) for k in cols if contam.get(V.DRIVERS[k][0]) != "干净"}.items()
    )
    out = {
        "guardrail": {
            "principle": "解释只用【干净公式 + 三角验证过】的驱动;含营收(在 Y=ln(PS) 分母里)/含市值的特征=算术假象,拒绝做反事实与因果话术。",
            "verified_hard": {"H1": tri["H1"]["verdict"], "H2": tri["H2"]["verdict"], "H3": tri["H3"]["verdict"]},
            "clean_passed_lever": "资产负债率(杠杆,H2 5/5 + 定义级干净 + 公司内FE真驱动)",
            "refused_levers": [{"feat": f, "reason": t} for f, t in refused],
        },
        "counterfactual_level": counterfactual_level(df, x, gbt, cols, contam),
        "counterfactual_mcap": counterfactual_mcap(mc),
        "per_firm_analysis": per_firm_analysis(mc),
        "dependence": dependence(x, gbt, cols, df, y),
        "firm_narratives": firm_narratives(rig),
        "rerating_triggers": rerating_triggers(mc, contam),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved -> {OUT}")
    print("拒绝模拟的污染杠杆:", [f for f, _ in refused])
    yw = out["counterfactual_level"]["by_firm"].get("移为通信", {})
    print("移为 base_excess:", yw.get("base_excess"), "| 可动干净杠杆:", [lv["lever"] for lv in yw.get("levers", [])])
    for s in out["counterfactual_mcap"]["scenarios"]:
        print(f"  市值反事实 {s['scenario']}: CAGR {s['rev_cagr']}% → 市值×{s['mcap_mult']}")
    print("干净再定价触发:", [r["feat"] for r in out["rerating_triggers"]["clean_triggers"] if r["sig"]])


if __name__ == "__main__":
    main()

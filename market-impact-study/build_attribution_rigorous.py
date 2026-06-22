"""Rigorous attribution: contamination audit + group interventional SHAP + firm-bootstrap stability + closed waterfall."""

# 职责：把"什么驱动估值"的归因做到严谨 = INV-040。回应"归因糊弄 / 每个结论的上下游污染依赖都必须严谨测试":
#   ① 定义级污染标记:看特征公式里有没有 Y=ln(市值/营收) 的构造成分(含营收/含市值/干净)。
#      不用回归控 ln市值+ln营收——那等于控住结果 ln(PS),会把所有特征都打成污染(循环,无效)。
#   ② 分组 interventional SHAP(传背景集,非 tree_path_dependent 条件口径):组内共线随机摊credit无妨,
#      组间归因稳定。③ 公司层自助:重抽公司重算分组重要性 → CI + top3 稳定性(N=14 必须自助)。
#   ④ 逐家闭合瀑布:分组 SHAP 求和闭合到该公司超额估值(对账,不截断 top2)。
#   综合判定:可信关联 = 定义级干净 + 自助稳(top3≥0.5);否则标含污染/不稳。
# 不做什么：不重调超参(复用 build_valuation_model.auto_params);不做因果断言(关联级)。
# 允许依赖层：标准库、numpy/pandas、shap、build_valuation_model(复用面板/模型)。
# 谁不应该 import：仪表板/其它建模脚本只读其 JSON。
from __future__ import annotations

import json
from pathlib import Path

import build_valuation_model as V
import numpy as np
import pandas as pd
import shap

OUT = Path("market-impact-study/data/processed/modeling/cate_14firm/attribution_rigorous.json")
RNG = V.RNG
N_BOOT = 50
# 概念分组:组内高度共线(SHAP 组内随机摊 credit 无所谓),组间归因才稳定可信
GROUPS = {
    "盈利能力": ["f_net_margin", "f_gross_margin", "f_op_margin", "f_roe", "f_roa", "f_roic", "f_roe_dt"],
    "现金流质量": ["f_ocf_to_rev", "f_fcf_to_rev", "f_cash_to_assets", "f_cash_ratio", "f_ocf_yoy"],
    "运营效率": ["f_asset_turn", "f_ar_turn", "f_fa_turn"],
    "杠杆/流动性": ["f_debt_to_assets", "f_equity_mult", "f_debt_to_eqt", "f_current_ratio", "f_quick_ratio"],
    "成长": ["f_rev_yoy", "f_ni_yoy", "f_rev_cagr3", "f_dt_ni_yoy", "d_net_margin", "d_gross_margin"],
    "费用/研发": ["f_rd_intensity", "f_saleexp_ratio", "f_adminexp_ratio", "f_finaexp_ratio"],
    "海外": ["f_overseas_share"],
    "市场流动性/筹码": ["liq_turn", "liq_volratio", "liq_amplitude", "liq_amihud", "chip_holder_yoy"],
    "所有权/情绪": ["nf_north_ratio", "nf_north_chg", "nf_margin_ratio", "nf_margin_chg", "nf_inst_top10", "nf_mf_net"],
}


# 定义级污染标记:看特征公式里有没有 Y=ln(市值/营收) 的构造成分。比回归测试可靠(回归控营收=控了结果,循环)。
# 含营收=与 PS 分母机械相关;含市值=与 PS 分子机械相关;干净=公式里无市值无营收(资产/净资产/净利等)。
CONTAM = {
    # 含营收(x/营收 或 营收/x):利润率类、周转类、费用率、成长率、营收型现金流
    "f_net_margin": "含营收",
    "f_gross_margin": "含营收",
    "f_op_margin": "含营收",
    "f_asset_turn": "含营收",
    "f_rev_yoy": "含营收",
    "f_rev_cagr3": "含营收",
    "f_ocf_to_rev": "含营收",
    "f_fcf_to_rev": "含营收",
    "f_rd_intensity": "含营收",
    "f_ar_turn": "含营收",
    "f_fa_turn": "含营收",
    "f_saleexp_ratio": "含营收",
    "f_adminexp_ratio": "含营收",
    "f_finaexp_ratio": "含营收",
    "d_net_margin": "含营收",
    "d_gross_margin": "含营收",
    # 含市值(x/市值 或 价量∝市值)
    "liq_amihud": "含市值",
    "nf_margin_ratio": "含市值",
    "nf_margin_chg": "含市值",
    "nf_mf_net": "含市值",
    # 干净(公式里无市值无营收)
    "f_roe": "干净",
    "f_roa": "干净",
    "f_roic": "干净",
    "f_roe_dt": "干净",
    "f_ni_yoy": "干净",
    "f_dt_ni_yoy": "干净",
    "f_ocf_yoy": "干净",
    "f_cash_to_assets": "干净",
    "f_debt_to_assets": "干净",
    "f_current_ratio": "干净",
    "f_quick_ratio": "干净",
    "f_cash_ratio": "干净",
    "f_equity_mult": "干净",
    "f_debt_to_eqt": "干净",
    "f_overseas_share": "干净",
    "chip_holder_yoy": "干净",
    "nf_north_ratio": "干净",
    "nf_north_chg": "干净",
    "nf_inst_top10": "干净",
    "liq_turn": "干净",
    "liq_volratio": "干净",
    "liq_amplitude": "干净",  # 机械干净,但市场侧=反向因果(另注)
}


def _z(a: np.ndarray) -> np.ndarray:
    s = np.nanstd(a)
    return (a - np.nanmean(a)) / (s if s > 1e-9 else 1.0)


def prep() -> tuple:
    df = V.build_panel()
    cols = list(V.DRIVERS)
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ps"]).reset_index(drop=True)
    x = df[cols].fillna(df[cols].median()).fillna(0.0)
    y = V.excess_valuation(df)
    log_mv = df["log_mv"].to_numpy()
    log_rev = log_mv - np.log(df["ps"].clip(lower=0.05).to_numpy())  # ln营收 = ln市值 − ln(PS)
    return df, cols, x, y, log_mv, log_rev


def group_cleanliness() -> dict:
    # 逐组:成员里干净/含营收/含市值各几个 → 组是否"定义级干净"(机械可信的前提)
    out = {}
    for g, feats in GROUPS.items():
        tags = [CONTAM.get(f, "未标") for f in feats]
        n = len(tags)
        clean = tags.count("干净")
        out[g] = {
            "n": n,
            "干净": clean,
            "含营收": tags.count("含营收"),
            "含市值": tags.count("含市值"),
            "clean_frac": round(clean / n, 2),
            "定义级": "干净" if clean == n else "部分污染" if clean > 0 else "全污染",
        }
    return out


def group_shap(gbt, x: pd.DataFrame, cols: list) -> tuple[np.ndarray, dict, float]:
    bg = shap.sample(x, min(100, len(x)), random_state=RNG)
    expl = shap.TreeExplainer(gbt, data=bg, feature_perturbation="interventional")
    sv = np.array(expl.shap_values(x, check_additivity=False))
    base = float(np.ravel(expl.expected_value)[0])
    gi = {}
    for g, feats in GROUPS.items():
        idx = [cols.index(f) for f in feats if f in cols]
        if idx:
            gi[g] = float(np.abs(sv[:, idx].sum(axis=1)).mean())  # 组内求和(组间稳定)
    return sv, gi, base


def bootstrap_groups(df: pd.DataFrame, cols: list, x: pd.DataFrame, y: np.ndarray, params: dict) -> dict:
    firms = df["ts_code"].unique()
    fidx = {c: np.where(df["ts_code"].to_numpy() == c)[0] for c in firms}
    rng = np.random.RandomState(RNG)
    glist = list(GROUPS)
    draws, top3 = [], dict.fromkeys(glist, 0)
    for _ in range(N_BOOT):
        pick = rng.choice(firms, len(firms), replace=True)
        idx = np.concatenate([fidx[c] for c in pick])
        gb = V.fit_gbt(x.iloc[idx], y[idx], cols, params)
        _, gi, _ = group_shap(gb, x.iloc[idx], cols)
        draws.append(gi)
        for g in sorted(glist, key=lambda z: -gi.get(z, 0))[:3]:
            top3[g] += 1
    out = {}
    for g in glist:
        vals = [d.get(g, 0.0) for d in draws]
        out[g] = {
            "mean": round(float(np.mean(vals)), 3),
            "ci90": [round(float(np.percentile(vals, 5)), 3), round(float(np.percentile(vals, 95)), 3)],
            "top3_freq": round(top3[g] / N_BOOT, 2),
        }
    return out


def firm_waterfall(df: pd.DataFrame, sv: np.ndarray, cols: list, y: np.ndarray, base: float) -> list:
    rows = []
    for code in df["ts_code"].unique():
        mask = (df["ts_code"] == code).to_numpy()
        gs = {}
        for g, feats in GROUPS.items():
            idx = [cols.index(f) for f in feats if f in cols]
            if idx:
                gs[g] = round(float(sv[mask][:, idx].sum(axis=1).mean()), 3)
        recon = base + sum(gs.values())  # 闭合:基线 + 各组贡献 = 模型对该公司的超额估值预测
        rows.append(
            {
                "firm": df.loc[mask, "firm"].iloc[0],
                "code": code,
                "excess_actual": round(float(y[mask].mean()), 3),
                "recon_pred": round(recon, 3),
                "groups": dict(sorted(gs.items(), key=lambda kv: -abs(kv[1]))),
            }
        )
    return sorted(rows, key=lambda r: -r["excess_actual"])


def main() -> None:
    df, cols, x, y, _lmv, _lrev = prep()
    params = V.auto_params(x, y, df["ts_code"], cols)
    gbt = V.fit_gbt(x, y, cols, params)
    sv, gi, base = group_shap(gbt, x, cols)
    clean = group_cleanliness()
    boot = bootstrap_groups(df, cols, x, y, params)
    wf = firm_waterfall(df, sv, cols, y, base)

    # 综合判定:可信关联 = 定义级干净 + 自助稳(top3≥0.5);含污染/不稳 各自标出
    REVERSE = {"市场流动性/筹码"}  # 机械干净但反向因果(高估值→高关注),非可操作
    verdict = {}
    for g in GROUPS:
        st = boot[g]["top3_freq"] >= 0.5
        cl = clean[g]["定义级"] == "干净"
        if not cl:
            v = f"含机械污染({clean[g]['定义级']})"
        elif not st:
            v = "弱/自助不稳"
        elif g in REVERSE:
            v = "稳但反向因果(非可操作)"
        else:
            v = "可信关联(干净+稳;但仍非因果)"
        verdict[g] = {
            "importance": round(gi.get(g, 0), 3),
            "top3_freq": boot[g]["top3_freq"],
            "定义级": clean[g]["定义级"],
            "verdict": v,
        }

    gi_sorted = sorted(gi.items(), key=lambda kv: -kv[1])
    out = {
        "n_obs": len(df),
        "base_value": round(base, 3),
        "group_importance_interventional": {g: round(v, 3) for g, v in gi_sorted},
        "group_bootstrap_stability": boot,
        "group_cleanliness_definitional": clean,
        "group_verdict": verdict,
        "feature_contamination_tags": {V.DRIVERS[c][0]: CONTAM.get(c, "未标") for c in cols},
        "firm_waterfall": wf,
        "method": "interventional SHAP(背景集)+概念分组(组间稳定)+公司层自助+定义级污染标记(看公式含营收/市值)",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== 分组综合判定(重要性 | top3稳定 | 定义级 | 结论)===")
    for g, vd in sorted(verdict.items(), key=lambda kv: -kv[1]["importance"]):
        print(f"  {g:14s} {vd['importance']:.3f} | top3 {vd['top3_freq']:.2f} | {vd['定义级']:5s} | {vd['verdict']}")
    print("saved ->", OUT)


if __name__ == "__main__":
    main()

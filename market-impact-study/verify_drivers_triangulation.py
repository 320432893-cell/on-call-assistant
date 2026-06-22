"""Triangulated verification of value/mcap drivers: wild cluster bootstrap + permutation + spec curve + ID + placebo + LOFO."""

# 职责：把"驱动结论"用多种探不同失效模式的独立方法交叉验证 = INV-041(回应"只用一种方法不够/野=wild cluster bootstrap")。
#   每个预登记假设过 5 类:① 推断 = 手写 wild cluster bootstrap(Rademacher+null-imposed,N=14少簇唯一正确)+ 置换;
#   ② 设定曲线(多设定符号/显著一致率);③ 识别(公司内FE + 领先-滞后查反向因果);④ 安慰剂(打乱→应失效);
#   ⑤ 留一家。综合 consilience 判定(过几关)。只测预登记的 3 条假设,不 42 特征捞鱼。
# 不做什么：不做因果断言(关联级);SHAP/分组仅描述,不当推断。
# 允许依赖层：标准库、numpy/pandas、build_valuation_model(水平面板)、build_mcap_attribution(变动面板)。
# 谁不应该 import：仪表板/其它脚本只读其 JSON。
from __future__ import annotations

import json
from pathlib import Path

import build_mcap_attribution as MC  # noqa: N812 - 模块别名
import build_valuation_model as VL  # noqa: N812 - 模块别名
import numpy as np
import pandas as pd

OUT = Path("market-impact-study/data/processed/modeling/cate_14firm/drivers_triangulation.json")
RNG = 0
B = 599


# ---------- 手写统计引擎 ----------
def ols_cluster(x: np.ndarray, y: np.ndarray, g: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # OLS + CR1 公司层聚类稳健 SE
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ y
    u = y - x @ beta
    n, k = x.shape
    gids = np.unique(g)
    meat = np.zeros((k, k))
    for gg in gids:
        m = g == gg
        s = x[m].T @ u[m]
        meat += np.outer(s, s)
    c = (len(gids) / (len(gids) - 1)) * ((n - 1) / max(n - k, 1))
    v = xtx_inv @ meat @ xtx_inv * c
    return beta, np.sqrt(np.maximum(np.diag(v), 1e-12)), u


def wild_cluster_boot(x: np.ndarray, y: np.ndarray, g: np.ndarray, k: int, null: float) -> tuple[float, float, float]:
    # restricted(null-imposed)wild cluster bootstrap-t,Rademacher 权重(少簇正确推断)
    beta, se, _ = ols_cluster(x, y, g)
    t = (beta[k] - null) / se[k]
    others = [j for j in range(x.shape[1]) if j != k]
    xo, yr = x[:, others], y - null * x[:, k]
    br, _, ur = ols_cluster(xo, yr, g)
    fit_r = xo @ br
    gids = np.unique(g)
    rng = np.random.RandomState(RNG)
    tstar = np.empty(B)
    for b in range(B):
        v = dict(zip(gids, np.where(rng.rand(len(gids)) < 0.5, 1.0, -1.0), strict=False))
        vv = np.array([v[c] for c in g])
        ystar = null * x[:, k] + fit_r + vv * ur
        bb, sb, _ = ols_cluster(x, ystar, g)
        tstar[b] = (bb[k] - null) / sb[k]
    p = (np.sum(np.abs(tstar) >= abs(t)) + 1) / (B + 1)
    return float(beta[k]), float(t), float(p)


def perm_test(x: np.ndarray, y: np.ndarray, g: np.ndarray, k: int) -> float:
    # 置换检验(打乱关键回归元,测 β_k=0 的零分布)= 第二种独立推断
    beta, _, _ = ols_cluster(x, y, g)
    rng = np.random.RandomState(RNG)
    null = np.empty(B)
    for b in range(B):
        xp = x.copy()
        xp[:, k] = rng.permutation(x[:, k])
        null[b] = ols_cluster(xp, y, g)[0][k]
    return float((np.sum(np.abs(null) >= abs(beta[k])) + 1) / (B + 1))


def placebo_test(x: np.ndarray, y: np.ndarray, g: np.ndarray, k: int) -> float:
    # 安慰剂:把关键回归元按公司整体打乱(破坏真链接),效应应消失 → 返回"安慰剂下 |β| ≥ 实测"的比例(应高)
    beta, _, _ = ols_cluster(x, y, g)
    gids = np.unique(g)
    rng = np.random.RandomState(RNG + 1)
    hit = 0
    for _ in range(B):
        perm_g = dict(zip(gids, rng.permutation(gids), strict=False))
        # 用打乱后公司的该特征均值替换(破坏公司-特征对应)
        xb = x.copy()
        col = x[:, k].copy()
        gmean = {gg: col[g == gg].mean() for gg in gids}
        xb[:, k] = np.array([gmean[perm_g[c]] for c in g])
        if abs(ols_cluster(xb, y, g)[0][k]) >= abs(beta[k]):
            hit += 1
    return float((hit + 1) / (B + 1))


def _z(a: np.ndarray) -> np.ndarray:
    s = a.std()
    return (a - a.mean()) / (s if s > 1e-9 else 1.0)


def _fe(*cats: np.ndarray) -> np.ndarray:
    # 拼固定效应哑变量(去一列防共线),返回设计矩阵块
    blocks = []
    for c in cats:
        d = pd.get_dummies(c, drop_first=True, dtype=float).to_numpy()
        blocks.append(d)
    return np.column_stack(blocks) if blocks else np.empty((len(cats[0]), 0))


# ---------- 面板 ----------
def change_panel() -> pd.DataFrame:
    rows = []
    for code in [c["ts_code"] for c in VL.load_companies()]:
        a = MC.annual_firm(code)
        if len(a) < 3:
            continue
        a = a.sort_values("yr")
        a["dln_mv"] = np.log(a["mv"]).diff()
        a["dln_rev"] = np.log(a["rev"]).diff()
        a["ts_code"] = code
        rows.append(a.dropna(subset=["dln_mv", "dln_rev"])[["ts_code", "yr", "dln_mv", "dln_rev"]])
    return pd.concat(rows, ignore_index=True)


def level_panel() -> pd.DataFrame:
    df = VL.build_panel()
    df = df.dropna(subset=["ps"]).reset_index(drop=True)
    df["Y"] = VL.excess_valuation(df)
    df["year"] = df["end_date"] // 10000
    df["log_rev"] = df["log_mv"].to_numpy() - np.log(df["ps"].clip(lower=0.05).to_numpy())
    return df


def consilience(passes: dict) -> str:
    n = sum(bool(v) for v in passes.values())
    fails = [k for k, v in passes.items() if not v]
    tag = "可信(5/5)" if n == 5 else f"稳健({n}/5)" if n == 4 else f"存疑({n}/5)"
    return tag + ("" if not fails else " 未过:" + "/".join(fails))


def _lofo_sign(x: np.ndarray, y: np.ndarray, g: np.ndarray, k: int) -> float:
    signs = []
    for c in np.unique(g):
        m = g != c
        if m.sum() > x.shape[1] + 5:
            signs.append(np.sign(ols_cluster(x[m], y[m], g[m])[0][k]))
    s0 = np.sign(ols_cluster(x, y, g)[0][k])
    return float(np.mean([s == s0 for s in signs])) if signs else 0.0


def run_H1(cp: pd.DataFrame) -> dict:  # noqa: N802 - 假设编号
    # H1 成长被打折:dln(PS) ~ dln(营收) 斜率<0 = 营收涨、倍数压缩。null=0(干净:营收只在右边)
    cp = cp.copy()
    cp["dln_ps"] = cp["dln_mv"] - cp["dln_rev"]
    y, g = cp["dln_ps"].to_numpy(), cp["ts_code"].to_numpy()
    xr = _z(cp["dln_rev"].to_numpy())
    twoway = np.column_stack([np.ones(len(y)), xr, _fe(g, cp["yr"].to_numpy())])
    beta, _t, p_wcb = wild_cluster_boot(twoway, y, g, 1, 0.0)
    p_perm = perm_test(twoway, y, g, 1)
    p_plac = placebo_test(twoway, y, g, 1)
    # 设定曲线:±各FE、winsorize、去最大公司
    yw = np.clip(y, np.percentile(y, 5), np.percentile(y, 95))
    specs = {
        "双向FE": twoway,
        "仅公司FE": np.column_stack([np.ones(len(y)), xr, _fe(g)]),
        "仅年度FE": np.column_stack([np.ones(len(y)), xr, _fe(cp["yr"].to_numpy())]),
        "无FE": np.column_stack([np.ones(len(y)), xr]),
    }
    sgn = [np.sign(ols_cluster(X, y, g)[0][1]) for X in specs.values()]
    sgn.append(np.sign(ols_cluster(twoway, yw, g)[0][1]))  # winsorize
    sign_consist = float(np.mean([s < 0 for s in sgn]))
    b_firm = ols_cluster(specs["仅公司FE"], y, g)[0][1]  # 公司内
    ident = bool(beta < 0 and b_firm < 0)  # 去年度趋势(公司内)仍<0
    lofo = _lofo_sign(twoway, y, g, 1)
    passes = {
        "推断": p_wcb < 0.10 and p_perm < 0.10 and beta < 0,
        "设定": sign_consist >= 0.8,
        "识别": ident,
        "证伪": p_plac < 0.10,
        "泛化": lofo >= 0.85,
    }
    return {
        "name": "H1 成长被打折(ΔlnPS~Δln营收 斜率<0)",
        "slope": round(beta, 3),
        "p_wcb": round(p_wcb, 3),
        "p_perm": round(p_perm, 3),
        "p_placebo": round(p_plac, 3),
        "sign_consist": round(sign_consist, 2),
        "within_firm_slope": round(float(b_firm), 3),
        "lofo_consist": round(lofo, 2),
        "passes": passes,
        "verdict": consilience(passes),
    }


def _run_level(df: pd.DataFrame, feat: np.ndarray, name: str, *, do_leadlag: str | None = None) -> dict:
    # H2/H3 通用:Y(超额估值) ~ feat + 年度FE,公司聚类。null=0
    y, g = df["Y"].to_numpy(), df["ts_code"].to_numpy()
    xz = _z(feat)
    yr = _fe(df["year"].to_numpy())
    base = np.column_stack([np.ones(len(y)), xz, yr])
    beta, _t, p_wcb = wild_cluster_boot(base, y, g, 1, 0.0)
    p_perm = perm_test(base, y, g, 1)
    p_plac = placebo_test(base, y, g, 1)
    yw = np.clip(y, np.percentile(y, 5), np.percentile(y, 95))
    specs = {
        "年度FE": base,
        "无FE": np.column_stack([np.ones(len(y)), xz]),
        "+公司FE": np.column_stack([np.ones(len(y)), xz, _fe(g), yr]),
    }
    sgn = [np.sign(ols_cluster(X, y, g)[0][1]) for X in specs.values()]
    sgn.append(np.sign(ols_cluster(base, yw, g)[0][1]))
    sign_consist = float(np.mean([s == np.sign(beta) for s in sgn]))
    b_within = ols_cluster(specs["+公司FE"], y, g)[0][1]  # 公司内
    ident = bool(np.sign(b_within) == np.sign(beta) and abs(b_within) > 0.02)
    lofo = _lofo_sign(base, y, g, 1)
    # 领先-滞后(反向因果):仅 H2 做
    leadlag = None
    if do_leadlag:
        d = df.sort_values(["ts_code", "end_date"]).copy()
        d["f_lag"] = d.groupby("ts_code")[do_leadlag].shift(1)
        d["Y_lag"] = d.groupby("ts_code")["Y"].shift(1)
        d["d_feat"] = d.groupby("ts_code")[do_leadlag].diff()
        fwd = d.dropna(subset=["f_lag", "Y"])
        rev = d.dropna(subset=["Y_lag", "d_feat"])
        sf = float(np.polyfit(_z(fwd["f_lag"].to_numpy()), fwd["Y"].to_numpy(), 1)[0]) if len(fwd) > 10 else np.nan
        sr = float(np.polyfit(_z(rev["Y_lag"].to_numpy()), rev["d_feat"].to_numpy(), 1)[0]) if len(rev) > 10 else np.nan
        leadlag = {
            "forward_过去特征→今估值": round(sf, 3),
            "reverse_过去估值→特征变化": round(sr, 3),
            "判读": "疑反向(past估值更能预测特征变化)" if abs(sr) > abs(sf) else "正向为主",
        }
    passes = {
        "推断": p_wcb < 0.10 and p_perm < 0.10,
        "设定": sign_consist >= 0.8,
        "识别": ident,
        "证伪": p_plac < 0.10,
        "泛化": lofo >= 0.85,
    }
    return {
        "name": name,
        "beta": round(beta, 3),
        "p_wcb": round(p_wcb, 3),
        "p_perm": round(p_perm, 3),
        "p_placebo": round(p_plac, 3),
        "sign_consist": round(sign_consist, 2),
        "within_firm_beta": round(float(b_within), 3),
        "lofo_consist": round(lofo, 2),
        "leadlag": leadlag,
        "passes": passes,
        "verdict": consilience(passes),
    }


def main() -> None:
    cp = change_panel()
    lp = level_panel()
    # H3:盈利正交化 = 毛利率剥掉与 ln营收 机械相关的部分,测残差
    nm = lp["f_net_margin"].fillna(lp["f_net_margin"].median()).to_numpy()
    lr = lp["log_rev"].to_numpy()
    nm_resid = (
        nm
        - np.column_stack([np.ones(len(lr)), lr])
        @ np.linalg.lstsq(np.column_stack([np.ones(len(lr)), lr]), nm, rcond=None)[0]
    )
    results = {
        "H1": run_H1(cp),
        "H2": _run_level(
            lp,
            lp["f_debt_to_assets"].fillna(lp["f_debt_to_assets"].median()).to_numpy(),
            "H2 低杠杆→高估值(超额PS~资产负债率,负)",
            do_leadlag="f_debt_to_assets",
        ),
        "H3": _run_level(lp, nm_resid, "H3 盈利(毛利率剥营收机械部分后)→估值"),
    }
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for h, r in results.items():
        print(f"\n[{h}] {r['name']}")
        b = r.get("slope", r.get("beta"))
        print(
            f"  系数={b} | WCB p={r['p_wcb']} 置换p={r['p_perm']} 安慰剂p={r['p_placebo']} | "
            f"设定一致{r['sign_consist']} 公司内={r.get('within_firm_slope', r.get('within_firm_beta'))} 留一家{r['lofo_consist']}"
        )
        if r.get("leadlag"):
            print(f"  领先滞后: {r['leadlag']}")
        print(f"  关:{r['passes']}")
        print(f"  ⇒ {r['verdict']}")
    print("\nsaved ->", OUT)


if __name__ == "__main__":
    main()

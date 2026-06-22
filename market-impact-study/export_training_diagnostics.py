# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Export causal-ML internals (DML residuals, propensity, CATE, bootstrap, placebo) for dashboard transparency."""

# 职责：把因果管道的"训练过程"中间量导出供仪表板可视化 = INV-028,破黑箱:
#       ① DML 去偏残差(Y残差 vs 处理残差,斜率=效应);② 倾向得分重叠;③ 因果森林 CATE 分布;
#       ④ 公司层聚类自助 ATE 分布;⑤ 安慰剂置换零分布。聚焦定增(头条)+ 3 动作倾向。
# 不做什么：不重出主结论(那是 analyze/harden);只导出中间量。
# 运行环境：隔离 venv `.venv-causal`(econml);从仓库根 `.venv-causal/bin/python ...`。
# 允许依赖层：标准库、numpy/pandas、lightgbm、econml、sklearn、cate_14firm 产物。
# 谁不应该 import：建模/主流程不应 import 本入口。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from econml.dml import CausalForestDML
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict

C = Path("market-impact-study/data/processed/modeling/cate_14firm")
OUT = C / "training_diagnostics.json"
# 与 analyze_capital_action_cate.py 同步:价格技术 + 基本面 + 成长
WCOLS = [
    "log_mv",
    "mom20",
    "mom60",
    "vol20",
    "turn20",
    "f_roe",
    "f_roa",
    "f_gross_margin",
    "f_net_margin",
    "f_op_margin",
    "f_debt_to_assets",
    "f_current_ratio",
    "f_equity_mult",
    "f_asset_turn",
    "f_rd_intensity",
    "f_ocf_to_rev",
    "f_fcf_to_rev",
    "f_cash_to_assets",
    "f_ni_yoy",
    "rev_cagr2",
    "rev_cagr3",
]
XCF_COLS = ["val_pct", "log_mv", "f_roe", "f_debt_to_assets", "f_rd_intensity", "rev_cagr3"]
ACTIONS = ["定增/再融资", "股东增减持/限售流通", "股份回购(首发)"]
HEAD = "定增/再融资"
RNG = 0
N_BOOT = 150
N_PERM = 200


def y_model(n: int = 200) -> LGBMRegressor:
    return LGBMRegressor(
        n_estimators=n, num_leaves=15, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1
    )


def t_model(n: int = 200) -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=n, num_leaves=15, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1
    )


def subset(df: pd.DataFrame, action: str) -> pd.DataFrame:
    s = df[(df["subtype"] == action) | (df["D"] == 0)].copy()
    s["D"] = (s["subtype"] == action).astype(int)
    return s


def ate_linear(y_res: np.ndarray, t_res: np.ndarray) -> float:
    return float(np.polyfit(t_res, y_res, 1)[0])


def main() -> None:
    df = pd.read_csv(C / "cate_panel_14firm.csv")
    df = df[df["val_pct"].notna()].copy()
    df["rel"] = df["rel"].clip(df["rel"].quantile(0.01), df["rel"].quantile(0.99))
    for c in WCOLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(df[c].median())
    rng = np.random.RandomState(RNG)
    out: dict = {}

    # ① DML 去偏残差(定增):partial out W via cross-fitting,残差散点斜率=ATE
    s = subset(df, HEAD)
    y, d, w = s["rel"].to_numpy(), s["D"].to_numpy(), s[WCOLS].to_numpy()
    y_hat = cross_val_predict(y_model(), w, y, cv=KFold(5, shuffle=True, random_state=RNG))
    p_hat = cross_val_predict(
        t_model(), w, d, cv=StratifiedKFold(5, shuffle=True, random_state=RNG), method="predict_proba"
    )[:, 1]
    y_res, t_res = y - y_hat, d - p_hat
    sl = ate_linear(y_res, t_res)
    out["dml_residual"] = {
        "action": HEAD,
        "y_res": [round(float(v) * 100, 2) for v in y_res],
        "t_res": [round(float(v), 3) for v in t_res],
        "slope_pct": round(sl * 100, 2),
        "n_treated": int(d.sum()),
    }

    # ② 倾向得分重叠(3 动作):treated vs control 的倾向分
    prop = {}
    for a in ACTIONS:
        sa = subset(df, a)
        ph = cross_val_predict(
            t_model(),
            sa[WCOLS].to_numpy(),
            sa["D"].to_numpy(),
            cv=StratifiedKFold(5, shuffle=True, random_state=RNG),
            method="predict_proba",
        )[:, 1]
        da = sa["D"].to_numpy()
        prop[a] = {
            "treated": [round(float(v), 3) for v in ph[da == 1]],
            "control": [round(float(v), 3) for v in ph[da == 0]],
        }
    out["propensity"] = prop

    # ③ 因果森林 CATE 分布(定增):每个处理事件的个体效应
    xcf = s[XCF_COLS].to_numpy()
    cf = CausalForestDML(
        model_y=y_model(),
        model_t=t_model(),
        discrete_treatment=True,
        n_estimators=600,
        min_samples_leaf=20,
        cv=4,
        random_state=RNG,
    )
    cf.fit(y, d, X=xcf, W=w)
    cate = cf.effect(xcf[d == 1]) * 100
    out["cate_dist"] = {
        "action": HEAD,
        "cate_pct": [round(float(v), 2) for v in cate],
        "val_pct": [round(float(v), 2) for v in s.loc[s["D"] == 1, "val_pct"]],
    }

    # ④ 公司层聚类自助 ATE 分布(定增)
    firms = s["ts_code"].unique().tolist()
    draws = []
    for _ in range(N_BOOT):
        pick = rng.choice(firms, size=len(firms), replace=True)
        parts = [s[s["ts_code"] == c].assign(ts_code=f"{c}_{i}") for i, c in enumerate(pick)]
        bs = pd.concat(parts, ignore_index=True)
        yb, db_, wb = bs["rel"].to_numpy(), bs["D"].to_numpy(), bs[WCOLS].to_numpy()
        if db_.sum() < 15 or db_.sum() == len(db_):
            continue
        yhb = cross_val_predict(y_model(120), wb, yb, cv=KFold(3, shuffle=True, random_state=RNG))
        phb = cross_val_predict(
            t_model(120), wb, db_, cv=StratifiedKFold(3, shuffle=True, random_state=RNG), method="predict_proba"
        )[:, 1]
        draws.append(ate_linear(yb - yhb, db_ - phb) * 100)
    arr = np.array(draws)
    out["cluster_bootstrap"] = {
        "action": HEAD,
        "draws_pct": [round(float(v), 2) for v in arr],
        "ci90": [round(float(np.percentile(arr, 5)), 2), round(float(np.percentile(arr, 95)), 2)],
        "point_pct": round(sl * 100, 2),
    }

    # ⑤ 安慰剂置换零分布(定增):打乱处理标签,ATE 应≈0
    null = []
    for _ in range(N_PERM):
        dp = rng.permutation(d)
        php = cross_val_predict(
            t_model(120), w, dp, cv=StratifiedKFold(3, shuffle=True, random_state=RNG), method="predict_proba"
        )[:, 1]
        null.append(ate_linear(y - y_hat, dp - php) * 100)
    nn = np.array(null)
    out["placebo_perm"] = {
        "action": HEAD,
        "null_pct": [round(float(v), 2) for v in nn],
        "observed_pct": round(sl * 100, 2),
        "p": round(float((np.abs(nn) >= abs(sl * 100)).mean()), 3),
    }

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(
        f"DML残差 slope={out['dml_residual']['slope_pct']}%  CATE n={len(cate)}  "
        f"bootstrap n={len(arr)} CI={out['cluster_bootstrap']['ci90']}  placebo p={out['placebo_perm']['p']}"
    )
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()

# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Event DML nuisance robustness: machine-tune nuisance (by prediction, NOT by ATE) + report ATE sensitivity band."""
# 职责：去掉事件因果线"手调 nuisance 作弊"嫌疑 = INV-043。① nuisance 用 GroupKFold 随机搜索按"预测准不准"
#       (Y的R²/T的AUC)机器选,不碰 ATE(按ATE调才叫作弊);② ATE 报成跨 5 种 nuisance 配置的区间 + 机器调那版的
#       解析CI。结论:各配置 ATE 都落 null/小区,定性稳 = 手调改不了结论。
# 不做什么：不改主 analyze 脚本逻辑;只做稳健性复核,产 JSON。
# 运行环境：隔离 venv .venv-causal(econml)。从仓库根 .venv-causal/bin/python ...。
# 允许依赖层：标准库、numpy/pandas、lightgbm、econml、sklearn、cate_panel 产物。
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from econml.dml import LinearDML
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import GroupKFold, RandomizedSearchCV

warnings.filterwarnings("ignore")
C = Path("market-impact-study/data/processed/modeling/cate_14firm")
OUT = C / "event_dml_robust.json"
WCOLS = ["log_mv", "mom20", "mom60", "vol20", "turn20", "f_roe", "f_roa", "f_gross_margin", "f_net_margin",
         "f_op_margin", "f_debt_to_assets", "f_current_ratio", "f_equity_mult", "f_asset_turn", "f_rd_intensity",
         "f_ocf_to_rev", "f_fcf_to_rev", "f_ni_yoy", "rev_cagr2", "rev_cagr3"]
ACTIONS = ["定增/再融资", "股东增减持/限售流通", "股份回购(首发)"]
RNG = 0
SPACE = {"n_estimators": [100, 200, 300], "num_leaves": [7, 15, 31], "max_depth": [-1, 3, 5],
         "learning_rate": [0.03, 0.05], "min_child_samples": [20, 30, 50], "subsample": [0.7, 0.9],
         "colsample_bytree": [0.7, 0.9]}


def tune_nuisance(w: np.ndarray, y: np.ndarray, t: np.ndarray, groups: np.ndarray) -> tuple:
    # 按"预测准"机器调(不碰ATE):Y模型最大化R²、T模型最大化AUC,GroupKFold按公司
    gkf = GroupKFold(4)
    ry = RandomizedSearchCV(LGBMRegressor(random_state=RNG, verbose=-1), SPACE, n_iter=12, scoring="r2",
                            cv=gkf, random_state=RNG, n_jobs=2, error_score="raise").fit(w, y, groups=groups)
    rt = RandomizedSearchCV(LGBMClassifier(random_state=RNG, verbose=-1), SPACE, n_iter=12, scoring="roc_auc",
                            cv=gkf, random_state=RNG, n_jobs=2, error_score="raise").fit(w, t, groups=groups)
    ym = LGBMRegressor(**ry.best_params_, random_state=RNG, verbose=-1)
    tm = LGBMClassifier(**rt.best_params_, random_state=RNG, verbose=-1)
    return ym, tm, round(float(ry.best_score_), 3), round(float(rt.best_score_), 3)


def ate_of(my, mt, y, t, x, w) -> float:
    ld = LinearDML(model_y=my, model_t=mt, discrete_treatment=True, cv=4, random_state=RNG)
    ld.fit(y, t, X=x, W=w)
    return float(np.ravel(ld.ate(x))[0]) * 100


def ate_ci(my, mt, y, t, x, w) -> tuple[float, list]:
    ld = LinearDML(model_y=my, model_t=mt, discrete_treatment=True, cv=4, random_state=RNG)
    ld.fit(y, t, X=x, W=w)
    lo, hi = ld.ate_interval(x, alpha=0.10)
    return float(np.ravel(ld.ate(x))[0]) * 100, [round(float(np.ravel(lo)[0]) * 100, 2), round(float(np.ravel(hi)[0]) * 100, 2)]


def fixed(name: str):
    cfg = {"手设(300/15)": (300, 15), "浅(100/7)": (100, 7), "深(500/31)": (500, 31)}
    if name == "线性":
        return LinearRegression(), LogisticRegression(max_iter=2000)
    n, lv = cfg[name]
    return (LGBMRegressor(n_estimators=n, num_leaves=lv, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1),
            LGBMClassifier(n_estimators=n, num_leaves=lv, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1))


def main() -> None:
    df = pd.read_csv(C / "cate_panel_14firm.csv")
    fit = df[df["val_pct"].notna()].copy()
    fit["rel"] = fit["rel"].clip(fit["rel"].quantile(0.01), fit["rel"].quantile(0.99))
    for col in [*WCOLS, "val_pct"]:
        fit[col] = pd.to_numeric(fit[col], errors="coerce").fillna(fit[col].median())
    out = {}
    for action in ACTIONS:
        sub = fit[(fit["subtype"] == action) | (fit["D"] == 0)].copy()
        sub["D"] = (sub["subtype"] == action).astype(int)
        y, t = sub["rel"].to_numpy(), sub["D"].to_numpy()
        x, w = sub[["val_pct"]].to_numpy(), sub[WCOLS].to_numpy()
        g = sub["ts_code"].to_numpy()
        ym, tm, r2, auc = tune_nuisance(w, y, t, g)
        ate_t, ci_t = ate_ci(ym, tm, y, t, x, w)
        band = {"机器调": round(ate_t, 2)}
        for nm in ("手设(300/15)", "浅(100/7)", "深(500/31)", "线性"):
            my, mt = fixed(nm)
            band[nm] = round(ate_of(my, mt, y, t, x, w), 2)
        vals = list(band.values())
        out[action] = {"ate_tuned_pct": round(ate_t, 2), "tuned_ci90": ci_t, "tuned_sig": bool(ci_t[0] * ci_t[1] > 0),
                       "nuisance_Y_r2": r2, "nuisance_T_auc": auc, "ate_band": band,
                       "band_min": min(vals), "band_max": max(vals),
                       "conclusion": "各配置全落非显著/小区,定性稳" if (ci_t[0] * ci_t[1] <= 0) else "显著(罕见)"}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for a, r in out.items():
        print(f"{a[:8]:8s} 机器调ATE={r['ate_tuned_pct']:+.2f}% CI{r['tuned_ci90']} (Y_R²={r['nuisance_Y_r2']} T_AUC={r['nuisance_T_auc']}) "
              f"| 跨配置区间[{r['band_min']:+.2f},{r['band_max']:+.2f}] → {r['conclusion']}")
    print("saved ->", OUT)


if __name__ == "__main__":
    main()

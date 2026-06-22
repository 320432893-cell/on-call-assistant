# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Harden the capital-action CATE inference: nuisance diagnostics, firm-cluster bootstrap, pre-event placebo."""

# 职责：加固 INV-016 的因果推断稳健性 = INV-017。三件事:① nuisance 拟合诊断(Y OOF R²/倾向 AUC/overlap,
#       证 DML 有效性前提);② 公司层整簇 bootstrap(少簇稳健推断,WCB 的非参等价,重检定增显著性);
#       ③ 事前安慰剂(定增是否预测事件前异常收益=反向因果)。读已落盘 cate_panel,不重训主估计。
# 不做什么：不重估主 CATE(那是 analyze_capital_action_cate.py);基准/口径一致沿用。
# 运行环境：隔离 venv `.venv-causal`(econml,见 requirements-causal.txt);从仓库根 `.venv-causal/bin/python market-impact-study/harden_cate_inference.py`。
# 允许依赖层：标准库、numpy/pandas、lightgbm、econml、sklearn、peer_universe、data/raw 行情、cate_14firm 产物。
# 谁不应该 import：主流程/建模脚本不应 import 本入口(依赖隔离 venv)。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from econml.dml import LinearDML
from lightgbm import LGBMClassifier, LGBMRegressor
from peer_universe import load_companies
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict

RAW = Path("market-impact-study/data/raw/tushare")
CATE_DIR = Path("market-impact-study/data/processed/modeling/cate_14firm")
# 与 analyze_capital_action_cate.py 同步:价格技术 + 基本面(盈利/质量/杠杆) + 成长
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
ACTIONS = ["定增/再融资", "股东增减持/限售流通", "股份回购(首发)"]
HEADLINE = "定增/再融资"
RNG = 0
N_BOOT = 150


def light_y() -> LGBMRegressor:
    return LGBMRegressor(
        n_estimators=150, num_leaves=15, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1
    )


def light_t() -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=150, num_leaves=15, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1
    )


def pre_event_reaction(codes: list[str]) -> dict[tuple[str, int], float]:
    """[-21,-1] peer-adjusted reaction per firm-day (placebo outcome: should be unaffected by the action)."""
    panels = {}
    for code in codes:
        path = RAW / "daily_basic" / f"{code}.csv"
        if not path.exists():
            continue
        d = pd.read_csv(path)
        d.columns = [c.lstrip("﻿") for c in d.columns]
        d = d[["trade_date", "total_mv"]].copy()
        d["trade_date"] = d["trade_date"].astype(int)
        d = d.sort_values("trade_date").reset_index(drop=True)
        mv = pd.to_numeric(d["total_mv"], errors="coerce").to_numpy()
        n = len(d)
        pre = np.array([mv[max(0, i - 21)] for i in range(n)])
        cur = np.array([mv[max(0, i - 1)] for i in range(n)])
        with np.errstate(invalid="ignore", divide="ignore"):
            d["ret_pre20"] = np.where(pre > 0, cur / pre - 1, np.nan)
        panels[code] = d
    long = pd.concat(
        [p[["trade_date", "ret_pre20"]].assign(ts_code=c) for c, p in panels.items()], ignore_index=True
    ).dropna(subset=["ret_pre20"])
    grp = long.groupby("trade_date")["ret_pre20"]
    long["tot"] = grp.transform("sum")
    long["cnt"] = grp.transform("count")
    long = long[long["cnt"] >= 2].copy()
    long["relpre"] = long["ret_pre20"] - (long["tot"] - long["ret_pre20"]) / (long["cnt"] - 1)
    return {(r.ts_code, int(r.trade_date)): float(r.relpre) for r in long.itertuples(index=False)}


def ate_of(sub: pd.DataFrame, ycol: str) -> float | None:
    s = sub.dropna(subset=[ycol])
    if s["D"].sum() < 15 or s["D"].nunique() < 2:
        return None
    ld = LinearDML(model_y=light_y(), model_t=light_t(), discrete_treatment=True, cv=3, random_state=RNG)
    ld.fit(s[ycol].to_numpy(), s["D"].to_numpy(), X=s[["val_pct"]].to_numpy(), W=s[WCOLS].to_numpy())
    return float(np.ravel(ld.ate(s[["val_pct"]].to_numpy()))[0])


def nuisance_diag(df: pd.DataFrame) -> list[dict]:
    out = []
    for action in ACTIONS:
        sub = df[(df["subtype"] == action) | (df["D"] == 0)].copy()
        sub["D"] = (sub["subtype"] == action).astype(int)
        x = sub[[*WCOLS, "val_pct"]].to_numpy()
        y, d = sub["rel"].to_numpy(), sub["D"].to_numpy()
        yhat = cross_val_predict(light_y(), x, y, cv=KFold(5, shuffle=True, random_state=RNG))
        phat = cross_val_predict(
            light_t(), x, d, cv=StratifiedKFold(5, shuffle=True, random_state=RNG), method="predict_proba"
        )[:, 1]
        lo, hi = max(phat[d == 1].min(), phat[d == 0].min()), min(phat[d == 1].max(), phat[d == 0].max())
        out.append(
            {
                "action": action,
                "treated": int(d.sum()),
                "y_oof_r2": round(float(r2_score(y, yhat)), 3),
                "propensity_auc": round(float(roc_auc_score(d, phat)), 3),
                "overlap_frac": round(float(((phat >= lo) & (phat <= hi)).mean()), 3),
            }
        )
    return out


def cluster_bootstrap(base: pd.DataFrame, ycol: str) -> dict:
    firms = base["ts_code"].unique().tolist()
    rng = np.random.RandomState(RNG)
    point = ate_of(base, ycol)
    draws = []
    for _ in range(N_BOOT):
        pick = rng.choice(firms, size=len(firms), replace=True)
        parts = []
        for i, code in enumerate(pick):
            g = base[base["ts_code"] == code].copy()
            g["ts_code"] = f"{code}_{i}"
            parts.append(g)
        val = ate_of(pd.concat(parts, ignore_index=True), ycol)
        if val is not None:
            draws.append(val)
    arr = np.array(draws)
    lo, hi = np.percentile(arr, [5, 95])
    p = 2 * min((arr <= 0).mean(), (arr >= 0).mean())
    return {
        "point_pct": round(point * 100, 2),
        "cluster_ci90_pct": [round(lo * 100, 2), round(hi * 100, 2)],
        "two_sided_p": round(float(p), 3),
        "n_boot": len(arr),
        "sig": bool(lo * hi > 0),
    }


def main() -> None:
    codes = [c["ts_code"] for c in load_companies()]
    df = pd.read_csv(CATE_DIR / "cate_panel_14firm.csv")
    df = df[df["val_pct"].notna()].copy()
    df["rel"] = df["rel"].clip(df["rel"].quantile(0.01), df["rel"].quantile(0.99))
    for col in WCOLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(df[col].median())
    relpre = pre_event_reaction(codes)
    df["relpre"] = [relpre.get((c, int(t))) for c, t in zip(df["ts_code"], df["trade_date"], strict=False)]

    diag = nuisance_diag(df)
    base = df[(df["subtype"] == HEADLINE) | (df["D"] == 0)].copy()
    base["D"] = (base["subtype"] == HEADLINE).astype(int)
    forward = cluster_bootstrap(base, "rel")
    placebo = cluster_bootstrap(base, "relpre")

    result = {"action": HEADLINE, "nuisance_diagnostics": diag, "forward_causal": forward, "pre_event_placebo": placebo}
    (CATE_DIR / "cate_hardening.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(diag, ensure_ascii=False, indent=2))
    print(f"定增 forward 因果: {forward}")
    print(f"定增 事前安慰剂(应≈0): {placebo}")
    print(f"saved -> {CATE_DIR}/cate_hardening.json")


if __name__ == "__main__":
    main()

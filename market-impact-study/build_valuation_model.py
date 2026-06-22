"""Explain cross-firm valuation (excess PS) with interpretable ML: GBT+SHAP + ElasticNet, validated out-of-time/LOFO."""

# 职责：把"什么解释 14 家估值差异"做成可解释 ML = INV-035。Y=超额估值(log PS 剥掉年度β+规模残差),
#       X=基本面驱动(盈利/质量/杠杆/成长/趋势)。单调约束 GBT + SHAP 逐家归因 + ElasticNet 弹性对照;
#       样本外(按时间)/留一家(LOFO)验证 + 量化不可解释残差 + 移为折让的 SHAP 归因。
#       兑现"用对的 Y、剥β、GBT+SHAP+趋势、样本外验证"四件(对话 2026-06-17)。
# 不做什么：不做事件因果(那是 analyze_capital_action_cate);不预测股价;只解释估值横截面。
# 允许依赖层：标准库、numpy/pandas、lightgbm、shap、sklearn、peer_universe、data/raw、fundamental_panel。
# 谁不应该 import：建模/仪表板脚本不应 import 本入口,只读其 JSON。
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import statsmodels.api as sm
from lightgbm import LGBMRegressor
from peer_universe import load_companies
from sklearn.linear_model import ElasticNetCV, LinearRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.preprocessing import StandardScaler

DB = Path("market-impact-study/data/raw/tushare/daily_basic")
DAILY = Path("market-impact-study/data/raw/tushare/daily")
HOLDER = Path("market-impact-study/data/raw/tushare/stk_holdernumber")
HK = Path("market-impact-study/data/raw/tushare/hk_hold")  # 北向持股
MARGIN = Path("market-impact-study/data/raw/tushare/margin_detail")  # 融资融券
TOP10 = Path("market-impact-study/data/raw/tushare/top10_floatholders")  # 前十大流通股东
MFLOW = Path("market-impact-study/data/raw/tushare/moneyflow")  # 资金流
INST_KW = ("基金", "社保", "保险", "QFII", "养老", "年金", "资管", "证券投资")  # 机构股东识别
FUND = Path("market-impact-study/data/processed/modeling/fundamental_panel.csv")
OUT = Path("market-impact-study/data/processed/modeling/cate_14firm/valuation_model.json")
YIWEI = "300590.SZ"
RNG = 0
OOT_CUT = 2021  # 样本外:≤2021 训练,≥2022 测试
# GBT 超参:由 `python build_valuation_model.py tune`(GroupKFold按公司随机搜索)选出,见 INV-037
GBT_PARAMS = dict(  # noqa: C408
    n_estimators=120,
    num_leaves=7,
    max_depth=3,
    learning_rate=0.03,
    min_child_samples=30,
    subsample=0.7,
    subsample_freq=1,
    colsample_bytree=0.6,
    reg_alpha=0.5,
    reg_lambda=3.0,
    min_split_gain=0.01,
)

# 驱动 + 期望单调方向(经济意义清晰的才约束,模糊的=0,防小样本编故事)
DRIVERS = {
    "f_net_margin": ("净利率", 1),
    "f_gross_margin": ("毛利率", 1),
    "f_op_margin": ("营业利润率", 1),
    "f_roe": ("ROE", 1),
    "f_roa": ("ROA", 1),
    "f_asset_turn": ("资产周转率", 1),
    "f_rev_yoy": ("营收同比", 1),
    "f_ni_yoy": ("净利同比", 1),
    "f_rev_cagr3": ("营收3年CAGR", 1),
    "f_ocf_to_rev": ("经营现金流/营收", 1),
    "f_fcf_to_rev": ("自由现金流/营收", 1),
    "f_rd_intensity": ("研发强度", 0),
    "f_cash_to_assets": ("现金/总资产", 0),
    "f_debt_to_assets": ("资产负债率", -1),
    "f_current_ratio": ("流动比率", 0),
    "f_equity_mult": ("权益乘数", 0),
    # INV-036 增强:108字段现成比率 + 海外 + 人均
    "f_roic": ("ROIC投入资本回报", 1),
    "f_roe_dt": ("扣非ROE", 1),
    "f_quick_ratio": ("速动比率", 0),
    "f_cash_ratio": ("现金比率", 0),
    "f_ar_turn": ("应收周转", 1),
    "f_fa_turn": ("固定资产周转", 1),
    "f_saleexp_ratio": ("销售费用率", -1),
    "f_adminexp_ratio": ("管理费用率", -1),
    "f_finaexp_ratio": ("财务费用率", -1),
    "f_dt_ni_yoy": ("扣非净利增速", 1),
    "f_ocf_yoy": ("经营现金流增速", 1),
    "f_debt_to_eqt": ("产权比率", -1),
    "f_overseas_share": ("海外收入占比", 0),
    "d_net_margin": ("净利率趋势Δ", 1),
    "d_gross_margin": ("毛利率趋势Δ", 1),  # 趋势特征:再定价触发
    # 流动性/筹码(β/关联层,反向因果,非可操作杠杆;单调=0 不约束)
    "liq_turn": ("换手率(60d)", 0),
    "liq_volratio": ("量比(60d)", 0),
    "liq_amplitude": ("振幅(60d)", 0),
    "liq_amihud": ("Amihud非流动性(60d)", 0),
    "chip_holder_yoy": ("股东户数同比", 0),
    # INV-038 非财务历史信号:所有权/预期/情绪(与财务正交,测残差里另一半)
    "nf_north_ratio": ("北向持股占比", 0),
    "nf_north_chg": ("北向持股Δ60d", 0),
    "nf_margin_ratio": ("融资余额/市值", 0),
    "nf_margin_chg": ("融资余额Δ60d", 0),
    "nf_inst_top10": ("前十大机构占比", 0),
    "nf_mf_net": ("主力净流入/市值", 0),
}
# 标记:这些是流动性/筹码的关联层(非基本面杠杆),报告里单独归类
LIQ_COLS = {"liq_turn", "liq_volratio", "liq_amplitude", "liq_amihud", "chip_holder_yoy"}
NONFIN_COLS = {"nf_north_ratio", "nf_north_chg", "nf_margin_ratio", "nf_margin_chg", "nf_inst_top10", "nf_mf_net"}


def _tmean(a: np.ndarray) -> float:
    a = a[~np.isnan(a)]
    return float(a.mean()) if len(a) else np.nan


def market_series(code: str) -> pd.DataFrame:
    # daily_basic(估值/换手/量比)+ daily(算振幅/Amihud非流动性),按交易日合并
    p1 = DB / f"{code}.csv"
    if not p1.exists():
        return pd.DataFrame()
    db = pd.read_csv(p1)
    db.columns = [c.lstrip("﻿") for c in db.columns]
    db["trade_date"] = db["trade_date"].astype(int)
    for c in ("ps", "total_mv", "turnover_rate", "volume_ratio"):
        db[c] = pd.to_numeric(db.get(c), errors="coerce")
    db = db[["trade_date", "ps", "total_mv", "turnover_rate", "volume_ratio"]]
    p2 = DAILY / f"{code}.csv"
    if p2.exists():
        dl = pd.read_csv(p2)
        dl.columns = [c.lstrip("﻿") for c in dl.columns]
        dl["trade_date"] = dl["trade_date"].astype(int)
        for c in ("high", "low", "pre_close", "pct_chg", "amount"):
            dl[c] = pd.to_numeric(dl.get(c), errors="coerce")
        dl["amplitude"] = ((dl["high"] - dl["low"]) / dl["pre_close"] * 100).where(dl["pre_close"] > 0)
        dl["amihud"] = (dl["pct_chg"].abs() / (dl["amount"] / 1e5)).where(dl["amount"] > 0)  # 千元→亿元
        db = db.merge(dl[["trade_date", "amplitude", "amihud"]], on="trade_date", how="left")
    else:
        db["amplitude"], db["amihud"] = np.nan, np.nan
    return db.sort_values("trade_date").reset_index(drop=True)


def holder_series(code: str) -> pd.DataFrame:
    p = HOLDER / f"{code}.csv"
    if not p.exists():
        return pd.DataFrame()
    h = pd.read_csv(p)
    h.columns = [c.lstrip("﻿") for c in h.columns]
    h["ann_date"] = pd.to_numeric(h["ann_date"], errors="coerce")
    h["holder_num"] = pd.to_numeric(h["holder_num"], errors="coerce")
    return h.dropna(subset=["ann_date", "holder_num"]).sort_values("ann_date").reset_index(drop=True)


def holder_yoy(hs: pd.DataFrame, ann: int) -> float:
    # 股东户数同比(剔出事件前最近一期 vs 约一年前):负=筹码集中(常伴机构进场)
    if hs.empty:
        return np.nan
    a, hn = hs["ann_date"].to_numpy(), hs["holder_num"].to_numpy()
    j = int(np.searchsorted(a, ann, side="right")) - 1
    k = int(np.searchsorted(a, ann - 10000, side="right")) - 1
    if j < 0 or k < 0 or k == j or hn[k] <= 0:
        return np.nan
    return float((hn[j] / hn[k] - 1) * 100)


def _daily_lookup(path: Path, code: str, val_col: str) -> tuple[np.ndarray, np.ndarray] | None:
    p = path / f"{code}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p)
    d.columns = [c.lstrip("﻿") for c in d.columns]
    if "trade_date" not in d.columns or val_col not in d.columns:
        return None
    d["trade_date"] = pd.to_numeric(d["trade_date"], errors="coerce")
    d[val_col] = pd.to_numeric(d[val_col], errors="coerce")
    d = d.dropna(subset=["trade_date", val_col]).sort_values("trade_date")
    return (d["trade_date"].to_numpy(), d[val_col].to_numpy()) if len(d) else None


def _ser_at(ser: tuple[np.ndarray, np.ndarray] | None, ann: int, lag: int = 60) -> tuple[float, float]:
    # PIT 取值:事件日(ann)前最近一条的 level,及相对 lag 行前的变化(同序列网格 ≈ lag 交易日)
    if ser is None:
        return (np.nan, np.nan)
    dates, vals = ser
    j = int(np.searchsorted(dates, ann, side="right")) - 1
    if j < 0:
        return (np.nan, np.nan)
    chg = float(vals[j] - vals[j - lag]) if j - lag >= 0 else np.nan
    return (float(vals[j]), chg)


def top10_inst_series(code: str) -> pd.DataFrame:
    # 前十大流通股东里机构(基金/社保/保险/QFII…)持股占比合计,按报告期 ann_date
    p = TOP10 / f"{code}.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p)
    d.columns = [c.lstrip("﻿") for c in d.columns]
    d["ann_date"] = pd.to_numeric(d["ann_date"], errors="coerce")
    d["hold_ratio"] = pd.to_numeric(d.get("hold_ratio"), errors="coerce")
    name = d.get("holder_name", "").astype(str)
    htype = d.get("holder_type", "").astype(str)
    is_inst = name.str.contains("|".join(INST_KW)) | htype.str.contains("|".join(INST_KW))
    d = d[d["ann_date"].notna() & is_inst]
    g = d.groupby("ann_date")["hold_ratio"].sum().reset_index().sort_values("ann_date")
    return g


def _inst_at(g: pd.DataFrame, ann: int) -> float:
    if g.empty:
        return np.nan
    a, v = g["ann_date"].to_numpy(), g["hold_ratio"].to_numpy()
    j = int(np.searchsorted(a, ann, side="right")) - 1
    return float(v[j]) if j >= 0 else np.nan


def build_panel() -> pd.DataFrame:
    fund = pd.read_csv(FUND)
    names = {c["ts_code"]: c["name"] for c in load_companies()}
    fcols = [k for k in DRIVERS if k.startswith("f_")]
    rows = []
    for code, g in fund.groupby("ts_code"):
        ms = market_series(code)
        if ms.empty:
            continue
        td = ms["trade_date"].to_numpy()
        ps_a, mv_a = ms["ps"].to_numpy(), ms["total_mv"].to_numpy()
        turn, vr, amp, amh = (ms[c].to_numpy() for c in ("turnover_rate", "volume_ratio", "amplitude", "amihud"))
        hs = holder_series(code)
        hk, mg, mf = (
            _daily_lookup(HK, code, "ratio"),
            _daily_lookup(MARGIN, code, "rzye"),
            _daily_lookup(MFLOW, code, "net_mf_amount"),
        )
        t10 = top10_inst_series(code)
        for _, r in g.iterrows():
            ann = int(r["ann_date"])
            i = int(np.searchsorted(td, ann, side="left"))
            if i >= len(td):
                continue
            ps, mv = ps_a[i], mv_a[i]
            if not (ps > 0 and mv > 0):
                continue
            lo = max(0, i - 60)  # 事件前60交易日窗口的流动性
            north_lvl, north_chg = _ser_at(hk, ann)
            marg_lvl, marg_chg = _ser_at(mg, ann)
            mf_lvl, _mc = _ser_at(mf, ann, lag=20)
            row = {
                "ts_code": code,
                "firm": names.get(code, code),
                "year": int(r["end_date"]) // 10000,
                "end_date": int(r["end_date"]),
                "ps": float(ps),
                "log_mv": float(np.log(mv)),
                "liq_turn": _tmean(turn[lo:i]),
                "liq_volratio": _tmean(vr[lo:i]),
                "liq_amplitude": _tmean(amp[lo:i]),
                "liq_amihud": _tmean(amh[lo:i]),
                "chip_holder_yoy": holder_yoy(hs, ann),
                # 非财务历史信号(所有权/预期/情绪),按 ann_date PIT;比率除以市值口径一致(树/Lasso尺度无关)
                "nf_north_ratio": north_lvl,
                "nf_north_chg": north_chg,
                "nf_margin_ratio": marg_lvl / mv if marg_lvl == marg_lvl else np.nan,
                "nf_margin_chg": marg_chg / mv if marg_chg == marg_chg else np.nan,
                "nf_inst_top10": _inst_at(t10, ann),
                "nf_mf_net": mf_lvl / mv if mf_lvl == mf_lvl else np.nan,
            }
            row.update({k: pd.to_numeric(r.get(k), errors="coerce") for k in fcols})
            rows.append(row)
    df = pd.DataFrame(rows).sort_values(["ts_code", "end_date"]).reset_index(drop=True)
    # 趋势特征:同公司毛利/净利率的环比变化(再定价触发)
    df["d_net_margin"] = df.groupby("ts_code")["f_net_margin"].diff()
    df["d_gross_margin"] = df.groupby("ts_code")["f_gross_margin"].diff()
    return df


def excess_valuation(df: pd.DataFrame) -> np.ndarray:
    # Y = log(PS) 剥掉 年度固定效应 + log规模 后的残差 = 公司特异的"估值溢价/折让"(剥β+规模)
    logps = np.log(df["ps"].clip(lower=0.05).to_numpy())
    logps = np.clip(logps, np.quantile(logps, 0.02), np.quantile(logps, 0.98))
    yr = pd.get_dummies(df["year"], prefix="y", drop_first=True).to_numpy(dtype=float)
    ctrl = np.column_stack([df["log_mv"].to_numpy(), yr])
    resid = logps - LinearRegression().fit(ctrl, logps).predict(ctrl)
    return resid


def fit_gbt(x: pd.DataFrame, y: np.ndarray, cols: list[str], params: dict | None = None) -> LGBMRegressor:
    mono = [DRIVERS[c][1] for c in cols]
    m = LGBMRegressor(**(params or GBT_PARAMS), random_state=RNG, verbose=-1, monotone_constraints=mono)
    m.fit(x, y)
    return m


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    # 多种评估指标(回归):R² + RMSE + MAE
    return {
        "r2": round(float(r2_score(y_true, y_pred)), 3),
        "rmse": round(float(mean_squared_error(y_true, y_pred) ** 0.5), 3),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 3),
    }


def auto_params(x: pd.DataFrame, y: np.ndarray, groups: pd.Series, cols: list[str]) -> dict:
    # 机器自动选超参:GroupKFold(按公司)随机搜索,固定种子→可复现。无任何手填数字。
    from sklearn.model_selection import GroupKFold, RandomizedSearchCV

    mono = [DRIVERS[c][1] for c in cols]
    base = LGBMRegressor(random_state=RNG, verbose=-1, subsample_freq=1, monotone_constraints=mono)
    rs = RandomizedSearchCV(
        base,
        SPACE,
        n_iter=120,
        scoring="r2",
        cv=GroupKFold(5),
        random_state=RNG,
        n_jobs=2,
        refit=False,
        error_score="raise",
    )
    rs.fit(x, y, groups=groups)
    return dict(rs.best_params_)


def select_features(x: pd.DataFrame, y: np.ndarray, groups: pd.Series, cols: list[str]) -> list[str]:
    # L1(Lasso)自动特征选择:GroupKFold(按公司)选 alpha 防泄漏,保留非零系数特征。纯机器、固定种子。
    from sklearn.linear_model import LassoCV
    from sklearn.model_selection import GroupKFold

    xs = StandardScaler().fit_transform(x[cols])
    splits = list(GroupKFold(5).split(xs, y, groups))
    las = LassoCV(cv=splits, random_state=RNG, max_iter=50000, n_jobs=2).fit(xs, y)
    kept = [c for c, co in zip(cols, las.coef_, strict=False) if abs(co) > 1e-6]
    return kept or list(cols)


def l1_report(x: pd.DataFrame, y: np.ndarray, groups: pd.Series, cols: list[str]) -> dict:
    # 可审的 L1 选择数据:每特征标准化 Lasso 系数 + 舍弃原因(与哪个选中特征共线、|r|)。
    from sklearn.linear_model import LassoCV
    from sklearn.model_selection import GroupKFold

    xs = StandardScaler().fit_transform(x[cols])
    splits = list(GroupKFold(5).split(xs, y, groups))
    las = LassoCV(cv=splits, random_state=RNG, max_iter=50000, n_jobs=2).fit(xs, y)
    coef = las.coef_
    kept_idx = [i for i, co in enumerate(coef) if abs(co) > 1e-6]
    corr = np.corrcoef(xs, rowvar=False)
    rows = []
    for j, c in enumerate(cols):
        co = float(coef[j])
        is_kept = abs(co) > 1e-6
        reason = None
        if not is_kept and kept_idx:
            best = max(kept_idx, key=lambda k: abs(corr[j, k]))
            reason = {"with": DRIVERS[cols[best]][0], "r": round(float(abs(corr[j, best])), 2)}
        rows.append({"feat": DRIVERS[c][0], "coef": round(co, 3), "kept": is_kept, "reason": reason})
    rows.sort(key=lambda r: (not r["kept"], -abs(r["coef"])))
    return {"alpha": round(float(las.alpha_), 4), "n_kept": len(kept_idx), "features": rows}


SPACE = {
    "n_estimators": [80, 120, 200, 300],
    "num_leaves": [5, 7, 11, 15, 31],
    "max_depth": [2, 3, 4, 5, -1],
    "learning_rate": [0.02, 0.03, 0.05],
    "min_child_samples": [20, 30, 40, 60],
    "subsample": [0.6, 0.7, 0.8, 1.0],
    "colsample_bytree": [0.5, 0.6, 0.8, 1.0],
    "reg_alpha": [0, 0.5, 1, 2],
    "reg_lambda": [1, 3, 5, 10],
    "min_split_gain": [0.0, 0.01, 0.05],
}


def tune() -> None:
    # 正规方法 = 嵌套交叉验证:外层GroupKFold(按公司)估泛化,内层GroupKFold+随机搜索选参。
    # 报告的外层分数从未被用来挑过模型 → 无选择偏置(不掩耳盗铃)。GroupKFold 杜绝同公司跨折泄漏。
    from sklearn.model_selection import GroupKFold, RandomizedSearchCV, cross_val_score

    df = build_panel()
    cols = list(DRIVERS)
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ps"]).reset_index(drop=True)
    x, y, groups = df[cols].fillna(df[cols].median()), excess_valuation(df), df["ts_code"]
    mono = [DRIVERS[c][1] for c in cols]
    base = LGBMRegressor(random_state=RNG, verbose=-1, subsample_freq=1, monotone_constraints=mono)

    outer, outer_scores, picks = GroupKFold(5), [], []
    for k, (tr, te) in enumerate(outer.split(x, y, groups)):
        inner = RandomizedSearchCV(
            base,
            SPACE,
            n_iter=60,
            scoring="r2",
            cv=GroupKFold(4),
            random_state=RNG,
            n_jobs=2,
            refit=True,
            error_score="raise",
        )
        inner.fit(x.iloc[tr], y[tr], groups=groups.iloc[tr])
        sc = float(r2_score(y[te], inner.predict(x.iloc[te])))
        outer_scores.append(sc)
        picks.append(inner.best_params_)
        bp = inner.best_params_
        print(
            f"  外折{k + 1}: 测试R²={sc:.3f}  内层选 leaves={bp['num_leaves']} depth={bp['max_depth']} "
            f"min_child={bp['min_child_samples']} lr={bp['learning_rate']}"
        )
    cur = LGBMRegressor(**GBT_PARAMS, random_state=RNG, verbose=-1, monotone_constraints=mono)
    cur_cv = float(cross_val_score(cur, x, y, groups=groups, cv=GroupKFold(5), scoring="r2").mean())
    print(
        f"\n【嵌套CV 无偏泛化 R²】= {np.mean(outer_scores):.3f} ± {np.std(outer_scores):.3f}  "
        f"(诚实数:没在它上面选过模型)"
    )
    print(f"对比:手调参数的分组CV R² = {cur_cv:.3f}")
    # 部署参数:全数据上单层搜索定参(仅用于落地的那一组,泛化以上面嵌套CV为准)
    final = RandomizedSearchCV(
        base,
        SPACE,
        n_iter=120,
        scoring="r2",
        cv=GroupKFold(5),
        random_state=RNG,
        n_jobs=2,
        refit=False,
        error_score="raise",
    )
    final.fit(x, y, groups=groups)
    print("部署用参数(全数据搜索定参,填入 GBT_PARAMS):", {k: final.best_params_[k] for k in sorted(final.best_params_)})


def fe_validate(df: pd.DataFrame, cols: list[str], y: np.ndarray) -> list[dict]:
    # 逐特征:跨公司(pooled)斜率 vs 公司内随时间(FE 去公司均值)斜率,聚类SE(按公司)。
    # 真驱动=公司内也显著且同号(经得起固定效应);伪/跨公司驱动=只在跨公司成立(被公司固定特质混淆,如杠杆)。
    firm = df["ts_code"]
    yz = pd.Series(y, index=df.index)
    yw = yz - yz.groupby(firm).transform("mean")
    rows = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce")
        s = ((s - s.mean()) / (s.std(ddof=0) or 1.0)).fillna(0.0)
        try:
            pooled = sm.OLS(yz, sm.add_constant(s)).fit(cov_type="cluster", cov_kwds={"groups": firm})
            pc, pp = float(pooled.params.iloc[1]), float(pooled.pvalues.iloc[1])
            sw = s - s.groupby(firm).transform("mean")
            within = sm.OLS(yw, sw).fit(cov_type="cluster", cov_kwds={"groups": firm})
            wc, wp = float(within.params.iloc[0]), float(within.pvalues.iloc[0])
        except Exception:  # noqa: BLE001 - 退化样本跳过
            continue
        if wp < 0.10 and pc * wc > 0 and abs(wc) > 0.05:
            verdict = "真驱动"
        elif abs(pc) > 0.08 and pp < 0.10 and (wp > 0.20 or abs(wc) < 0.03):
            verdict = "伪/跨公司"
        else:
            verdict = "弱"
        rows.append(
            {
                "feat": DRIVERS[c][0],
                "pooled": round(pc, 3),
                "pooled_p": round(pp, 3),
                "within": round(wc, 3),
                "within_p": round(wp, 3),
                "verdict": verdict,
            }
        )
    return sorted(rows, key=lambda r: -abs(r["pooled"]))


def learning_curve_data(x: pd.DataFrame, y: np.ndarray, groups: pd.Series, cols: list[str], params: dict) -> dict:
    # 学习曲线(实验图):训练分 vs 交叉验证分随训练样本量变化。
    # CV 用 GroupKFold(按公司,防泄漏)+ **汇集留出预测算一个 R²**(与卡片 LOFO/OOT 同口径,非每折平均),
    # 故末端与全卡片报告的样本外 R² 一致、且无每折小样本的负值噪声。还在涨=扩样本能提升(数据是瓶颈)。
    from sklearn.model_selection import GroupKFold

    g = groups.to_numpy()
    rng = np.random.default_rng(RNG)
    sizes, train_r2s, cv_r2s = [], [], []
    for frac in [0.4, 0.55, 0.7, 0.85, 1.0]:
        idx = []  # 按公司分层子采样,保证每家都在(否则少公司 = 伪小样本)
        for code in np.unique(g):
            ci = np.where(g == code)[0]
            k = min(len(ci), max(3, int(round(len(ci) * frac))))
            idx.extend(rng.choice(ci, size=k, replace=False).tolist())
        idx = np.array(sorted(idx))
        xs, ys, gs = x.iloc[idx], y[idx], g[idx]
        pred = np.full(len(idx), np.nan)
        for tr, te in GroupKFold(5).split(xs, ys, gs):  # 汇集留出预测
            m = fit_gbt(xs.iloc[tr], ys[tr], cols, params)
            pred[te] = m.predict(xs.iloc[te])
        ok = ~np.isnan(pred)
        full = fit_gbt(xs, ys, cols, params)
        sizes.append(int(len(idx)))
        train_r2s.append(round(float(r2_score(ys, full.predict(xs))), 3))
        cv_r2s.append(round(float(r2_score(ys[ok], pred[ok])), 3))
    return {"train_sizes": sizes, "train_r2": train_r2s, "cv_r2": cv_r2s}


def screen_report(y: np.ndarray, pred: np.ndarray, ok: np.ndarray, yiwei_mask: np.ndarray) -> dict:
    # 错误定价筛查:把"预测超额估值"做成决策层。①分类(溢价>0 vs 折让)用 LOFO 外推预测打分,
    # 报多指标(AUC/准确率/精确率/召回率/F1+混淆矩阵)= 评委要的"多种评估指标";只用样本外预测,不掺样本内。
    # ②移为情绪缺口:同行定价模型(LOFO,训练不含移为)给出"基本面应得溢价",实际−应得=移为特异的情绪/未定价部分。
    yt = (y[ok] > 0).astype(int)
    score = pred[ok]
    yhat = (score > 0).astype(int)
    cls = {}
    if yt.sum() > 0 and yt.sum() < len(yt):  # 两类都有才可评
        tn, fp, fn, tp = confusion_matrix(yt, yhat, labels=[0, 1]).ravel()
        cls = {
            "n": len(yt),
            "base_rate_premium": round(float(yt.mean()), 3),  # 样本中"溢价"占比(基准)
            "auc": round(float(roc_auc_score(yt, score)), 3),
            "accuracy": round(float(accuracy_score(yt, yhat)), 3),
            "precision": round(float(precision_score(yt, yhat, zero_division=0)), 3),
            "recall": round(float(recall_score(yt, yhat, zero_division=0)), 3),
            "f1": round(float(f1_score(yt, yhat, zero_division=0)), 3),
            "confusion": {"tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)},
            "note": "LOFO 外推预测;阈值=0(溢价/折让分界)。小样本(有效簇14)下指标方差大,只作筛查参考。",
        }
        fpr, tpr, _ = roc_curve(yt, score)
        cls["roc"] = {"fpr": [round(float(v), 3) for v in fpr], "tpr": [round(float(v), 3) for v in tpr]}
    ym = yiwei_mask & ok
    yiwei = {}
    if ym.sum() > 0:
        actual = float(y[ym].mean())
        justified = float(pred[ym].mean())  # 同行定价模型(LOFO)给的"基本面应得溢价"
        gap = actual - justified
        yiwei = {
            "actual_excess": round(actual, 3),
            "fundamental_justified": round(justified, 3),
            "sentiment_gap": round(gap, 3),
            "explained_share": round(justified / actual, 3) if abs(actual) > 1e-6 else None,
            "sentiment_share": round(gap / actual, 3) if abs(actual) > 1e-6 else None,
            "note": "应得=用其余13家定价规律外推移为(不含移为训练);缺口=基本面解释不了的部分(情绪/叙事/小样本)。",
        }
    return {"classification": cls, "yiwei_mispricing": yiwei}


def eda_report(df: pd.DataFrame, cols_all: list[str], cols: list[str], y: np.ndarray) -> dict:
    # 探索性数据分析:描述统计 + 目标分布直方图 + 相关性矩阵 + 缺失率(供 EDA 页)。
    def desc(name: str, arr) -> dict:
        a = pd.to_numeric(pd.Series(arr), errors="coerce").dropna().to_numpy()
        if a.size == 0:
            return {"name": name, "n": 0}
        return {"name": name, "n": int(a.size), "mean": round(float(a.mean()), 2), "std": round(float(a.std()), 2),
                "min": round(float(a.min()), 2), "median": round(float(np.median(a)), 2), "max": round(float(a.max()), 2)}

    stats = [desc("超额估值 Y(目标)", y)]
    for c in cols[:7]:
        stats.append(desc(DRIVERS[c][0], df[c]))
    h, e = np.histogram(np.asarray(y, dtype=float), bins=11)
    thist = [{"x": round(float((e[i] + e[i + 1]) / 2), 2), "c": int(h[i])} for i in range(len(h))]
    want = ["净利率", "营业利润率", "ROE", "毛利率", "资产负债率", "营收3年CAGR", "海外收入占比", "研发强度", "资产周转率", "现金比率"]
    sel = [c for c in cols_all if DRIVERS[c][0] in want]
    cm = df[sel].apply(lambda col: pd.to_numeric(col, errors="coerce")).corr()
    corr = [[round(float(v), 2) for v in row] for row in cm.to_numpy()]
    cnames = [DRIVERS[c][0] for c in sel]
    miss = sorted(
        [{"feat": DRIVERS[c][0], "pct": round(float(pd.to_numeric(df[c], errors="coerce").isna().mean() * 100), 1)} for c in cols_all],
        key=lambda z: -z["pct"],
    )
    return {"stats": stats, "target_hist": thist, "corr": corr, "corr_names": cnames, "missing": miss[:10]}


def main() -> None:
    df = build_panel()
    cols_all = list(DRIVERS)
    for c in cols_all:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ps"]).reset_index(drop=True)
    med = df[cols_all].median()
    x_full = df[cols_all].fillna(med).fillna(0.0)  # 末位兜底:整列全缺(如某信号无覆盖)填0,防 Lasso NaN
    y = excess_valuation(df)
    groups = df["ts_code"]
    # L1 特征正则:全数据选(给最终可解释模型);OOT/LOFO 折内单独再选(防泄漏)
    cols = select_features(x_full, y, groups, cols_all)
    x_all = x_full[cols]
    print(f"L1特征选择:{len(cols_all)}→{len(cols)} 个;丢弃 {[DRIVERS[c][0] for c in cols_all if c not in cols]}")
    params = auto_params(x_all, y, groups, cols)  # 机器自动选参(无手填)
    print("机器自动选参(GroupKFold随机搜索):", {k: params[k] for k in sorted(params)})

    # 主模型:单调 GBT(全样本拟合用于 SHAP 归因)
    gbt = fit_gbt(x_all, y, cols, params)
    expl = shap.TreeExplainer(gbt)
    sv = expl.shap_values(x_all)
    mean_abs = np.abs(sv).mean(axis=0)
    imp = sorted(
        [
            {"feat": DRIVERS[c][0], "shap": round(float(mean_abs[j]), 4), "dir": DRIVERS[c][1]}
            for j, c in enumerate(cols)
        ],
        key=lambda z: -z["shap"],
    )

    # 移为折让的 SHAP 归因:移为各期平均 SHAP(负=把移为估值往下压=折让来源)
    yw = df["ts_code"] == YIWEI
    yw_shap = sorted(
        [{"feat": DRIVERS[c][0], "contrib": round(float(sv[yw.to_numpy(), j].mean()), 4)} for j, c in enumerate(cols)],
        key=lambda z: z["contrib"],
    )

    # 逐家归因:每家平均 SHAP → 溢价/折让 + 抬高(lift)/压低(drag)前2驱动 + 一句话结论
    firm_attr = []
    for code in df["ts_code"].unique():
        m = (df["ts_code"] == code).to_numpy()
        msv = sv[m].mean(axis=0)
        pairs = sorted([[DRIVERS[c][0], round(float(msv[j]), 3)] for j, c in enumerate(cols)], key=lambda z: z[1])
        firm_attr.append(
            {
                "firm": df.loc[m, "firm"].iloc[0],
                "code": code,
                "n": int(m.sum()),
                "excess": round(float(y[m].mean()), 3),
                "lift": [p for p in reversed(pairs[-2:])],
                "drag": pairs[:2],
            }
        )
    firm_attr.sort(key=lambda z: -z["excess"])

    # ElasticNet 弹性对照(标准化系数,符号校验)
    xs = StandardScaler().fit_transform(x_all)
    en = ElasticNetCV(l1_ratio=[0.2, 0.5, 0.8], cv=5, random_state=RNG, max_iter=5000).fit(xs, y)
    en_coef = sorted(
        [
            {"feat": DRIVERS[c][0], "coef": round(float(en.coef_[j]), 4), "dir": DRIVERS[c][1]}
            for j, c in enumerate(cols)
        ],
        key=lambda z: -abs(z["coef"]),
    )

    # 验证①样本外(按时间):≤2021 训练,≥2022 测试
    tr, te = (df["year"] <= OOT_CUT).to_numpy(), (df["year"] >= OOT_CUT + 1).to_numpy()
    oot_r2 = None
    oot_m = {}
    if tr.sum() > 30 and te.sum() > 10:
        xtr, xte = x_full[tr], x_full[te]
        kept_tr = select_features(xtr, y[tr], groups[tr], cols_all)  # 折内选特征,防泄漏
        g2 = fit_gbt(xtr[kept_tr], y[tr], kept_tr, params)
        oot_m = _metrics(y[te], g2.predict(xte[kept_tr]))
        oot_r2 = oot_m["r2"]

    # 验证②留一家(LOFO):用其它13家训,预测留出家
    pred = np.full(len(df), np.nan)
    for code in df["ts_code"].unique():
        m = (df["ts_code"] != code).to_numpy()
        if m.sum() < 30:
            continue
        kept_m = select_features(x_full[m], y[m], groups[m], cols_all)  # 折内选特征,防泄漏
        gf = fit_gbt(x_full[m][kept_m], y[m], kept_m, params)
        pred[~m] = gf.predict(x_full[~m][kept_m])
    ok = ~np.isnan(pred)
    lofo_m = _metrics(y[ok], pred[ok]) if ok.sum() > 20 else {}
    lofo_r2 = lofo_m.get("r2")

    insample_m = _metrics(y, gbt.predict(x_all))
    insample_r2 = insample_m["r2"]
    fe = fe_validate(df, cols, y)
    screen = screen_report(y, pred, ok, yw.to_numpy())  # 错误定价筛查:分类多指标 + 移为情绪缺口
    lcurve = learning_curve_data(x_all, y, groups, cols, params)  # 学习曲线(实验图)
    eda = eda_report(df, cols_all, cols, y)  # 探索性数据分析
    # LOFO 预测 vs 实际(实验散点图,评估页用):每点 = 一个公司-报告期的留出外推
    pred_actual = [
        {"a": round(float(y[i]), 3), "p": round(float(pred[i]), 3),
         "firm": df["firm"].iloc[i], "yw": bool(df["ts_code"].iloc[i] == YIWEI)}
        for i in range(len(df)) if ok[i]
    ]
    out = {
        "n_obs": len(df),
        "n_firms": int(df["ts_code"].nunique()),
        "year_min": int(df["year"].min()),
        "year_max": int(df["year"].max()),
        "target": "超额估值 = log(PS) 剥年度β+规模后的残差(公司特异溢价/折让)",
        "gbt_params": params,
        "n_features_all": len(cols_all),
        "n_features_selected": len(cols),
        "selected_features": [DRIVERS[c][0] for c in cols],
        "dropped_features": [DRIVERS[c][0] for c in cols_all if c not in cols],
        "insample_r2": insample_r2,
        "oot_r2": oot_r2,
        "lofo_r2": lofo_r2,
        "metrics": {"insample": insample_m, "oot": oot_m, "lofo": lofo_m},
        "unexplained_share": round(1 - (lofo_r2 or 0), 3),
        "shap_importance": imp,
        "elasticnet_coef": en_coef,
        "yiwei_attribution": yw_shap,
        "yiwei_excess_mean": round(float(y[yw.to_numpy()].mean()), 3),
        "firm_attribution": firm_attr,
        "fe_validation": fe,
        "mispricing_screen": screen,
        "learning_curve": lcurve,
        "eda": eda,
        "pred_actual": pred_actual,
        "l1_selection": l1_report(x_full, y, groups, cols_all),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"面板 {out['n_obs']} 行 × {out['n_firms']} 家 ({out['year_min']}-{out['year_max']})")
    print(
        f"解释力:样本内 R²={insample_r2} | 样本外 R²={oot_r2} | 留一家 R²={lofo_r2} | 不可解释≈{out['unexplained_share']}"
    )
    print("SHAP top5 驱动:", [(d["feat"], d["shap"]) for d in imp[:5]])
    print("\n驱动真伪(跨公司 vs 公司内FE,聚类SE):")
    for r in fe[:14]:
        print(
            f"  {r['feat']:12s} 跨公司{r['pooled']:+.2f}(p{r['pooled_p']:.2f}) 公司内{r['within']:+.2f}(p{r['within_p']:.2f}) → {r['verdict']}"
        )
    ym = out["yiwei_excess_mean"]
    print(
        f"移为超额估值均值={ym}({'>0=溢价' if ym > 0 else '<0=折让'});压低估值前3:",
        [(d["feat"], d["contrib"]) for d in yw_shap[:3]],
    )
    print("  抬高估值前3:", [(d["feat"], d["contrib"]) for d in yw_shap[-3:]])
    print("\n逐家估值驱动(溢价/折让 ← 抬高 vs 压低):")
    for f in firm_attr:
        tag = "溢价" if f["excess"] > 0 else "折让"
        print(
            f"  {f['firm']:6s} {tag}{f['excess']:+.2f} ← 抬:{f['lift'][0][0]}({f['lift'][0][1]:+}) 压:{f['drag'][0][0]}({f['drag'][0][1]:+})"
        )
    cls, ymp = screen["classification"], screen["yiwei_mispricing"]
    if cls:
        print(
            f"\n错误定价筛查(分类·LOFO外推):AUC={cls['auc']} 准确率={cls['accuracy']} "
            f"精确率={cls['precision']} 召回率={cls['recall']} F1={cls['f1']} 混淆={cls['confusion']}"
        )
    if ymp:
        print(
            f"移为错误定价:实际溢价{ymp['actual_excess']:+} 基本面应得{ymp['fundamental_justified']:+} "
            f"情绪缺口{ymp['sentiment_gap']:+}(基本面解释{ymp['explained_share']}、情绪{ymp['sentiment_share']})"
        )
    print("saved ->", OUT)


if __name__ == "__main__":
    import sys

    tune() if "tune" in sys.argv else main()

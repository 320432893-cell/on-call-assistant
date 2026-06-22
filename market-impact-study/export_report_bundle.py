"""Export data EDA + feature importance for the standard 8-section ML report (data/feature sections)."""

# 职责：为标准 ML 报告(八段)补 §2 数据EDA(样本/子类/年份/标签分布/缺失)+ §3 特征重要性(nuisance Y 模型 gain)= INV-030。
#       供仪表板报告段。因果版:学习曲线→nuisance诊断、特征重要性=去混淆里"什么预测了市值反应"。
# 不做什么：不做新因果估计;只产报告底层统计。
# 允许依赖层：标准库、numpy/pandas、lightgbm、cate_14firm 产物。
# 谁不应该 import：建模脚本不应 import 本入口。
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from lightgbm import LGBMRegressor

C = Path("market-impact-study/data/processed/modeling/cate_14firm")
OUT = C / "report_bundle.json"
# 与 analyze_capital_action_cate.py 同步:估值 + 价格技术 + 基本面(盈利/质量/杠杆) + 成长
FEAT = [
    "val_pct",
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
FEAT_CN = {
    "val_pct": "估值分位",
    "log_mv": "对数市值(规模)",
    "mom20": "20日动量",
    "mom60": "60日动量",
    "vol20": "20日波动",
    "turn20": "20日换手",
    "f_roe": "ROE",
    "f_roa": "ROA",
    "f_gross_margin": "毛利率",
    "f_net_margin": "净利率",
    "f_op_margin": "营业利润率",
    "f_debt_to_assets": "资产负债率",
    "f_current_ratio": "流动比率",
    "f_equity_mult": "权益乘数",
    "f_asset_turn": "资产周转率",
    "f_rd_intensity": "研发强度",
    "f_ocf_to_rev": "经营现金流/营收",
    "f_fcf_to_rev": "自由现金流/营收",
    "f_cash_to_assets": "现金/总资产",
    "f_ni_yoy": "净利同比",
    "rev_cagr2": "营收2年CAGR",
    "rev_cagr3": "营收3年CAGR",
}


def main() -> None:
    df = pd.read_csv(C / "cate_panel_14firm.csv")
    treated = df[df["D"] == 1]
    yr = df["trade_date"] // 10000
    rel = pd.to_numeric(df["rel"], errors="coerce") * 100
    # §2 数据 EDA
    sub = treated.groupby("subtype").agg(n=("rel", "size"), firms=("ts_code", "nunique")).reset_index()
    eda = {
        "n_total": len(df),
        "n_treated": int((df["D"] == 1).sum()),
        "n_control": int((df["D"] == 0).sum()),
        "n_firms": int(df["ts_code"].nunique()),
        "year_min": int(yr.min()),
        "year_max": int(yr.max()),
        "subtypes": [
            {"name": r["subtype"][:8], "n": int(r["n"]), "firms": int(r["firms"])}
            for _, r in sub.sort_values("n", ascending=False).iterrows()
        ],
        "y_mean": round(float(rel.mean()), 2),
        "y_std": round(float(rel.std()), 2),
        "y_q01": round(float(rel.quantile(0.01)), 1),
        "y_med": round(float(rel.median()), 2),
        "y_q99": round(float(rel.quantile(0.99)), 1),
        "y_pos_pct": round(float((rel > 0).mean()) * 100, 1),
        "y_neg_pct": round(float((rel < 0).mean()) * 100, 1),
        "missing": [
            {"feat": FEAT_CN[c], "miss_pct": round(float(pd.to_numeric(df[c], errors="coerce").isna().mean()) * 100, 1)}
            for c in FEAT
        ],
        "winsor": "训练前对 Y 做 1%/99% winsorize(去极端值);特征缺失用中位数填补",
    }
    # §3 特征重要性(nuisance Y 模型 = 去混淆里学"什么预测了市值反应")
    fit = df[df["val_pct"].notna()].copy()
    for c in FEAT:
        fit[c] = pd.to_numeric(fit[c], errors="coerce").fillna(fit[c].median())
    yv = pd.to_numeric(fit["rel"], errors="coerce")
    yv = yv.clip(yv.quantile(0.01), yv.quantile(0.99))
    m = LGBMRegressor(
        n_estimators=300,
        num_leaves=15,
        learning_rate=0.05,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=0,
        verbose=-1,
        importance_type="gain",
    )
    m.fit(fit[FEAT], yv)
    imp = m.feature_importances_.astype(float)
    imp = imp / imp.sum() * 100
    fi = sorted(
        [{"feat": FEAT_CN[f], "imp": round(float(v), 1)} for f, v in zip(FEAT, imp, strict=False)],
        key=lambda x: -x["imp"],
    )
    OUT.write_text(
        json.dumps({"eda": eda, "feat_importance": fi, "features": [FEAT_CN[f] for f in FEAT]}, ensure_ascii=False),
        encoding="utf-8",
    )
    print("EDA:", eda["n_treated"], "treated /", eda["n_control"], "control,", len(eda["subtypes"]), "subtypes")
    print("Y%: mean", eda["y_mean"], "std", eda["y_std"], "正", eda["y_pos_pct"], "% 负", eda["y_neg_pct"], "%")
    print("特征重要性:", [(f["feat"], f["imp"]) for f in fi])
    print("saved ->", OUT)


if __name__ == "__main__":
    main()

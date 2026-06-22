"""Export the transparent training process (learning curves, residualization, full feature table) for the dashboard."""

# 职责：把"黑箱训练过程"摊开给非专家看 = INV-033。对定增的去混淆模型,导出 ① nuisance LightGBM
#       逐轮学习曲线(train vs valid,看数字收敛)② 残差化抹掉了多少混淆方差(去混淆前后)
#       ③ 朴素 vs 去混淆斜率(怎么变)④ 全特征表(W/X 角色 + 重要性 + 缺失 + 取值域)。
# 不做什么：不做新因果断言;复用 cate_panel 与 analyze 同口径特征,只为透明化训练过程产数。
# 允许依赖层：标准库、numpy/pandas、lightgbm、sklearn、cate_14firm 产物。
# 谁不应该 import：建模/仪表板脚本不应 import 本入口,只读其 JSON。
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import cross_val_predict, train_test_split

C = Path("market-impact-study/data/processed/modeling/cate_14firm")
OUT = C / "training_process.json"
RNG = 0
TECH = ["log_mv", "mom20", "mom60", "vol20", "turn20"]
FUND_W = [
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
]
WCOLS = [*TECH, *FUND_W, "rev_cagr2", "rev_cagr3"]
XCF = ["val_pct", "log_mv", "f_roe", "f_debt_to_assets", "f_rd_intensity", "rev_cagr3"]
FEATS = [*WCOLS, "val_pct"]
CN = {
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
    "val_pct": "估值分位",
}


def ymodel() -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(
        n_estimators=300,
        num_leaves=15,
        learning_rate=0.05,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RNG,
        verbose=-1,
    )


def tmodel() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        n_estimators=300,
        num_leaves=15,
        learning_rate=0.05,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RNG,
        verbose=-1,
    )


def main() -> None:
    df = pd.read_csv(C / "cate_panel_14firm.csv")
    fit = df[df["val_pct"].notna()].copy()
    miss = {c: round(float(df[c].isna().mean()) * 100, 1) for c in FEATS}  # 缺失看原始(填补前)
    fit["rel"] = fit["rel"].clip(fit["rel"].quantile(0.01), fit["rel"].quantile(0.99))
    for c in FEATS:
        fit[c] = pd.to_numeric(fit[c], errors="coerce").fillna(fit[c].median())
    sub = fit[(fit["subtype"] == "定增/再融资") | (fit["D"] == 0)].copy()
    sub["t"] = (sub["subtype"] == "定增/再融资").astype(int)
    x, y, t = sub[FEATS].to_numpy(), sub["rel"].to_numpy(), sub["t"].to_numpy()

    # ① 学习曲线:train/valid 逐轮(看数字收敛)
    xtr, xva, ytr, yva, ttr, tva = train_test_split(x, y, t, test_size=0.25, random_state=RNG, stratify=t)
    my = ymodel()
    my.fit(xtr, ytr, eval_set=[(xtr, ytr), (xva, yva)], eval_metric="l2", callbacks=[lgb.log_evaluation(0)])
    yev = my.evals_result_
    mt = tmodel()
    mt.fit(xtr, ttr, eval_set=[(xtr, ttr), (xva, tva)], eval_metric="auc", callbacks=[lgb.log_evaluation(0)])
    tev = mt.evals_result_

    n_round = len(yev["training"]["l2"])
    step = max(1, n_round // 80)

    def thin(seq: list[float]) -> list[float]:
        return [round(float(v), 4) for v in seq[::step]]

    rounds = list(range(1, n_round + 1))[::step]
    y_curve = {"rounds": rounds, "train": thin(yev["training"]["l2"]), "valid": thin(yev["valid_1"]["l2"])}
    t_curve = {"rounds": rounds, "train": thin(tev["training"]["auc"]), "valid": thin(tev["valid_1"]["auc"])}

    # ② 残差化:去混淆抹掉了多少(交叉拟合 OOF)
    yhat = cross_val_predict(ymodel(), x, y, cv=5)
    that = cross_val_predict(tmodel(), x, t, cv=5, method="predict_proba")[:, 1]
    y_res, t_res = y - yhat, t - that
    y_r2 = round(float(r2_score(y, yhat)), 3)  # 市值反应可预测性(OOF,≈0=近不可预测,反应本就噪)
    auc_t = round(float(roc_auc_score(t, that)), 3)  # 倾向模型 AUC=做不做定增能被公司状态预测的程度(混淆强度)
    naive = float(np.polyfit(t, y, 1)[0]) * 100  # 朴素:直接回归斜率(含混淆)
    deconf = float(np.polyfit(t_res, y_res, 1)[0]) * 100  # 去混淆:残差对残差(混淆已抹掉)

    # ④ 真实数据样例(让公式落到具体数字):4 处理 + 4 对照事件
    rng2 = np.random.RandomState(RNG)
    pick = [
        *rng2.choice(np.where(t == 1)[0], 4, replace=False).tolist(),
        *rng2.choice(np.where(t == 0)[0], 4, replace=False).tolist(),
    ]
    col = {
        c: sub[c].to_numpy()
        for c in ("firm", "trade_date", "val_pct", "f_roe", "log_mv", "f_debt_to_assets", "rev_cagr3")
    }
    data_sample = [
        {
            "firm": col["firm"][i],
            "date": int(col["trade_date"][i]),
            "val_pct": round(float(col["val_pct"][i]), 2),
            "roe": round(float(col["f_roe"][i]), 1),
            "log_mv": round(float(col["log_mv"][i]), 1),
            "debt": round(float(col["f_debt_to_assets"][i]), 1),
            "cagr3": round(float(col["rev_cagr3"][i]), 1),
            "Y": round(float(y[i]) * 100, 2),
            "T": int(t[i]),
        }
        for i in pick
    ]
    residual_sample = [
        {
            "firm": col["firm"][i],
            "Y": round(float(y[i]) * 100, 2),
            "Yhat": round(float(yhat[i]) * 100, 2),
            "Yres": round(float(y_res[i]) * 100, 2),
            "T": int(t[i]),
            "That": round(float(that[i]), 3),
            "Tres": round(float(t_res[i]), 3),
        }
        for i in pick
    ]
    # ⑤ 逐事件可选(交互):全部定增 + 40对照,带 22 维特征向量,供"选中即看它过模型"
    ev_idx = [*np.where(t == 1)[0].tolist(), *rng2.choice(np.where(t == 0)[0], 40, replace=False).tolist()]
    events = [
        {
            "firm": col["firm"][i],
            "date": int(col["trade_date"][i]),
            "T": int(t[i]),
            "Y": round(float(y[i]) * 100, 2),
            "Yhat": round(float(yhat[i]) * 100, 2),
            "Yres": round(float(y_res[i]) * 100, 2),
            "p": round(float(that[i]), 3),
            "Tres": round(float(t_res[i]), 3),
            "feats": [round(float(v), 2) for v in x[i]],
        }
        for i in ev_idx
    ]
    feat_names = [CN[c] for c in FEATS]

    # ③ 全特征表:角色 + 重要性(Y模型gain)+ 缺失 + 取值域
    imp = my.booster_.feature_importance(importance_type="gain").astype(float)
    imp = imp / imp.sum() * 100
    feats = []
    for i, c in enumerate(FEATS):
        role = "X 效应修饰" if c in XCF else "W 混淆控制"
        if c in XCF and c in WCOLS:
            role = "W+X"
        feats.append(
            {
                "name": CN[c],
                "role": role,
                "imp": round(float(imp[i]), 1),
                "miss": miss[c],
                "lo": round(float(np.percentile(df[c].dropna(), 5)), 2) if df[c].notna().any() else None,
                "hi": round(float(np.percentile(df[c].dropna(), 95)), 2) if df[c].notna().any() else None,
            }
        )
    feats.sort(key=lambda f: -f["imp"])

    out = {
        "n_treated": int(t.sum()),
        "n_control": int((t == 0).sum()),
        "n_feat": len(FEATS),
        "y_curve": y_curve,
        "t_curve": t_curve,
        "residual": {
            "y_r2": y_r2,
            "propensity_auc": auc_t,
            "naive_slope": round(naive, 2),
            "deconf_slope": round(deconf, 2),
            "confound_removed": round(naive - deconf, 2),
        },
        "features": feats,
        "data_sample": data_sample,
        "residual_sample": residual_sample,
        "events": events,
        "feat_names": feat_names,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(
        f"学习曲线: Y l2 {y_curve['valid'][0]:.3f}→{y_curve['valid'][-1]:.3f}, T auc {t_curve['valid'][0]:.3f}→{t_curve['valid'][-1]:.3f}"
    )
    print(f"Y可预测性 R²={y_r2}(近0=反应噪);T倾向 AUC={auc_t}(高=强混淆);朴素 {naive:.2f}% → 去混淆 {deconf:.2f}%")
    print(f"特征 {len(feats)} 个,top:", [(f["name"], f["imp"]) for f in feats[:4]])
    print("saved ->", OUT)


if __name__ == "__main__":
    main()

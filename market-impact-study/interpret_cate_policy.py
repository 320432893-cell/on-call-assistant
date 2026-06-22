# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Collapse the 定增 causal forest into readable CATE + policy trees (interpretable causal output)."""

# 职责：把 INV-016/017 的定增因果森林用 econml 解释器塌成两棵可读浅树 = INV-018:
#       ① CATE 树(效应多大,随估值/规模/成长怎么变);② 策略树(谁该做定增 do/don't)。
#       附每叶处理样本数作诚实警示(边际效应、极端叶子样本稀薄)。读已落盘 cate_panel,不改主估计。
# 不做什么：不重估 ATE/不做新推断;只解释已有因果森林。
# 运行环境：隔离 venv `.venv-causal`(econml);`.venv-causal/bin/python market-impact-study/interpret_cate_policy.py`。
# 允许依赖层：标准库、numpy/pandas、lightgbm、econml、sklearn、cate_14firm 产物。
# 谁不应该 import：主流程/建模脚本不应 import 本入口(依赖隔离 venv)。
from __future__ import annotations

from pathlib import Path

import pandas as pd
from econml.cate_interpreter import SingleTreeCateInterpreter, SingleTreePolicyInterpreter
from econml.dml import CausalForestDML
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.tree import export_text

CATE_DIR = Path("market-impact-study/data/processed/modeling/cate_14firm")
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
XCOLS = ["val_pct", "log_mv", "f_roe", "f_debt_to_assets", "f_rd_intensity", "rev_cagr3"]
ACTION = "定增/再融资"
RNG = 0


def nuis_y() -> LGBMRegressor:
    return LGBMRegressor(
        n_estimators=300, num_leaves=15, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1
    )


def nuis_t() -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=300, num_leaves=15, learning_rate=0.05, min_child_samples=30, random_state=RNG, verbose=-1
    )


def main() -> None:
    df = pd.read_csv(CATE_DIR / "cate_panel_14firm.csv")
    df = df[df["val_pct"].notna()].copy()
    df["rel"] = df["rel"].clip(df["rel"].quantile(0.01), df["rel"].quantile(0.99))
    for c in WCOLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(df[c].median())
    sub = df[(df["subtype"] == ACTION) | (df["D"] == 0)].copy()
    sub["D"] = (sub["subtype"] == ACTION).astype(int)
    y, t = sub["rel"].to_numpy(), sub["D"].to_numpy()
    x, w = sub[XCOLS].to_numpy(), sub[WCOLS].to_numpy()

    cf = CausalForestDML(
        model_y=nuis_y(),
        model_t=nuis_t(),
        discrete_treatment=True,
        n_estimators=800,
        min_samples_leaf=20,
        cv=4,
        random_state=RNG,
    )
    cf.fit(y, t, X=x, W=w)

    lines: list[str] = [
        "定增 因果森林可读化(INV-018) — 诚实警示:定增整体仅边际显著(INV-017 簇bootstrap p≈0.11),",
        "下面的树是沟通工具/方向性,不是坐实的政策;尤其看每叶处理事件数(treated)。",
        "",
    ]

    cate = SingleTreeCateInterpreter(include_model_uncertainty=True, max_depth=2, min_samples_leaf=40)
    cate.interpret(cf, x)
    lines.append("=== CATE 树:定增效应(%)随公司因素怎么变(叶值=该格定增的相对反应) ===")
    lines.append(export_text(cate.tree_model_, feature_names=XCOLS, show_weights=True))
    leaf = cate.tree_model_.apply(x)
    sub2 = sub.assign(leaf=leaf)
    lines.append("每叶样本:")
    for lf in sorted(set(leaf)):
        g = sub2[sub2["leaf"] == lf]
        cate_pct = float(cate.tree_model_.tree_.value[lf].ravel()[0]) * 100
        lines.append(
            f"  leaf{lf}: CATE={cate_pct:+.2f}%  n={len(g)}  treated={int(g['D'].sum())}  "
            f"估值分位均值={g['val_pct'].mean():.2f}  log市值均值={g['log_mv'].mean():.2f}"
        )

    policy = SingleTreePolicyInterpreter(risk_level=0.1, max_depth=2, min_samples_leaf=40)
    policy.interpret(cf, x)
    lines.append("\n=== 策略树:谁该做定增(class 1=建议/0=不建议) ===")
    lines.append(export_text(policy.tree_model_, feature_names=XCOLS, show_weights=True))
    lines.append("读法:低估值分位(≈底部20%)→ 建议;估值更高 → 不建议(高估值高成长时尤其不划算)。")

    out = "\n".join(lines)
    (CATE_DIR / "cate_interpretation.txt").write_text(out, encoding="utf-8")
    print(out)
    print(f"\nsaved -> {CATE_DIR}/cate_interpretation.txt")


if __name__ == "__main__":
    main()

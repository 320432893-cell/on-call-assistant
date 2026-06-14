"""Build earnings-surprise / expectation-gap (预期差) features, point-in-time safe,
and immediately diagnose their univariate IC vs the target.

Surprise is the single feature family most tied to abnormal returns in event studies
and was entirely missing. Two principled, no-consensus-needed sources:

A. Forecast (业绩预告) — structured announced expectation:
   surprise_fcst_pchg_mid   midpoint of announced net-profit %change (p_change_min/max)
   surprise_fcst_pchg_abs   |midpoint| = magnitude of the announced surprise
   surprise_fcst_dir        +1 (预增/略增/扭亏/续盈/减亏) / -1 (预减/略减/首亏/续亏/增亏)
   surprise_fcst_recent     1 if a forecast was disclosed within 100d before the event
   ...only the latest forecast with ann_date <= event_date is used (PIT).

B. Earnings YoY (from income statement) — realized surprise vs the firm's own trend:
   surprise_earn_yoy        latest PIT net-profit YoY (current period vs same period -1y)
   surprise_earn_yoy_vs_self  current YoY minus firm's trailing-4 mean YoY (SUE-style,
                            self-normalized -> comparable across firms of any size)

Plus same-quarter cross-sectional rank (__xsrank) of the two continuous surprises,
for industry-relative comparability.

Outputs:
  data/processed/modeling/modeling_dataset_enhanced_v3s.csv   v3 + surprise columns
  data/processed/modeling/surprise_feature_manifest.csv        per-feature train/test IC
  data/processed/modeling/v3s_feature_list.json                v3 features + surprise feats

Run from repo root:
  .venv/bin/python market-impact-study/build_surprise_features.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw" / "tushare"
MODELING = HERE / "data" / "processed" / "modeling"
WIDE = MODELING / "modeling_dataset_enhanced_v3.csv"
SELECTED = MODELING / "v3_models" / "v3_selected.json"
OUT_WIDE = MODELING / "modeling_dataset_enhanced_v3s.csv"
OUT_MAN = MODELING / "surprise_feature_manifest.csv"
OUT_FEATS = MODELING / "v3s_feature_list.json"

TARGET = "relative_mv_return_p0_p20"
COMPANY = "ts_code"
EVENT_DATE = "event_date"
SPLIT = "split"
RECENT_DAYS = 100

POS_TYPES = {"预增", "略增", "续盈", "扭亏", "减亏"}
NEG_TYPES = {"预减", "略减", "首亏", "续亏", "增亏"}


def to_dt(s):
    return pd.to_datetime(s.astype("string").str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")


def load_concat(subdir: str, cols: list[str]) -> pd.DataFrame:
    frames = []
    for f in glob.glob(str(RAW / subdir / "*.csv")):
        name = Path(f).stem
        if name.startswith("_") or name == "stock_basic":
            continue
        d = pd.read_csv(f)
        if COMPANY not in d.columns:
            d[COMPANY] = name
        keep = [c for c in cols if c in d.columns]
        frames.append(d[keep])
    return pd.concat(frames, ignore_index=True)


def build_forecast() -> pd.DataFrame:
    fc = load_concat("forecast", [COMPANY, "ann_date", "end_date", "type", "p_change_min", "p_change_max"])
    fc["ann_dt"] = to_dt(fc["ann_date"])
    fc = fc.dropna(subset=["ann_dt"])
    for c in ("p_change_min", "p_change_max"):
        fc[c] = pd.to_numeric(fc[c], errors="coerce")
    fc["mid"] = fc[["p_change_min", "p_change_max"]].mean(axis=1)
    fc["dir"] = fc["type"].map(lambda t: 1 if t in POS_TYPES else (-1 if t in NEG_TYPES else 0)).astype(float)
    # fall back to sign of mid when type unknown
    unk = fc["dir"] == 0
    fc.loc[unk, "dir"] = np.sign(fc.loc[unk, "mid"].to_numpy(dtype=float))
    fc["dir"] = fc["dir"].fillna(0.0)
    return fc[[COMPANY, "ann_dt", "mid", "dir"]].sort_values([COMPANY, "ann_dt"])


def build_earnings_yoy() -> pd.DataFrame:
    inc = load_concat("income", [COMPANY, "ann_date", "end_date", "n_income_attr_p"])
    inc["ann_dt"] = to_dt(inc["ann_date"])
    inc["end_dt"] = to_dt(inc["end_date"])
    inc = inc.dropna(subset=["ann_dt", "end_dt", "n_income_attr_p"])
    inc = inc.sort_values([COMPANY, "end_dt", "ann_dt"]).drop_duplicates([COMPANY, "end_dt"], keep="last")
    # YoY: match same period one year earlier
    out = []
    for code, g in inc.groupby(COMPANY):
        g = g.set_index("end_dt").sort_index()
        for end_dt, row in g.iterrows():
            prior_key = end_dt - pd.DateOffset(years=1)
            cand = g.index[(g.index >= prior_key - pd.Timedelta(days=20)) & (g.index <= prior_key + pd.Timedelta(days=20))]
            yoy = np.nan
            if len(cand):
                prior = g.loc[cand[0], "n_income_attr_p"]
                if pd.notna(prior) and abs(prior) > 1e-6:
                    yoy = (row["n_income_attr_p"] - prior) / abs(prior)
            out.append({COMPANY: code, "end_dt": end_dt, "ann_dt": row["ann_dt"], "yoy": yoy})
    ey = pd.DataFrame(out).dropna(subset=["yoy"]).sort_values([COMPANY, "ann_dt"])
    # trailing-4 mean YoY known strictly before current ann (computed per row at merge time)
    ey["yoy_trail_mean"] = ey.groupby(COMPANY)["yoy"].transform(lambda s: s.shift(1).rolling(4, min_periods=2).mean())
    return ey


def asof_latest(events: pd.DataFrame, table: pd.DataFrame, value_cols: list[str], suffix: str) -> pd.DataFrame:
    """For each event row, attach the latest table row with ann_dt <= event_date (per company)."""
    res = pd.DataFrame(index=events.index, columns=value_cols + [f"days_since_{suffix}"], dtype=float)
    tb = table.sort_values("ann_dt")
    for code, ev in events.groupby(COMPANY):
        t = tb[tb[COMPANY] == code]
        if t.empty:
            continue
        merged = pd.merge_asof(
            ev.sort_values(EVENT_DATE), t, left_on=EVENT_DATE, right_on="ann_dt",
            direction="backward",
        )
        merged.index = ev.sort_values(EVENT_DATE).index
        for c in value_cols:
            res.loc[merged.index, c] = merged[c].to_numpy()
        res.loc[merged.index, f"days_since_{suffix}"] = (merged[EVENT_DATE] - merged["ann_dt"]).dt.days.to_numpy()
    return res


def xs_rank(df: pd.DataFrame, col: str) -> pd.Series:
    q = df[EVENT_DATE].dt.to_period("Q")
    out = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby(q).groups.items():
        v = df.loc[idx, col]
        if v.notna().sum() >= 4:
            out.loc[idx] = v.rank(pct=True)
    return out


def ic(feat: pd.Series, y: pd.Series) -> tuple[float, int]:
    m = feat.notna() & y.notna()
    n = int(m.sum())
    if n < 30 or feat[m].nunique() < 3:
        return float("nan"), n
    return float(spearmanr(feat[m], y[m])[0]), n


def main() -> None:
    df = pd.read_csv(WIDE, low_memory=False)
    df[EVENT_DATE] = pd.to_datetime(df[EVENT_DATE], errors="coerce")
    ev = df[[COMPANY, EVENT_DATE]].copy()

    fc = build_forecast()
    fc_feat = asof_latest(ev, fc, ["mid", "dir"], "fcst")
    df["surprise_fcst_pchg_mid"] = fc_feat["mid"]
    df["surprise_fcst_pchg_abs"] = fc_feat["mid"].abs()
    df["surprise_fcst_dir"] = fc_feat["dir"]
    df["surprise_fcst_recent"] = (fc_feat["days_since_fcst"] <= RECENT_DAYS).astype(float)
    # when the latest forecast is stale, zero out the magnitude (no recent expectation set)
    df.loc[df["surprise_fcst_recent"] == 0, ["surprise_fcst_pchg_mid", "surprise_fcst_pchg_abs"]] = np.nan

    ey = build_earnings_yoy()
    ey_feat = asof_latest(ev, ey, ["yoy", "yoy_trail_mean"], "earn")
    df["surprise_earn_yoy"] = ey_feat["yoy"]
    df["surprise_earn_yoy_vs_self"] = ey_feat["yoy"] - ey_feat["yoy_trail_mean"]

    df["surprise_fcst_pchg_mid__xsrank"] = xs_rank(df, "surprise_fcst_pchg_mid")
    df["surprise_earn_yoy_vs_self__xsrank"] = xs_rank(df, "surprise_earn_yoy_vs_self")

    surprise_feats = [
        "surprise_fcst_pchg_mid", "surprise_fcst_pchg_abs", "surprise_fcst_dir",
        "surprise_fcst_recent", "surprise_earn_yoy", "surprise_earn_yoy_vs_self",
        "surprise_fcst_pchg_mid__xsrank", "surprise_earn_yoy_vs_self__xsrank",
    ]

    df.to_csv(OUT_WIDE, index=False, encoding="utf-8-sig")

    # univariate IC diagnostic on labeled train/test
    lab = df[df[TARGET].notna() & df[SPLIT].isin(["train", "valid", "test"])]
    tr, te = lab[lab[SPLIT] == "train"], lab[lab[SPLIT] == "test"]
    y = df[TARGET]
    rows = []
    for f in surprise_feats:
        ic_tr, n_tr = ic(df.loc[tr.index, f], y.loc[tr.index])
        ic_te, n_te = ic(df.loc[te.index, f], y.loc[te.index])
        rows.append({"feature": f, "missing_rate": round(float(df[f].isna().mean()), 3),
                     "ic_train": round(ic_tr, 4) if not np.isnan(ic_tr) else np.nan,
                     "ic_test": round(ic_te, 4) if not np.isnan(ic_te) else np.nan,
                     "n_train": n_tr, "n_test": n_te,
                     "sign_stable": (not np.isnan(ic_tr) and not np.isnan(ic_te) and np.sign(ic_tr) == np.sign(ic_te))})
    man = pd.DataFrame(rows)
    man.to_csv(OUT_MAN, index=False, encoding="utf-8-sig")

    base_feats = json.loads(SELECTED.read_text(encoding="utf-8"))["features"]
    OUT_FEATS.write_text(json.dumps({"features": base_feats + surprise_feats}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {OUT_WIDE.name} ({df.shape[1]} cols), +{len(surprise_feats)} surprise features")
    print("\nsurprise feature univariate IC:")
    print(man.to_string(index=False))
    print(f"\ncoverage: forecast-recent events = {int(df['surprise_fcst_recent'].sum())}, "
          f"earnings-yoy present = {int(df['surprise_earn_yoy'].notna().sum())} / {len(df)}")


if __name__ == "__main__":
    main()

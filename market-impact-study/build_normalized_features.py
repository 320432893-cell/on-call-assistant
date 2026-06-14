"""Build scale-free / industry-relative variants of the modeling features and
diagnose whether the normalized representations carry more stable out-of-sample
signal than the raw levels.

For every continuous base feature f we derive up to four point-in-time-safe
variants, each aimed at making heterogeneous firms (very different size) live in
a common, industry-relative feature space:

  f__selfz   within-company trailing z-score, using only that company's PRIOR
             event rows (expanding mean/std shifted by one). Removes the firm's
             own level; keeps the deviation from its own history.
  f__yoy     within-company change vs the nearest prior event ~1 year earlier
             (event_date in [t-420d, t-300d]); pct change. Captures YoY dynamics.
  f__xsrank  cross-sectional percentile rank within the same calendar quarter
             across the peer set [0,1]. Puts a 50bn and a 5bn firm on one scale.
  f__xsdemed feature minus the same-quarter cross-sectional median.

Then we compute univariate Spearman IC of each base feature AND each variant
against the target on the labeled train set and (held-out) test set, and report
whether the normalized variants are more sign-stable / higher |test IC| than raw.

Outputs (under data/processed/modeling/):
  modeling_dataset_enhanced_v3.csv     wide table = enhanced_v2 + derived variants
  normalized_feature_manifest.csv      per (feature, representation) IC diagnostics

Run from repo root:
  .venv/bin/python market-impact-study/build_normalized_features.py
Caveat (documented): f__xsrank/f__xsdemed rank peers by their own event-date
snapshot inside the quarter, so there is up to ~1 quarter of within-bucket
look-ahead. This is a first-pass diagnostic; a strict version would snapshot all
peers as-of date t from the raw daily series.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
MODELING = HERE / "data" / "processed" / "modeling"
WIDE_PATH = MODELING / "modeling_dataset_enhanced_v2.csv"
REGISTRY_PATH = MODELING / "baseline_models" / "baseline_registry.json"
OUT_WIDE = MODELING / "modeling_dataset_enhanced_v3.csv"
OUT_MANIFEST = MODELING / "normalized_feature_manifest.csv"

TARGET = "relative_mv_return_p0_p20"
COMPANY = "ts_code"
EVENT_DATE = "event_date"
SPLIT = "split"
EPS = 1e-9
MIN_SELFZ_PRIOR = 3      # need >=3 prior obs for a trailing std
MIN_XS_GROUP = 4         # need >=4 firms in a quarter to rank cross-sectionally
IC_THRESHOLD = 0.03      # |test IC| considered non-trivial
MIN_EFF_N = 200          # ignore IC built on a tiny effective sample


def load_base_features() -> list[str]:
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    return list(reg["features"])


def is_continuous(series: pd.Series) -> bool:
    s = series.dropna()
    if s.empty:
        return False
    # skip binary / low-cardinality flags (one-hot, *_is_*, *_has_*): normalizing them is meaningless
    return s.nunique() > 5


def selfz(df: pd.DataFrame, col: str) -> pd.Series:
    g = df.groupby(COMPANY)[col]
    mean_prior = g.transform(lambda x: x.expanding().mean().shift(1))
    std_prior = g.transform(lambda x: x.expanding().std().shift(1))
    cnt_prior = g.transform(lambda x: x.expanding().count().shift(1))
    z = (df[col] - mean_prior) / std_prior.replace(0, np.nan)
    z[cnt_prior < MIN_SELFZ_PRIOR] = np.nan
    return z


def yoy(df: pd.DataFrame, col: str) -> pd.Series:
    out = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby(COMPANY).groups.items():
        sub = df.loc[idx, [EVENT_DATE, col]].dropna(subset=[col])
        if len(sub) < 2:
            continue
        dates = sub[EVENT_DATE].to_numpy()
        vals = sub[col].to_numpy()
        for i in range(len(sub)):
            t = dates[i]
            lo = t - np.timedelta64(420, "D")
            hi = t - np.timedelta64(300, "D")
            mask = (dates >= lo) & (dates <= hi)
            if not mask.any():
                continue
            # nearest to t-365
            cand = np.where(mask)[0]
            target_day = t - np.timedelta64(365, "D")
            j = cand[np.argmin(np.abs(dates[cand] - target_day))]
            prior = vals[j]
            out.loc[sub.index[i]] = (vals[i] - prior) / (abs(prior) + EPS)
    return out


def xs_quarter(df: pd.DataFrame, col: str) -> tuple[pd.Series, pd.Series]:
    q = df[EVENT_DATE].dt.to_period("Q")
    rank = pd.Series(np.nan, index=df.index)
    demed = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby(q).groups.items():
        vals = df.loc[idx, col]
        if vals.notna().sum() < MIN_XS_GROUP:
            continue
        rank.loc[idx] = vals.rank(pct=True)
        demed.loc[idx] = vals - vals.median()
    return rank, demed


def ic(feat: pd.Series, target: pd.Series) -> tuple[float, int]:
    mask = feat.notna() & target.notna()
    n = int(mask.sum())
    if n < 30 or feat[mask].nunique() < 3:
        return float("nan"), n
    rho, _ = spearmanr(feat[mask], target[mask])
    return float(rho), n


def main() -> None:
    df = pd.read_csv(WIDE_PATH)
    df[EVENT_DATE] = pd.to_datetime(df[EVENT_DATE], errors="coerce")
    df = df.sort_values([COMPANY, EVENT_DATE]).reset_index(drop=True)

    base_features = [f for f in load_base_features() if f in df.columns]
    cont = [f for f in base_features if is_continuous(df[f])]
    print(f"base features: {len(base_features)}, continuous (normalized): {len(cont)}")

    derived: dict[str, pd.Series] = {}
    for f in cont:
        derived[f"{f}__selfz"] = selfz(df, f)
        derived[f"{f}__yoy"] = yoy(df, f)
        r, m = xs_quarter(df, f)
        derived[f"{f}__xsrank"] = r
        derived[f"{f}__xsdemed"] = m

    derived_df = pd.DataFrame(derived, index=df.index)
    wide_v3 = pd.concat([df, derived_df], axis=1)
    wide_v3.to_csv(OUT_WIDE, index=False, encoding="utf-8-sig")
    print(f"wrote {OUT_WIDE.name}: {wide_v3.shape[0]} rows, {wide_v3.shape[1]} cols")

    labeled = df[df[TARGET].notna() & df[SPLIT].isin(["train", "valid", "test"])]
    tr = labeled[labeled[SPLIT] == "train"].index
    te = labeled[labeled[SPLIT] == "test"].index
    y = df[TARGET]

    rows = []
    all_cols = {f: df[f] for f in cont}
    all_cols.update(derived)
    base_of = {}
    for f in cont:
        base_of[f] = f
        for v in ("selfz", "yoy", "xsrank", "xsdemed"):
            base_of[f"{f}__{v}"] = f

    for col, series in all_cols.items():
        rep = "raw" if "__" not in col else col.split("__", 1)[1]
        ic_tr, n_tr = ic(series.loc[tr], y.loc[tr])
        ic_te, n_te = ic(series.loc[te], y.loc[te])
        stable = (
            not np.isnan(ic_tr)
            and not np.isnan(ic_te)
            and np.sign(ic_tr) == np.sign(ic_te)
            and abs(ic_te) >= IC_THRESHOLD
            and n_te >= MIN_EFF_N
        )
        rows.append(
            {
                "base_feature": base_of[col],
                "representation": rep,
                "column": col,
                "missing_rate": round(float(series.isna().mean()), 4),
                "ic_train": round(ic_tr, 4) if not np.isnan(ic_tr) else np.nan,
                "ic_test": round(ic_te, 4) if not np.isnan(ic_te) else np.nan,
                "n_train": n_tr,
                "n_test": n_te,
                "sign_stable_nontrivial": bool(stable),
            }
        )

    man = pd.DataFrame(rows).sort_values(
        ["sign_stable_nontrivial", "ic_test"], ascending=[False, False], key=lambda s: s.abs() if s.name == "ic_test" else s
    )
    man.to_csv(OUT_MANIFEST, index=False, encoding="utf-8-sig")
    print(f"wrote {OUT_MANIFEST.name}: {len(man)} (feature,representation) rows")

    # ---- summary ----
    print("\n=== sign-stable, non-trivial (|test IC|>=%.2f, n_test>=%d) by representation ===" % (IC_THRESHOLD, MIN_EFF_N))
    summ = (
        man.groupby("representation")
        .agg(
            candidates=("column", "count"),
            stable=("sign_stable_nontrivial", "sum"),
            mean_abs_test_ic_stable=("ic_test", lambda s: round(s[man.loc[s.index, "sign_stable_nontrivial"]].abs().mean(), 4) if man.loc[s.index, "sign_stable_nontrivial"].any() else np.nan),
        )
        .reset_index()
        .sort_values("stable", ascending=False)
    )
    print(summ.to_string(index=False))

    print("\n=== per-base-feature: does any normalized variant beat raw on stable |test IC|? ===")
    wins = {"raw_best": 0, "normalized_best": 0, "none_stable": 0}
    detail = []
    for bf, grp in man.groupby("base_feature"):
        stable_grp = grp[grp["sign_stable_nontrivial"]]
        if stable_grp.empty:
            wins["none_stable"] += 1
            continue
        best = stable_grp.loc[stable_grp["ic_test"].abs().idxmax()]
        if best["representation"] == "raw":
            wins["raw_best"] += 1
        else:
            wins["normalized_best"] += 1
        detail.append((bf, best["representation"], best["ic_test"], best["ic_train"]))
    print(wins)
    print("\ntop stable winners (base_feature, best_rep, test_ic, train_ic):")
    for d in sorted(detail, key=lambda x: -abs(x[2]))[:25]:
        print(f"  {d[0]:<34} {d[1]:<9} test={d[2]:+.4f} train={d[3]:+.4f}")


if __name__ == "__main__":
    main()

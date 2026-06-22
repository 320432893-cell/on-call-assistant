"""构造第二层 point-in-time 结构化特征。

唯一职责：基于 reviewed 建模宽表追加交易、估值、财务、管理层滚动和同行环境特征。
不做什么：不改 SSOT；不训练模型；不使用事件后窗口或标签字段作为特征。
允许依赖的层：只读取 raw/tushare、processed/management 和 reviewed 建模宽表。
谁不应 import：训练脚本不应 import 本脚本；应直接读取输出的 enhanced 宽表。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW_TUSHARE_DIR = Path("market-impact-study/data/raw/tushare")
MANAGEMENT_LEDGER_PATH = Path("market-impact-study/data/processed/management/management_signal_ledger.csv")
MODELING_DIR = Path("market-impact-study/data/processed/modeling")
DOC_REPORTS_DIR = Path("market-impact-study/docs/reports")

INPUT_PATH = MODELING_DIR / "modeling_dataset_reviewed_v1.csv"
OUTPUT_PATH = MODELING_DIR / "modeling_dataset_enhanced_v1.csv"
FEATURE_MANIFEST_PATH = MODELING_DIR / "enhanced_feature_manifest.csv"
REPORT_PATH = DOC_REPORTS_DIR / "ENHANCED_FEATURES_SUMMARY.md"

TRADING_WINDOWS = [5, 20, 60]
MANAGEMENT_WINDOWS = [30, 90, 180]
MARKET_INDEX = "399006.SZ"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少输入文件：{path}")
    return pd.read_csv(path)


def parse_yyyymmdd(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")


def read_company_panel(subdir: str) -> pd.DataFrame:
    frames = []
    for path in sorted((RAW_TUSHARE_DIR / subdir).glob("*.csv")):
        frame = pd.read_csv(path)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_daily_panel() -> pd.DataFrame:
    daily = read_company_panel("daily")
    basic = read_company_panel("daily_basic")
    daily["trade_dt"] = parse_yyyymmdd(daily["trade_date"])
    basic["trade_dt"] = parse_yyyymmdd(basic["trade_date"])
    daily["ret"] = pd.to_numeric(daily["pct_chg"], errors="coerce") / 100
    basic_cols = ["ts_code", "trade_dt", "turnover_rate", "volume_ratio", "pe", "pb", "ps", "total_mv", "circ_mv"]
    panel = daily.merge(basic[basic_cols], on=["ts_code", "trade_dt"], how="left")
    numeric = [
        "ret",
        "amount",
        "vol",
        "turnover_rate",
        "volume_ratio",
        "pe",
        "pb",
        "ps",
        "total_mv",
        "circ_mv",
    ]
    for column in numeric:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    return panel.sort_values(["ts_code", "trade_dt"]).reset_index(drop=True)


def load_index_panel() -> pd.DataFrame:
    path = RAW_TUSHARE_DIR / "index_daily" / f"{MARKET_INDEX}.csv"
    index = read_csv(path)
    index["trade_dt"] = parse_yyyymmdd(index["trade_date"])
    index["index_ret"] = pd.to_numeric(index["pct_chg"], errors="coerce") / 100
    index = index.sort_values("trade_dt")
    for window in TRADING_WINDOWS:
        index[f"mkt_ret_m{window}_m1"] = (
            index["index_ret"].rolling(window, min_periods=max(2, window // 2)).sum().shift(1)
        )
    return index[["trade_dt", *[f"mkt_ret_m{window}_m1" for window in TRADING_WINDOWS]]]


def add_trading_features(panel: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for _, group in panel.groupby("ts_code", sort=False):
        group = group.sort_values("trade_dt").copy()
        for window in TRADING_WINDOWS:
            min_periods = max(2, window // 2)
            group[f"ret_m{window}_m1"] = group["ret"].rolling(window, min_periods=min_periods).sum().shift(1)
            group[f"volatility_m{window}_m1"] = group["ret"].rolling(window, min_periods=min_periods).std().shift(1)
            group[f"turnover_avg_m{window}_m1"] = (
                group["turnover_rate"].rolling(window, min_periods=min_periods).mean().shift(1)
            )
            group[f"amount_avg_m{window}_m1"] = group["amount"].rolling(window, min_periods=min_periods).mean().shift(1)
        for column in ["pe", "pb", "ps", "total_mv", "circ_mv", "volume_ratio"]:
            group[f"{column}_pre"] = group[column].shift(1)
        group["log_total_mv_pre"] = np.log(group["total_mv_pre"].where(group["total_mv_pre"] > 0))
        pieces.append(group)
    return pd.concat(pieces, ignore_index=True)


def add_peer_features(panel: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [
        *[f"ret_m{window}_m1" for window in TRADING_WINDOWS],
        *[f"turnover_avg_m{window}_m1" for window in TRADING_WINDOWS],
        "pe_pre",
        "pb_pre",
        "ps_pre",
        "log_total_mv_pre",
    ]
    peer = panel[["ts_code", "trade_dt", *feature_cols]].copy()
    for column in feature_cols:
        peer[f"peer_avg_{column}"] = peer.groupby("trade_dt")[column].transform(
            lambda values: (
                (values.sum(skipna=True) - values) / (values.notna().sum() - values.notna()).replace(0, np.nan)
            )
        )
        peer[f"rel_to_peer_{column}"] = peer[column] - peer[f"peer_avg_{column}"]
    return peer[
        [
            "ts_code",
            "trade_dt",
            *[column for column in peer.columns if column.startswith(("peer_avg_", "rel_to_peer_"))],
        ]
    ]


def asof_by_company(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_on: str,
    right_on: str,
    allow_exact_matches: bool,
) -> pd.DataFrame:
    pieces = []
    for ts_code, left_group in left.groupby("ts_code", sort=False):
        right_group = right[right["ts_code"] == ts_code].sort_values(right_on)
        if right_group.empty:
            empty = left_group.copy()
            for column in right.columns:
                if column not in empty.columns:
                    empty[column] = np.nan
            pieces.append(empty)
            continue
        pieces.append(
            pd.merge_asof(
                left_group.sort_values(left_on),
                right_group,
                left_on=left_on,
                right_on=right_on,
                direction="backward",
                allow_exact_matches=allow_exact_matches,
                suffixes=("", "_right"),
            )
        )
    return pd.concat(pieces, ignore_index=True)


def nearest_prior_trade_features(events: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    left = events[["analysis_group_id", "ts_code", "event_date"]].copy()
    left["event_dt"] = pd.to_datetime(left["event_date"], errors="coerce")
    left = left.sort_values(["ts_code", "event_dt"])
    right = panel.sort_values(["ts_code", "trade_dt"])
    merged = asof_by_company(
        left,
        right,
        left_on="event_dt",
        right_on="trade_dt",
        allow_exact_matches=False,
    )
    return merged.drop(columns=["event_dt"])


def load_financial_table(subdir: str, columns: list[str]) -> pd.DataFrame:
    frame = read_company_panel(subdir)
    if frame.empty:
        return frame
    keep = ["ts_code", "ann_date", "end_date", *columns]
    frame = frame[[column for column in keep if column in frame.columns]].copy()
    frame["ann_dt"] = parse_yyyymmdd(frame["ann_date"])
    frame["end_dt"] = parse_yyyymmdd(frame["end_date"])
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["ts_code", "ann_dt", "end_dt"])


def add_financial_features(events: pd.DataFrame) -> pd.DataFrame:
    fina = load_financial_table(
        "fina_indicator",
        ["roe", "roa", "grossprofit_margin", "netprofit_margin", "rd_exp", "ocfps", "bps"],
    )
    income = load_financial_table("income", ["total_revenue", "n_income_attr_p"])
    balance = load_financial_table(
        "balancesheet",
        ["total_assets", "total_liab", "total_hldr_eqy_inc_min_int", "total_cur_assets", "total_cur_liab"],
    )
    cashflow = load_financial_table("cashflow", ["n_cashflow_act", "c_cash_equ_end_period"])

    left = events[["analysis_group_id", "ts_code", "event_date"]].copy()
    left["event_dt"] = pd.to_datetime(left["event_date"], errors="coerce")
    left = left.sort_values(["ts_code", "event_dt"])

    def join_latest(frame: pd.DataFrame, suffix: str) -> pd.DataFrame:
        if frame.empty:
            return left[["analysis_group_id"]].copy()
        right = frame.sort_values(["ts_code", "ann_dt"])
        joined = asof_by_company(
            left,
            right,
            left_on="event_dt",
            right_on="ann_dt",
            allow_exact_matches=True,
        )
        rename = {
            column: f"{suffix}_{column}"
            for column in joined.columns
            if column
            not in {"analysis_group_id", "ts_code", "event_date", "event_dt", "ann_dt", "ann_date", "end_date"}
        }
        joined = joined.rename(columns=rename)
        return joined[["analysis_group_id", *rename.values()]]

    output = left[["analysis_group_id"]].copy()
    for suffix, frame in [("fin", fina), ("inc", income), ("bal", balance), ("cf", cashflow)]:
        output = output.merge(join_latest(frame, suffix), on="analysis_group_id", how="left")

    output["fin_days_since_report"] = (
        pd.to_datetime(left["event_date"], errors="coerce").reset_index(drop=True)
        - pd.to_datetime(output.get("fin_end_dt"), errors="coerce")
    ).dt.days
    output["bal_liability_to_assets"] = output["bal_total_liab"] / output["bal_total_assets"].replace(0, np.nan)
    output["bal_current_ratio"] = output["bal_total_cur_assets"] / output["bal_total_cur_liab"].replace(0, np.nan)
    output["cf_operating_cash_to_assets"] = output["cf_n_cashflow_act"] / output["bal_total_assets"].replace(0, np.nan)
    output["inc_net_margin_calc"] = output["inc_n_income_attr_p"] / output["inc_total_revenue"].replace(0, np.nan)
    return output


def add_management_rolling_features(events: pd.DataFrame) -> pd.DataFrame:
    left = events[["analysis_group_id", "ts_code", "event_date"]].copy()
    left["event_dt"] = pd.to_datetime(left["event_date"], errors="coerce")
    ledger = read_csv(MANAGEMENT_LEDGER_PATH)
    ledger["signal_dt"] = pd.to_datetime(ledger["event_date"], errors="coerce")
    ledger["institution_count"] = pd.to_numeric(ledger.get("institution_count"), errors="coerce").fillna(0)
    output = left[["analysis_group_id", "ts_code", "event_dt"]].copy()
    for window in MANAGEMENT_WINDOWS:
        frames = []
        delta = pd.Timedelta(days=window)
        for ts_code, event_group in left.groupby("ts_code", sort=False):
            signal_group = ledger[ledger["ts_code"] == ts_code].copy()
            event_group = event_group.sort_values("event_dt")
            if signal_group.empty:
                empty = event_group[["analysis_group_id"]].copy()
                empty[f"mgmt_signal_count_m{window}"] = 0
                empty[f"mgmt_institution_count_sum_m{window}"] = 0.0
                empty[f"mgmt_ir_qa_count_m{window}"] = 0
                empty[f"mgmt_survey_count_m{window}"] = 0
                frames.append(empty)
                continue

            signals = signal_group.sort_values("signal_dt")
            dates = signals["signal_dt"].to_numpy(dtype="datetime64[ns]")
            event_dates = event_group["event_dt"].to_numpy(dtype="datetime64[ns]")
            left_bounds = event_dates - np.timedelta64(delta.days, "D")
            starts = np.searchsorted(dates, left_bounds, side="left")
            ends = np.searchsorted(dates, event_dates, side="left")

            inst = signals["institution_count"].to_numpy(dtype=float)
            ir_qa = (signals["source_type"].astype(str).to_numpy() == "irm_qa").astype(int)
            survey = (signals["source_type"].astype(str).to_numpy() == "institution_survey").astype(int)
            inst_cum = np.concatenate([[0.0], np.cumsum(inst)])
            ir_cum = np.concatenate([[0], np.cumsum(ir_qa)])
            survey_cum = np.concatenate([[0], np.cumsum(survey)])

            frame = event_group[["analysis_group_id"]].copy()
            frame[f"mgmt_signal_count_m{window}"] = ends - starts
            frame[f"mgmt_institution_count_sum_m{window}"] = inst_cum[ends] - inst_cum[starts]
            frame[f"mgmt_ir_qa_count_m{window}"] = ir_cum[ends] - ir_cum[starts]
            frame[f"mgmt_survey_count_m{window}"] = survey_cum[ends] - survey_cum[starts]
            frames.append(frame)
        output = output.merge(pd.concat(frames, ignore_index=True), on="analysis_group_id", how="left")
    return output.drop(columns=["ts_code", "event_dt"])


def build_enhanced_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    dataset = read_csv(INPUT_PATH)
    panel = add_trading_features(load_daily_panel())
    peer = add_peer_features(panel)
    index_panel = load_index_panel()
    panel = panel.merge(peer, on=["ts_code", "trade_dt"], how="left")
    panel = panel.merge(index_panel, on="trade_dt", how="left")

    trading = nearest_prior_trade_features(dataset, panel)
    financial = add_financial_features(dataset)
    management = add_management_rolling_features(dataset)

    drop_from_trading = {
        "event_date",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "ret",
        "vol",
        "amount",
        "turnover_rate",
        "volume_ratio",
        "pe",
        "pb",
        "ps",
        "total_mv",
        "circ_mv",
    }
    trading = trading.drop(columns=[column for column in drop_from_trading if column in trading.columns])
    trading = trading.rename(columns={"trade_dt": "enhanced_asof_trade_date"})

    enhanced = dataset.merge(trading.drop(columns=["ts_code"], errors="ignore"), on="analysis_group_id", how="left")
    enhanced = enhanced.merge(financial, on="analysis_group_id", how="left")
    enhanced = enhanced.merge(management, on="analysis_group_id", how="left")

    original_cols = set(dataset.columns)
    feature_rows = []
    for column in enhanced.columns:
        if column in original_cols or column == "analysis_group_id":
            continue
        if pd.api.types.is_numeric_dtype(enhanced[column]):
            missing_rate = float(enhanced[column].isna().mean())
            feature_rows.append(
                {
                    "feature": column,
                    "non_null": int(enhanced[column].notna().sum()),
                    "missing_rate": missing_rate,
                    "source_group": source_group(column),
                    "leakage_risk": "low",
                }
            )
    return enhanced, pd.DataFrame(feature_rows).sort_values(["source_group", "feature"])


def source_group(column: str) -> str:
    if column.startswith(
        (
            "ret_",
            "volatility_",
            "turnover_",
            "amount_",
            "pe_",
            "pb_",
            "ps_",
            "log_",
            "rel_to_peer_",
            "peer_avg_",
            "mkt_",
        )
    ):
        return "trading_valuation_peer"
    if column.startswith(("fin_", "inc_", "bal_", "cf_")):
        return "financial"
    if column.startswith("mgmt_"):
        return "management_rolling"
    return "other"


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |" for row in frame.to_numpy()]
    return "\n".join([header, divider, *rows])


def write_report(enhanced: pd.DataFrame, manifest: pd.DataFrame) -> None:
    group_summary = (
        manifest.groupby("source_group")
        .agg(features=("feature", "count"), avg_missing=("missing_rate", "mean"))
        .reset_index()
    )
    rows = [
        "# 增强结构化特征摘要",
        "",
        "## 结论",
        "",
        f"- 已生成 enhanced 建模宽表：{len(enhanced)} 行，{len(enhanced.columns)} 列。",
        f"- 新增可入模数值特征 {len(manifest)} 个，覆盖交易估值/同行、财务质量、管理层滚动信号。",
        "- 所有增强特征均按事件日前最近可得数据构造，不使用事件后窗口收益或标签字段。",
        "",
        "## 特征组摘要",
        "",
        markdown_table(group_summary),
        "",
        "## 输出产物",
        "",
        "| 产物 | 路径 | 用途 |",
        "| --- | --- | --- |",
        f"| enhanced 建模宽表 | `{OUTPUT_PATH}` | 下一版模型训练入口 |",
        f"| 特征 manifest | `{FEATURE_MANIFEST_PATH}` | 记录新增特征、缺失率、来源组 |",
        "",
        "## 使用边界",
        "",
        "- 财务特征按公告日 `ann_date <= event_date` 取最近一期。",
        "- 交易/估值特征使用事件日前一可得交易日，不包含事件日及之后表现。",
        "- 管理层滚动信号只统计事件日前已披露记录。",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    enhanced, manifest = build_enhanced_dataset()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    enhanced.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    manifest.to_csv(FEATURE_MANIFEST_PATH, index=False, encoding="utf-8-sig")
    write_report(enhanced, manifest)
    result = {
        "rows": len(enhanced),
        "columns": len(enhanced.columns),
        "new_numeric_features": len(manifest),
        "output": str(OUTPUT_PATH),
        "report": str(REPORT_PATH),
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

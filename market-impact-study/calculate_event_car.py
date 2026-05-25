"""Calculate event-window abnormal returns and market-cap impact."""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pandas as pd

RAW_TUSHARE_DIR = Path("market-impact-study/data/raw/tushare")
PROCESSED_DIR = Path("market-impact-study/data/processed")
TOP_EVENTS_DIR = PROCESSED_DIR / "top_events"

COMPANY_CODE_MAP = {
    "300590.SZ": "移为通信",
    "603236.SH": "移远通信",
    "300098.SZ": "高新兴",
    "300638.SZ": "广和通",
    "002313.SZ": "日海智能",
    "002970.SZ": "锐明技术",
    "688159.SH": "有方科技",
    "002881.SZ": "美格智能",
    "301608.SZ": "博实结",
}

WINDOWS = {
    "m1_p1": (-1, 1),
    "p0_p5": (0, 5),
    "p0_p20": (0, 20),
    "p0_p60": (0, 60),
}


def parse_trade_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")


def clean_title_key(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"^(?:\d{6})?[\u4e00-\u9fa5A-Za-z]+[:：]", "", text)
    text = re.sub(r"^[:：]+", "", text)
    text = re.sub(r"\(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?\)", "", text)
    text = re.sub(r"（\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?）", "", text)
    text = re.sub(r"\s+", "", text)
    return text[:80]


def is_ipo_listing_related(title: str) -> bool:
    text = str(title or "")
    patterns = [
        "首次公开发行",
        "招股说明书",
        "上市公告书",
        "上市保荐书",
        "上市首日",
        "盘中临时停牌",
        "盘中临停",
        "股票在创业板上市交易",
        "股票上市交易",
        "发行结果公告",
        "网上路演公告",
        "新股",
    ]
    return any(pattern in text for pattern in patterns)


def is_market_trading_related(title: str) -> bool:
    text = str(title or "")
    patterns = [
        "股票交易异常波动",
        "盘中临时停牌",
        "盘中临停",
        "停牌核查",
        "复牌公告",
        "临时停牌",
    ]
    return any(pattern in text for pattern in patterns)


def load_market_panel() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted((RAW_TUSHARE_DIR / "daily").glob("*.csv")):
        daily = pd.read_csv(path, dtype={"trade_date": str})
        daily_basic_path = RAW_TUSHARE_DIR / "daily_basic" / path.name
        if daily.empty or not daily_basic_path.exists():
            continue
        daily_basic = pd.read_csv(daily_basic_path, dtype={"trade_date": str})
        merged = daily.merge(
            daily_basic[
                [
                    "ts_code",
                    "trade_date",
                    "turnover_rate",
                    "volume_ratio",
                    "pe",
                    "pb",
                    "ps",
                    "total_mv",
                    "circ_mv",
                ]
            ],
            on=["ts_code", "trade_date"],
            how="left",
            suffixes=("", "_basic"),
        )
        frames.append(merged)
    panel = pd.concat(frames, ignore_index=True)
    panel["trade_dt"] = parse_trade_date(panel["trade_date"])
    panel["ret"] = pd.to_numeric(panel["pct_chg"], errors="coerce") / 100
    numeric_columns = [
        "close",
        "amount",
        "turnover_rate",
        "volume_ratio",
        "pe",
        "pb",
        "ps",
        "total_mv",
        "circ_mv",
    ]
    for column in numeric_columns:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    panel = panel.sort_values(["ts_code", "trade_dt"]).reset_index(drop=True)
    peer_ret = panel.pivot_table(index="trade_dt", columns="ts_code", values="ret", aggfunc="first")
    for ts_code in COMPANY_CODE_MAP:
        others = [column for column in peer_ret.columns if column != ts_code]
        panel.loc[panel["ts_code"] == ts_code, "peer_ret_ex_self"] = panel.loc[
            panel["ts_code"] == ts_code, "trade_dt"
        ].map(peer_ret[others].mean(axis=1))
    panel["abret_peer"] = panel["ret"] - panel["peer_ret_ex_self"]
    return panel


def load_index_returns() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted((RAW_TUSHARE_DIR / "index_daily").glob("*.csv")):
        item = pd.read_csv(path, dtype={"trade_date": str})
        item["trade_dt"] = parse_trade_date(item["trade_date"])
        item["index_ret"] = pd.to_numeric(item["pct_chg"], errors="coerce") / 100
        item["index_code"] = path.stem
        frames.append(item[["index_code", "trade_dt", "index_ret"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_events() -> pd.DataFrame:
    events = pd.read_csv(PROCESSED_DIR / "event_candidates.csv", dtype=str).fillna("")
    stock_basic = pd.read_csv(RAW_TUSHARE_DIR / "stock_basic.csv", dtype=str)
    list_dates = stock_basic.set_index("ts_code")["list_date"].to_dict()
    events["event_dt"] = pd.to_datetime(events["event_date"], errors="coerce")
    events["list_date"] = events["ts_code"].map(list_dates).fillna("")
    events["list_dt"] = pd.to_datetime(events["list_date"], format="%Y%m%d", errors="coerce")
    events["is_pre_listing"] = (
        events["event_dt"].notna() & events["list_dt"].notna() & (events["event_dt"] < events["list_dt"])
    )
    events["is_ipo_listing_related"] = events["title"].map(is_ipo_listing_related)
    events["is_market_trading_related"] = events["title"].map(is_market_trading_related)
    events["keyword_score_num"] = pd.to_numeric(events["keyword_score"], errors="coerce").fillna(0)
    events["source_weight_num"] = pd.to_numeric(events["source_weight"], errors="coerce").fillna(1)
    events["signal_strength_num"] = pd.to_numeric(events["signal_strength"], errors="coerce").fillna(1)
    events["has_pdf_num"] = pd.to_numeric(events["has_pdf"], errors="coerce").fillna(0)
    events["title_key"] = events["title"].map(clean_title_key)
    return events


def aggregate_event_sources(events: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["symbol", "event_date", "primary_category", "title_key"]
    rows: list[dict[str, object]] = []
    for _, group in events.groupby(group_cols, dropna=False, sort=False):
        best_idx = (
            group.assign(
                best_weight=group["source_weight_num"] + group["keyword_score_num"] + group["has_pdf_num"] * 2
            )["best_weight"]
            .astype(float)
            .idxmax()
        )
        base = group.loc[best_idx].to_dict()
        base["source_count"] = group["source_type"].nunique()
        base["source_types"] = "|".join(sorted(set(group["source_type"].astype(str))))
        base["evidence_count"] = len(group)
        base["has_pdf"] = str(int((group["has_pdf_num"] > 0).any()))
        base["source_weight_num"] = group["source_weight_num"].max()
        base["keyword_score_num"] = group["keyword_score_num"].max()
        base["signal_strength_num"] = group["signal_strength_num"].max()
        rows.append(base)
    return pd.DataFrame(rows)


def align_event_row(event: pd.Series, stock: pd.DataFrame) -> tuple[int | None, str]:
    if pd.isna(event["event_dt"]):
        return None, "bad_event_date"
    if bool(event.get("is_pre_listing", False)):
        return None, "pre_listing"
    positions = stock.index[stock["trade_dt"] >= event["event_dt"]].tolist()
    if not positions:
        return None, "after_price_coverage"
    return int(positions[0]), "ok"


def window_sum(stock: pd.DataFrame, pos: int, start: int, end: int, column: str) -> tuple[float, int, int]:
    left = max(0, pos + start)
    right = min(len(stock) - 1, pos + end)
    if right < left:
        return math.nan, 0, end - start + 1
    value = stock.loc[left:right, column].sum(skipna=True)
    actual = right - left + 1
    expected = end - start + 1
    return float(value), actual, expected


def window_end_position(stock: pd.DataFrame, pos: int, end: int) -> int:
    return min(len(stock) - 1, max(0, pos + end))


def build_window_metrics(panel: pd.DataFrame) -> dict[tuple[str, pd.Timestamp, str], dict[str, float]]:
    rows: list[dict[str, object]] = []
    for ts_code, group in panel.groupby("ts_code"):
        stock = group.sort_values("trade_dt").reset_index(drop=True)
        for pos, item in stock.iterrows():
            pre_pos = max(0, pos - 1)
            pre_mv = stock.loc[pre_pos, "total_mv"]
            if pd.isna(pre_mv) or pre_mv == 0:
                continue
            for label, (_, end) in WINDOWS.items():
                end_pos = window_end_position(stock, pos, end)
                end_mv = stock.loc[end_pos, "total_mv"]
                if pd.isna(end_mv):
                    continue
                rows.append(
                    {
                        "ts_code": ts_code,
                        "trade_dt": item["trade_dt"],
                        "label": label,
                        "mv_return": end_mv / pre_mv - 1,
                        "mv_change_yi": (end_mv - pre_mv) / 10000,
                    }
                )
    metrics = pd.DataFrame(rows)
    if metrics.empty:
        return {}
    metrics["rank"] = metrics.groupby(["trade_dt", "label"])["mv_return"].rank(method="min", ascending=False)
    metrics["total"] = metrics.groupby(["trade_dt", "label"])["ts_code"].transform("count")
    total_return = metrics.groupby(["trade_dt", "label"])["mv_return"].transform("sum")
    metrics["peer_avg_return"] = (total_return - metrics["mv_return"]) / (metrics["total"] - 1)
    metrics["percentile"] = 1 - (metrics["rank"] - 1) / (metrics["total"] - 1).clip(lower=1)
    return {
        (str(row.ts_code), row.trade_dt, str(row.label)): {
            "peer_avg_return": float(row.peer_avg_return),
            "rank": float(row.rank),
            "total": float(row.total),
            "percentile": float(row.percentile),
        }
        for row in metrics.itertuples(index=False)
    }


def enrich_events(events: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    stock_panels = {
        ts_code: group.sort_values("trade_dt").reset_index(drop=True) for ts_code, group in panel.groupby("ts_code")
    }
    window_metrics = build_window_metrics(panel)
    enriched_rows: list[dict[str, object]] = []
    for _, event in events.iterrows():
        row = event.to_dict()
        stock = stock_panels.get(str(event["ts_code"]))
        if stock is None or stock.empty:
            row["car_status"] = "missing_price"
            enriched_rows.append(row)
            continue
        pos, status = align_event_row(event, stock)
        row["car_status"] = status
        if pos is None:
            enriched_rows.append(row)
            continue
        aligned = stock.loc[pos]
        pre_pos = max(0, pos - 1)
        pre = stock.loc[pre_pos]
        row["aligned_trade_date"] = aligned["trade_dt"].strftime("%Y-%m-%d")
        row["pre_trade_date"] = pre["trade_dt"].strftime("%Y-%m-%d")
        row["pre_total_mv_wanyuan"] = pre["total_mv"]
        row["pre_total_mv_yi"] = pre["total_mv"] / 10000 if pd.notna(pre["total_mv"]) else math.nan
        row["event_turnover_rate"] = aligned["turnover_rate"]
        row["event_volume_ratio"] = aligned["volume_ratio"]
        row["event_close"] = aligned["close"]
        row["event_ret"] = aligned["ret"]
        row["event_abret_peer"] = aligned["abret_peer"]
        for label, (start, end) in WINDOWS.items():
            car, actual, expected = window_sum(stock, pos, start, end, "abret_peer")
            ret_sum, _, _ = window_sum(stock, pos, start, end, "ret")
            peer_sum, _, _ = window_sum(stock, pos, start, end, "peer_ret_ex_self")
            end_pos = window_end_position(stock, pos, end)
            end_row = stock.loc[end_pos]
            row[f"car_{label}"] = car
            row[f"ret_{label}"] = ret_sum
            row[f"peer_ret_{label}"] = peer_sum
            row[f"window_days_{label}"] = actual
            row[f"window_coverage_{label}"] = actual / expected if expected else math.nan
            row[f"end_trade_date_{label}"] = end_row["trade_dt"].strftime("%Y-%m-%d")
            row[f"end_total_mv_yi_{label}"] = end_row["total_mv"] / 10000 if pd.notna(end_row["total_mv"]) else math.nan
            row[f"actual_mv_change_yi_{label}"] = (
                (end_row["total_mv"] - pre["total_mv"]) / 10000
                if pd.notna(end_row["total_mv"]) and pd.notna(pre["total_mv"])
                else math.nan
            )
            row[f"actual_mv_return_{label}"] = (
                end_row["total_mv"] / pre["total_mv"] - 1
                if pd.notna(end_row["total_mv"]) and pd.notna(pre["total_mv"]) and pre["total_mv"] != 0
                else math.nan
            )
            row[f"abnormal_mv_impact_yi_{label}"] = (
                pre["total_mv"] * car / 10000 if pd.notna(pre["total_mv"]) and pd.notna(car) else math.nan
            )
            metrics = window_metrics.get((str(event["ts_code"]), aligned["trade_dt"], label), {})
            row[f"peer_avg_mv_return_{label}"] = metrics.get("peer_avg_return", math.nan)
            row[f"peer_rank_by_mv_return_{label}"] = metrics.get("rank", math.nan)
            row[f"peer_rank_total_{label}"] = metrics.get("total", math.nan)
            row[f"peer_percentile_by_mv_return_{label}"] = metrics.get("percentile", math.nan)
        enriched_rows.append(row)
    return pd.DataFrame(enriched_rows)


def add_scores(events: pd.DataFrame) -> pd.DataFrame:
    for column in [
        "source_weight_num",
        "keyword_score_num",
        "signal_strength_num",
        "has_pdf",
        "source_count",
        "evidence_count",
        "event_volume_ratio",
        "actual_mv_change_yi_p0_p20",
        "actual_mv_return_p0_p20",
        "car_m1_p1",
        "car_p0_p5",
        "car_p0_p20",
        "car_p0_p60",
    ]:
        events[column] = pd.to_numeric(events.get(column, 0), errors="coerce").fillna(0)
    events["multi_source_bonus"] = events["source_count"].clip(upper=4) - 1
    events["volume_spike_score"] = events["event_volume_ratio"].clip(upper=5).fillna(0)
    events["abs_car_score"] = (
        events["car_m1_p1"].abs() * 80 + events["car_p0_p5"].abs() * 50 + events["car_p0_p20"].abs() * 25
    )
    events["event_priority_score"] = (
        events["source_weight_num"] * 2
        + events["keyword_score_num"]
        + events["signal_strength_num"].clip(upper=20) / 5
        + events["has_pdf"].astype(float) * 2
        + events["multi_source_bonus"] * 1.5
        + events["volume_spike_score"]
        + events["abs_car_score"]
    )
    events["objective_change_score"] = (
        events["actual_mv_return_p0_p20"].abs() * 80
        + events["actual_mv_change_yi_p0_p20"].abs().clip(upper=100) * 0.5
        + events["event_volume_ratio"].clip(upper=5).fillna(0)
        + events["source_weight_num"]
    )
    return events


def aggregate_analysis_groups(events: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["symbol", "event_date", "primary_category"]
    rows: list[dict[str, object]] = []
    scored_events = events.sort_values("event_priority_score", ascending=False)
    for _, group in scored_events.groupby(group_cols, dropna=False, sort=False):
        base = group.iloc[0].to_dict()
        titles = [str(title) for title in group["title"].dropna().head(6)]
        source_types: set[str] = set()
        for value in group["source_types"].astype(str):
            source_types.update(part for part in value.split("|") if part)
        base["analysis_group_id"] = "|".join(str(base.get(column, "")) for column in group_cols)
        base["group_event_count"] = len(group)
        base["group_source_types"] = "|".join(sorted(source_types))
        base["group_source_count"] = group["source_count"].max()
        base["group_evidence_count"] = group["evidence_count"].sum()
        base["group_titles_sample"] = " || ".join(titles)
        base["event_priority_score"] = (
            group["event_priority_score"].max()
            + min(len(group), 8) * 0.5
            + min(group["evidence_count"].sum(), 20) * 0.1
        )
        rows.append(base)
    return pd.DataFrame(rows)


def add_peer_spillover(events: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    yiwei = panel[panel["ts_code"] == "300590.SZ"].sort_values("trade_dt").reset_index(drop=True)
    rows: list[dict[str, object]] = []
    peer_events = events[
        (events["symbol"] != "300590")
        & (events["car_status"] == "ok")
        & (~events["is_pre_listing"].astype(bool))
        & (~events["is_ipo_listing_related"].astype(bool))
        & (~events["is_market_trading_related"].astype(bool))
    ]
    for _, event in peer_events.iterrows():
        row = event.to_dict()
        if pd.notna(event["event_dt"]) and event["event_dt"] < yiwei["trade_dt"].min():
            pos, status = None, "before_yiwei_listing"
        else:
            pos, status = align_event_row(event, yiwei)
        row["yiwei_spillover_status"] = status
        if pos is not None:
            pre_pos = max(0, pos - 1)
            pre = yiwei.loc[pre_pos]
            row["yiwei_aligned_trade_date"] = yiwei.loc[pos, "trade_dt"].strftime("%Y-%m-%d")
            row["yiwei_pre_total_mv_yi"] = pre["total_mv"] / 10000 if pd.notna(pre["total_mv"]) else math.nan
            for label, (start, end) in WINDOWS.items():
                car, actual, expected = window_sum(yiwei, pos, start, end, "abret_peer")
                end_pos = window_end_position(yiwei, pos, end)
                end_row = yiwei.loc[end_pos]
                row[f"yiwei_car_{label}"] = car
                row[f"yiwei_window_coverage_{label}"] = actual / expected if expected else math.nan
                row[f"yiwei_end_total_mv_yi_{label}"] = (
                    end_row["total_mv"] / 10000 if pd.notna(end_row["total_mv"]) else math.nan
                )
                row[f"yiwei_actual_mv_change_yi_{label}"] = (
                    (end_row["total_mv"] - pre["total_mv"]) / 10000
                    if pd.notna(end_row["total_mv"]) and pd.notna(pre["total_mv"])
                    else math.nan
                )
                row[f"yiwei_actual_mv_return_{label}"] = (
                    end_row["total_mv"] / pre["total_mv"] - 1
                    if pd.notna(end_row["total_mv"]) and pd.notna(pre["total_mv"]) and pre["total_mv"] != 0
                    else math.nan
                )
                row[f"yiwei_abnormal_mv_impact_yi_{label}"] = (
                    pre["total_mv"] * car / 10000 if pd.notna(pre["total_mv"]) and pd.notna(car) else math.nan
                )
                row[f"peer_minus_yiwei_car_{label}"] = row.get(f"car_{label}", math.nan) - car
        rows.append(row)
    result = pd.DataFrame(rows)
    if not result.empty:
        result["spillover_abs_score"] = pd.to_numeric(result["yiwei_car_p0_p20"], errors="coerce").abs() * 100
        result["peer_learning_score"] = (
            pd.to_numeric(result["car_p0_p20"], errors="coerce").clip(lower=0) * 60
            + pd.to_numeric(result["yiwei_car_p0_p20"], errors="coerce").abs() * 40
            + pd.to_numeric(result["event_priority_score"], errors="coerce").fillna(0) * 0.2
        )
        result["peer_key_action_score"] = (
            pd.to_numeric(result["actual_mv_return_p0_p20"], errors="coerce").clip(lower=0) * 60
            + pd.to_numeric(result["car_p0_p20"], errors="coerce").clip(lower=0) * 30
            + pd.to_numeric(result["event_priority_score"], errors="coerce").fillna(0) * 0.2
        )
    return result


def write_outputs(events: pd.DataFrame, panel: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TOP_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "event_candidates_scored.csv"
    events.sort_values("event_priority_score", ascending=False).to_csv(output_path, index=False, encoding="utf-8-sig")

    output_groups_path = PROCESSED_DIR / "event_analysis_groups_scored.csv"
    analysis_groups = aggregate_analysis_groups(events)
    analysis_groups.sort_values("event_priority_score", ascending=False).to_csv(
        output_groups_path, index=False, encoding="utf-8-sig"
    )
    peer_spillover = add_peer_spillover(analysis_groups, panel)
    peer_spillover.to_csv(PROCESSED_DIR / "peer_spillover_to_yiwei.csv", index=False, encoding="utf-8-sig")

    ok = analysis_groups[
        (analysis_groups["car_status"] == "ok")
        & (~analysis_groups["is_pre_listing"].astype(bool))
        & (~analysis_groups["is_ipo_listing_related"].astype(bool))
        & (~analysis_groups["is_market_trading_related"].astype(bool))
    ].copy()
    outputs = {
        "subject_top_100.csv": ok[ok["symbol"] == "300590"]
        .sort_values("event_priority_score", ascending=False)
        .head(100),
        "peer_action_top_100.csv": ok[ok["symbol"] != "300590"]
        .sort_values("event_priority_score", ascending=False)
        .head(100),
        "subject_objective_mv_change_top_100.csv": ok[ok["symbol"] == "300590"]
        .sort_values("objective_change_score", ascending=False)
        .head(100),
        "peer_objective_mv_change_top_100.csv": ok[ok["symbol"] != "300590"]
        .sort_values("objective_change_score", ascending=False)
        .head(100),
        "positive_impact_top_50.csv": ok.sort_values("abnormal_mv_impact_yi_p0_p20", ascending=False).head(50),
        "negative_impact_top_50.csv": ok.sort_values("abnormal_mv_impact_yi_p0_p20", ascending=True).head(50),
        "positive_actual_mv_change_top_50.csv": ok.sort_values("actual_mv_change_yi_p0_p20", ascending=False).head(50),
        "negative_actual_mv_change_top_50.csv": ok.sort_values("actual_mv_change_yi_p0_p20", ascending=True).head(50),
        "category_impact_summary.csv": ok.groupby("primary_category", dropna=False)
        .agg(
            event_count=("event_id", "count"),
            avg_actual_mv_return_p0_p20=("actual_mv_return_p0_p20", "mean"),
            median_actual_mv_change_yi_p0_p20=("actual_mv_change_yi_p0_p20", "median"),
            abs_actual_mv_change_yi_p0_p20=("actual_mv_change_yi_p0_p20", lambda x: x.abs().sum()),
            avg_car_m1_p1=("car_m1_p1", "mean"),
            avg_car_p0_p5=("car_p0_p5", "mean"),
            avg_car_p0_p20=("car_p0_p20", "mean"),
            median_impact_yi_p0_p20=("abnormal_mv_impact_yi_p0_p20", "median"),
            abs_impact_yi_p0_p20=("abnormal_mv_impact_yi_p0_p20", lambda x: x.abs().sum()),
        )
        .reset_index()
        .sort_values("abs_impact_yi_p0_p20", ascending=False),
        "company_category_impact_summary.csv": ok.groupby(["company", "primary_category"], dropna=False)
        .agg(
            event_count=("event_id", "count"),
            avg_actual_mv_return_p0_p20=("actual_mv_return_p0_p20", "mean"),
            median_actual_mv_change_yi_p0_p20=("actual_mv_change_yi_p0_p20", "median"),
            avg_car_p0_p20=("car_p0_p20", "mean"),
            median_impact_yi_p0_p20=("abnormal_mv_impact_yi_p0_p20", "median"),
            abs_impact_yi_p0_p20=("abnormal_mv_impact_yi_p0_p20", lambda x: x.abs().sum()),
        )
        .reset_index()
        .sort_values(["company", "abs_impact_yi_p0_p20"], ascending=[True, False]),
    }
    if not peer_spillover.empty:
        outputs["peer_spillover_to_yiwei_top_50.csv"] = (
            peer_spillover[peer_spillover["yiwei_spillover_status"] == "ok"]
            .sort_values("spillover_abs_score", ascending=False)
            .head(50)
        )
        outputs["peer_learning_actions_top_50.csv"] = (
            peer_spillover[peer_spillover["yiwei_spillover_status"] == "ok"]
            .sort_values("peer_key_action_score", ascending=False)
            .head(50)
        )
    ipo = analysis_groups[
        (analysis_groups["car_status"] == "ok")
        & (
            analysis_groups["is_ipo_listing_related"].astype(bool)
            | analysis_groups["is_market_trading_related"].astype(bool)
        )
    ].copy()
    if not ipo.empty:
        outputs["ipo_listing_events_top_100.csv"] = ipo.sort_values("actual_mv_change_yi_p0_p20", ascending=False).head(
            100
        )
    for filename, frame in outputs.items():
        frame.to_csv(TOP_EVENTS_DIR / filename, index=False, encoding="utf-8-sig")

    status = events["car_status"].value_counts(dropna=False).rename_axis("status").reset_index(name="rows")
    status.to_csv(PROCESSED_DIR / "car_status_summary.csv", index=False, encoding="utf-8-sig")
    sys.stdout.write(f"rows={len(events)} path={output_path}\n")
    sys.stdout.write(status.to_string(index=False) + "\n")


def main() -> int:
    panel = load_market_panel()
    _ = load_index_returns()
    events = load_events()
    deduped = aggregate_event_sources(events)
    enriched = enrich_events(deduped, panel)
    scored = add_scores(enriched)
    write_outputs(scored, panel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

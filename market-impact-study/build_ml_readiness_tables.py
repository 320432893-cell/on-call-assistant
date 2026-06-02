"""生成统计/ML 主线建模准入诊断表。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAW_TUSHARE_DIR = Path("market-impact-study/data/raw/tushare")
PROCESSED_DIR = Path("market-impact-study/data/processed")
OUTPUT_DIR = PROCESSED_DIR / "ml_readiness"
EVENT_GROUPS_PATH = PROCESSED_DIR / "event_analysis_groups_scored.csv"
PEER_SPILLOVER_PATH = PROCESSED_DIR / "peer_spillover_to_yiwei.csv"
YIWEI_DAILY_PATH = RAW_TUSHARE_DIR / "daily" / "300590.SZ.csv"

OVERLAP_WINDOWS = {
    "m1_p1": ("pre_trade_date", "end_trade_date_m1_p1"),
    "p0_p5": ("aligned_trade_date", "end_trade_date_p0_p5"),
    "m1_p5": ("pre_trade_date", "end_trade_date_p0_p5"),
    "p0_p20": ("aligned_trade_date", "end_trade_date_p0_p20"),
    "p0_p60": ("aligned_trade_date", "end_trade_date_p0_p60"),
}

PEER_OVERLAP_END_OFFSETS = {"p0_p5": 5, "p0_p20": 20, "p0_p60": 60}

SUMMARY_COLUMNS = [
    "analysis_group_id",
    "company",
    "ts_code",
    "symbol",
    "event_date",
    "aligned_trade_date",
    "primary_category",
    "capital_action_subtype",
    "capital_action_subtype_hits",
    "source_type",
    "title",
    "group_titles_sample",
    "car_status",
    "is_ipo_listing_related",
    "is_market_trading_related",
    "car_m1_p1",
    "car_p0_p5",
    "car_p0_p20",
    "actual_mv_return_p0_p5",
    "actual_mv_return_p0_p20",
    "abnormal_mv_impact_yi_p0_p5",
    "abnormal_mv_impact_yi_p0_p20",
]


def contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def joined_event_text(row: pd.Series | dict[str, object]) -> str:
    parts = [
        str(row.get("title", "") or ""),
        str(row.get("group_titles_sample", "") or ""),
        str(row.get("summary", "") or ""),
        str(row.get("category_tags", "") or ""),
        str(row.get("raw_category", "") or ""),
        str(row.get("source_type", "") or ""),
    ]
    return " ".join(parts)


def capital_action_subtype_hits(row: pd.Series | dict[str, object]) -> list[str]:
    text = joined_event_text(row)
    hits: list[str] = []

    if contains_any(text, ("股权激励", "限制性股票", "股票期权", "员工持股", "激励对象", "解锁", "归属条件")):
        hits.append("股权激励/员工持股")
    if contains_any(
        text,
        (
            "重大资产重组",
            "资产重组",
            "发行股份购买资产",
            "支付现金购买资产",
            "收购",
            "并购",
            "资产出售",
            "股权转让",
            "资产注入",
            "利润承诺补偿",
        ),
    ):
        hits.append("并购重组/资产交易")
    if contains_any(text, ("非公开发行", "向特定对象发行", "定增", "配套募集资金", "募集配套资金", "再融资")):
        hits.append("定增/再融资")
    if contains_any(text, ("权益分派", "利润分配", "现金分红", "分红送转", "年度分红", "分红管理制度")):
        hits.append("分红/权益分派")
    if contains_any(text, ("增持", "减持", "持股变动", "股份变动", "限售股上市流通", "解除限售")):
        hits.append("股东增减持/限售流通")
    if contains_any(text, ("质押", "解押", "解除质押", "质押式回购")):
        hits.append("股权质押/解押")
    if contains_any(text, ("可转换公司债", "可转债", "公司债券", "债券发行", "短期融资券")):
        hits.append("债务融资")

    is_incentive_cancel = contains_any(text, ("回购注销", "注销限制性股票"))
    is_pledge_repo = contains_any(text, ("质押式回购",))
    is_share_repurchase = contains_any(
        text,
        (
            "回购公司股份",
            "股份回购",
            "以集中竞价交易方式回购",
            "回购报告书",
            "回购股份方案",
            "回购预案",
            "回购进展",
        ),
    )
    if is_share_repurchase and not is_incentive_cancel and not is_pledge_repo:
        hits.append("股份回购")

    deduped: list[str] = []
    for hit in hits:
        if hit not in deduped:
            deduped.append(hit)
    return deduped


def classify_capital_action_subtype(row: pd.Series | dict[str, object]) -> str:
    hits = capital_action_subtype_hits(row)
    if not hits:
        return "其他资本动作"
    if len(hits) == 1:
        return hits[0]
    return "复合资本动作"


def parse_date_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index)
    return pd.to_datetime(frame[column], errors="coerce")


def load_yiwei_trade_calendar() -> list[pd.Timestamp]:
    if not YIWEI_DAILY_PATH.exists():
        return []
    daily = pd.read_csv(YIWEI_DAILY_PATH, dtype={"trade_date": str})
    dates = pd.to_datetime(daily["trade_date"], format="%Y%m%d", errors="coerce").dropna().sort_values()
    return list(dates)


def trade_window_end(trade_dates: list[pd.Timestamp], start_dt: pd.Timestamp, end_offset: int) -> pd.Timestamp:
    if not trade_dates or pd.isna(start_dt):
        return pd.NaT
    trade_index = pd.Index(trade_dates)
    pos = int(trade_index.searchsorted(start_dt, side="left"))
    if pos < len(trade_dates):
        return trade_dates[min(len(trade_dates) - 1, pos + end_offset)]
    return pd.NaT


def format_trade_window_end(trade_dates: list[pd.Timestamp], start_dt: pd.Timestamp, end_offset: int) -> str:
    end_dt = trade_window_end(trade_dates, start_dt, end_offset)
    return end_dt.strftime("%Y-%m-%d") if pd.notna(end_dt) else ""


def add_capital_subtypes(events: pd.DataFrame) -> pd.DataFrame:
    result = events.copy()
    result["capital_action_subtype"] = ""
    result["capital_action_subtype_hits"] = ""
    mask = result["primary_category"].astype(str) == "资本动作"
    if mask.any():
        result.loc[mask, "capital_action_subtype"] = result.loc[mask].apply(classify_capital_action_subtype, axis=1)
        result.loc[mask, "capital_action_subtype_hits"] = result.loc[mask].apply(
            lambda row: "|".join(capital_action_subtype_hits(row)),
            axis=1,
        )
    return result


def add_same_company_overlap(events: pd.DataFrame) -> pd.DataFrame:
    result = events.copy()
    result["event_row_id"] = range(len(result))
    result["aligned_trade_dt"] = parse_date_column(result, "aligned_trade_date")
    for start_col, end_col in OVERLAP_WINDOWS.values():
        result[f"{start_col}_dt"] = parse_date_column(result, start_col)
        result[f"{end_col}_dt"] = parse_date_column(result, end_col)
    for label in OVERLAP_WINDOWS:
        result[f"overlap_event_count_{label}"] = 0
        result[f"overlap_category_count_{label}"] = 0
        result[f"overlap_categories_{label}"] = ""
        result[f"overlap_titles_sample_{label}"] = ""
        result[f"is_overlap_clean_{label}"] = False

    for _, group in result.groupby("ts_code", dropna=False):
        valid = group[group["aligned_trade_dt"].notna()].sort_values("aligned_trade_dt")
        aligned_values = valid["aligned_trade_dt"].to_numpy(dtype="datetime64[ns]")
        aligned_indices = list(valid.index)
        aligned_position_by_index = {index: position for position, index in enumerate(aligned_indices)}
        aligned_categories = list(valid["primary_category"].astype(str))
        aligned_titles = list(valid["title"].astype(str))
        for idx, row in group.iterrows():
            for label, (start_col, end_col) in OVERLAP_WINDOWS.items():
                start_dt = row.get(f"{start_col}_dt")
                end_dt = row.get(f"{end_col}_dt")
                if pd.isna(start_dt) or pd.isna(end_dt):
                    continue
                left = int(aligned_values.searchsorted(start_dt.to_datetime64(), side="left"))
                right = int(aligned_values.searchsorted(end_dt.to_datetime64(), side="right"))
                self_pos = aligned_position_by_index.get(idx, -1)
                self_in_window = left <= self_pos < right
                overlap_count = right - left - (1 if self_in_window else 0)
                category_slice = aligned_categories[left:right]
                title_slice = aligned_titles[left:right]
                if self_in_window:
                    relative_pos = self_pos - left
                    category_slice = category_slice[:relative_pos] + category_slice[relative_pos + 1 :]
                    title_slice = title_slice[:relative_pos] + title_slice[relative_pos + 1 :]
                categories = sorted(set(category_slice))
                titles = title_slice[:3]
                result.at[idx, f"overlap_event_count_{label}"] = overlap_count
                result.at[idx, f"overlap_category_count_{label}"] = len(categories)
                result.at[idx, f"overlap_categories_{label}"] = "|".join(categories)
                result.at[idx, f"overlap_titles_sample_{label}"] = " || ".join(titles)
                result.at[idx, f"is_overlap_clean_{label}"] = overlap_count == 0
    return result


def add_peer_yiwei_overlap(
    peer: pd.DataFrame, events: pd.DataFrame, yiwei_trade_dates: list[pd.Timestamp]
) -> pd.DataFrame:
    result = peer.copy()
    yiwei = events[(events["symbol"].astype(str) == "300590") & (events["car_status"].astype(str) == "ok")].copy()
    yiwei["aligned_trade_dt"] = parse_date_column(yiwei, "aligned_trade_date")
    yiwei = yiwei[yiwei["aligned_trade_dt"].notna()].sort_values("aligned_trade_dt")
    yiwei_dates = yiwei["aligned_trade_dt"].to_numpy(dtype="datetime64[ns]")
    yiwei_categories = list(yiwei["primary_category"].astype(str))

    result["yiwei_aligned_trade_dt"] = parse_date_column(result, "yiwei_aligned_trade_date")
    for label, end_offset in PEER_OVERLAP_END_OFFSETS.items():
        end_col = f"yiwei_response_end_trade_date_{label}"
        result[end_col] = result["yiwei_aligned_trade_dt"].map(
            lambda value, offset=end_offset: format_trade_window_end(yiwei_trade_dates, value, offset)
        )
        result[f"{end_col}_dt"] = parse_date_column(result, end_col)
        result[f"yiwei_own_event_overlap_count_{label}"] = 0
        result[f"yiwei_own_event_overlap_categories_{label}"] = ""
        result[f"is_spillover_clean_{label}"] = False

    for idx, row in result.iterrows():
        if str(row.get("yiwei_spillover_status", "")) != "ok":
            continue
        start_dt = row.get("yiwei_aligned_trade_dt")
        if pd.isna(start_dt):
            continue
        for label in PEER_OVERLAP_END_OFFSETS:
            end_dt = row.get(f"yiwei_response_end_trade_date_{label}_dt")
            if pd.isna(end_dt):
                continue
            left = int(yiwei_dates.searchsorted(start_dt.to_datetime64(), side="left"))
            right = int(yiwei_dates.searchsorted(end_dt.to_datetime64(), side="right"))
            overlap_count = right - left
            categories = sorted(set(yiwei_categories[left:right]))
            result.at[idx, f"yiwei_own_event_overlap_count_{label}"] = overlap_count
            result.at[idx, f"yiwei_own_event_overlap_categories_{label}"] = "|".join(categories)
            result.at[idx, f"is_spillover_clean_{label}"] = overlap_count == 0
    return result


def true_count(series: pd.Series) -> int:
    return int(series.fillna(value=False).astype(bool).sum())


def model_readiness_label(row: pd.Series) -> str:
    clean_events = int(row["clean_p0_p5_event_groups"])
    clean_companies = int(row["clean_p0_p5_company_count"])
    total_companies = int(row["company_count"])
    if clean_events >= 60 and clean_companies >= 5:
        return "可作为主力估计候选"
    if clean_events >= 20 and clean_companies >= 3 and total_companies >= 4:
        return "可做描述+谨慎估计"
    return "仅描述或合并到其他类"


def readiness_reason(row: pd.Series) -> str:
    return (
        f"总样本{int(row['event_groups'])}，CAR成功{int(row['ok_event_groups'])}，"
        f"[0,+5]无同公司重叠{int(row['clean_p0_p5_event_groups'])}，"
        f"干净样本覆盖{int(row['clean_p0_p5_company_count'])}家公司。"
    )


def build_capital_counts(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    capital = events[events["primary_category"].astype(str) == "资本动作"].copy()
    numeric_columns = [
        "car_p0_p5",
        "car_p0_p20",
        "actual_mv_return_p0_p5",
        "actual_mv_return_p0_p20",
        "abnormal_mv_impact_yi_p0_p5",
        "abnormal_mv_impact_yi_p0_p20",
    ]
    for column in numeric_columns:
        capital[column] = pd.to_numeric(capital.get(column), errors="coerce")
    capital["is_ok"] = capital["car_status"].astype(str) == "ok"
    capital["is_clean_p0_p5_ok"] = capital["is_ok"] & capital["is_overlap_clean_p0_p5"].astype(bool)

    subtype_counts = (
        capital.groupby("capital_action_subtype", dropna=False)
        .agg(
            event_groups=("analysis_group_id", "count"),
            ok_event_groups=("is_ok", true_count),
            clean_p0_p5_event_groups=("is_clean_p0_p5_ok", true_count),
            company_count=("company", "nunique"),
            ok_company_count=(
                "company",
                lambda x: capital.loc[x.index][capital.loc[x.index, "is_ok"]]["company"].nunique(),
            ),
            clean_p0_p5_company_count=(
                "company",
                lambda x: capital.loc[x.index][capital.loc[x.index, "is_clean_p0_p5_ok"]]["company"].nunique(),
            ),
            yiwei_event_groups=("symbol", lambda x: int((x.astype(str) == "300590").sum())),
            median_car_p0_p5=("car_p0_p5", "median"),
            median_car_p0_p20=("car_p0_p20", "median"),
            median_actual_mv_return_p0_p5=("actual_mv_return_p0_p5", "median"),
            median_actual_mv_return_p0_p20=("actual_mv_return_p0_p20", "median"),
            median_abnormal_mv_impact_yi_p0_p5=("abnormal_mv_impact_yi_p0_p5", "median"),
            median_abnormal_mv_impact_yi_p0_p20=("abnormal_mv_impact_yi_p0_p20", "median"),
        )
        .reset_index()
        .sort_values(["clean_p0_p5_event_groups", "event_groups"], ascending=[False, False])
    )
    subtype_counts["model_readiness"] = subtype_counts.apply(model_readiness_label, axis=1)
    subtype_counts["readiness_reason"] = subtype_counts.apply(readiness_reason, axis=1)

    company_counts = (
        capital.groupby(["company", "capital_action_subtype"], dropna=False)
        .agg(
            event_groups=("analysis_group_id", "count"),
            ok_event_groups=("is_ok", true_count),
            clean_p0_p5_event_groups=("is_clean_p0_p5_ok", true_count),
            median_car_p0_p5=("car_p0_p5", "median"),
            median_actual_mv_return_p0_p5=("actual_mv_return_p0_p5", "median"),
        )
        .reset_index()
        .sort_values(
            ["capital_action_subtype", "clean_p0_p5_event_groups", "event_groups"],
            ascending=[True, False, False],
        )
    )
    return capital, subtype_counts, company_counts


def build_overlap_summary(events: pd.DataFrame, peer: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    base_masks = {
        "全事件组": pd.Series(data=True, index=events.index),
        "CAR成功事件组": events["car_status"].astype(str) == "ok",
        "资本动作事件组": events["primary_category"].astype(str) == "资本动作",
        "移为事件组": events["symbol"].astype(str) == "300590",
    }
    for scope, mask in base_masks.items():
        scoped = events.loc[mask]
        row: dict[str, object] = {"scope": scope, "event_groups": len(scoped)}
        for label in OVERLAP_WINDOWS:
            count_col = f"overlap_event_count_{label}"
            dirty = int((scoped[count_col] > 0).sum()) if count_col in scoped else 0
            row[f"overlapped_{label}"] = dirty
            row[f"clean_{label}"] = len(scoped) - dirty
            row[f"overlap_rate_{label}"] = dirty / len(scoped) if len(scoped) else 0
        rows.append(row)

    ok_peer = peer[peer["yiwei_spillover_status"].astype(str) == "ok"] if not peer.empty else peer
    peer_row: dict[str, object] = {"scope": "竞品外溢OK事件", "event_groups": len(ok_peer)}
    for label in PEER_OVERLAP_END_OFFSETS:
        count_col = f"yiwei_own_event_overlap_count_{label}"
        dirty = int((ok_peer[count_col] > 0).sum()) if count_col in ok_peer else 0
        peer_row[f"overlapped_{label}"] = dirty
        peer_row[f"clean_{label}"] = len(ok_peer) - dirty
        peer_row[f"overlap_rate_{label}"] = dirty / len(ok_peer) if len(ok_peer) else 0
    rows.append(peer_row)
    return pd.DataFrame(rows)


def write_summary(
    events: pd.DataFrame,
    peer: pd.DataFrame,
    subtype_counts: pd.DataFrame,
    overlap_summary: pd.DataFrame,
    output_path: Path,
) -> None:
    capital = events[events["primary_category"].astype(str) == "资本动作"]
    clean_capital = capital[
        (capital["car_status"].astype(str) == "ok") & capital["is_overlap_clean_p0_p5"].astype(bool)
    ]
    ok_peer = peer[peer["yiwei_spillover_status"].astype(str) == "ok"] if not peer.empty else peer
    clean_peer = ok_peer[ok_peer["is_spillover_clean_p0_p5"].astype(bool)] if not ok_peer.empty else ok_peer
    candidates = subtype_counts[subtype_counts["model_readiness"] == "可作为主力估计候选"]

    subtype_summary = subtype_counts[
        [
            "capital_action_subtype",
            "event_groups",
            "clean_p0_p5_event_groups",
            "clean_p0_p5_company_count",
            "model_readiness",
        ]
    ]
    lines = [
        "# ML 建模准入诊断摘要",
        "",
        "## 关键结论",
        "",
        f"- 事件组总数：{len(events)}；资本动作事件组：{len(capital)}。",
        f"- 资本动作 CAR 成功且 [0,+5] 无同公司重叠：{len(clean_capital)}。",
        f"- 竞品外溢 OK 事件：{len(ok_peer)}；排除移为自身 [0,+5] 同窗事件后：{len(clean_peer)}。",
        f"- 当前可作为主力估计候选的资本动作子类：{len(candidates)} 个。",
        "",
        "## 资本动作子类准入",
        "",
        markdown_table(subtype_summary),
        "",
        "## 重叠污染概览",
        "",
        markdown_table(overlap_summary),
        "",
        "## 使用边界",
        "",
        "- 本诊断只判断能否进入估计/归因，不产生最终效应结论。",
        "- `复合资本动作` 说明同一事件组文本命中多个资本机制，默认不适合直接进入单一子类回归。",
        "- [0,+60] 重叠率只做描述性风险提示，不用于因果主窗口。",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    rows = [["" if pd.isna(value) else str(value) for value in row] for row in frame.to_numpy()]
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def selected_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[[column for column in columns if column in frame.columns]].copy()


def main() -> int:
    events = pd.read_csv(EVENT_GROUPS_PATH, dtype=str).fillna("")
    peer = pd.read_csv(PEER_SPILLOVER_PATH, dtype=str).fillna("") if PEER_SPILLOVER_PATH.exists() else pd.DataFrame()

    events = add_capital_subtypes(events)
    events = add_same_company_overlap(events)
    yiwei_trade_dates = load_yiwei_trade_calendar()
    peer = add_peer_yiwei_overlap(peer, events, yiwei_trade_dates) if not peer.empty else peer
    capital, subtype_counts, company_counts = build_capital_counts(events)
    overlap_summary = build_overlap_summary(events, peer)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    events.to_csv(OUTPUT_DIR / "event_overlap_diagnostics.csv", index=False, encoding="utf-8-sig")
    if not peer.empty:
        peer.to_csv(OUTPUT_DIR / "peer_spillover_overlap_diagnostics.csv", index=False, encoding="utf-8-sig")
    selected_columns(
        capital,
        SUMMARY_COLUMNS + [column for column in capital.columns if column.startswith("overlap_")],
    ).to_csv(OUTPUT_DIR / "capital_action_event_diagnostics.csv", index=False, encoding="utf-8-sig")
    subtype_counts.to_csv(OUTPUT_DIR / "capital_action_subtype_counts.csv", index=False, encoding="utf-8-sig")
    company_counts.to_csv(OUTPUT_DIR / "capital_action_company_subtype_counts.csv", index=False, encoding="utf-8-sig")
    subtype_counts.to_csv(OUTPUT_DIR / "capital_action_model_readiness.csv", index=False, encoding="utf-8-sig")
    overlap_summary.to_csv(OUTPUT_DIR / "event_overlap_summary.csv", index=False, encoding="utf-8-sig")
    write_summary(events, peer, subtype_counts, overlap_summary, OUTPUT_DIR / "ml_readiness_summary.md")

    sys.stdout.write(f"event_groups={len(events)} capital_actions={len(capital)} output_dir={OUTPUT_DIR}\n")
    sys.stdout.write(
        subtype_counts[
            ["capital_action_subtype", "event_groups", "clean_p0_p5_event_groups", "model_readiness"]
        ].to_string(index=False)
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

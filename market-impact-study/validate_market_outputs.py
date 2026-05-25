"""Validate market-impact outputs with reproducible spot checks."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

RAW_TUSHARE_DIR = Path("market-impact-study/data/raw/tushare")
PROCESSED_DIR = Path("market-impact-study/data/processed")
TOP_DIR = PROCESSED_DIR / "top_events"
VALIDATION_DIR = PROCESSED_DIR / "validation"
EXPECTED_COMPANY_COUNT = 9
CAR_TOLERANCE = 1e-10
IMPACT_TOLERANCE = 1e-6

COMPANY_CODES = [
    "300590.SZ",
    "603236.SH",
    "300098.SZ",
    "300638.SZ",
    "002313.SZ",
    "002970.SZ",
    "688159.SH",
    "002881.SZ",
    "301608.SZ",
]

WINDOWS = {
    "m1_p1": (-1, 1),
    "p0_p5": (0, 5),
    "p0_p20": (0, 20),
    "p0_p60": (0, 60),
}


def parse_trade_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")


def load_market_panel() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ts_code in COMPANY_CODES:
        daily_path = RAW_TUSHARE_DIR / "daily" / f"{ts_code}.csv"
        basic_path = RAW_TUSHARE_DIR / "daily_basic" / f"{ts_code}.csv"
        if not daily_path.exists() or not basic_path.exists():
            continue
        daily = pd.read_csv(daily_path, dtype={"trade_date": str})
        basic = pd.read_csv(basic_path, dtype={"trade_date": str})
        merged = daily.merge(
            basic[["ts_code", "trade_date", "total_mv", "turnover_rate", "volume_ratio"]],
            on=["ts_code", "trade_date"],
            how="left",
        )
        frames.append(merged)

    panel = pd.concat(frames, ignore_index=True)
    panel["trade_dt"] = parse_trade_date(panel["trade_date"])
    panel["ret"] = pd.to_numeric(panel["pct_chg"], errors="coerce") / 100
    for column in ["total_mv", "turnover_rate", "volume_ratio"]:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    panel = panel.sort_values(["ts_code", "trade_dt"]).reset_index(drop=True)

    peer_ret = panel.pivot_table(index="trade_dt", columns="ts_code", values="ret", aggfunc="first")
    for ts_code in COMPANY_CODES:
        others = [column for column in peer_ret.columns if column != ts_code]
        mask = panel["ts_code"] == ts_code
        panel.loc[mask, "peer_ret_ex_self"] = panel.loc[mask, "trade_dt"].map(peer_ret[others].mean(axis=1))
    panel["abret_peer"] = panel["ret"] - panel["peer_ret_ex_self"]
    return panel


def window_sum(stock: pd.DataFrame, pos: int, start: int, end: int, column: str) -> tuple[float, int, int]:
    left = max(0, pos + start)
    right = min(len(stock) - 1, pos + end)
    expected = end - start + 1
    if right < left:
        return math.nan, 0, expected
    return float(stock.loc[left:right, column].sum(skipna=True)), right - left + 1, expected


def recheck_car(panel: pd.DataFrame, sample: pd.DataFrame) -> pd.DataFrame:
    stock_panels = {
        ts_code: group.sort_values("trade_dt").reset_index(drop=True) for ts_code, group in panel.groupby("ts_code")
    }
    rows: list[dict[str, object]] = []
    for _, event in sample.iterrows():
        ts_code = str(event["ts_code"])
        stock = stock_panels.get(ts_code)
        row = {
            "analysis_group_id": event.get("analysis_group_id", ""),
            "事件日期": event.get("event_date", ""),
            "公司": event.get("company", ""),
            "事件类型": event.get("primary_category", ""),
            "事件标题": event.get("title", ""),
            "复核状态": "missing_price",
        }
        if stock is None or stock.empty:
            rows.append(row)
            continue
        event_dt = pd.to_datetime(event.get("event_date", ""), errors="coerce")
        positions = stock.index[stock["trade_dt"] >= event_dt].tolist()
        if not positions:
            row["复核状态"] = "after_price_coverage"
            rows.append(row)
            continue
        pos = int(positions[0])
        pre_pos = max(0, pos - 1)
        pre_total_mv = stock.loc[pre_pos, "total_mv"]
        row["对齐交易日"] = stock.loc[pos, "trade_dt"].strftime("%Y-%m-%d")
        row["事件前总市值_亿元"] = pre_total_mv / 10000
        mismatches = []
        for label, (start, end) in WINDOWS.items():
            car, actual, expected = window_sum(stock, pos, start, end, "abret_peer")
            impact = pre_total_mv * car / 10000 if pd.notna(pre_total_mv) and pd.notna(car) else math.nan
            recorded_car = pd.to_numeric(event.get(f"car_{label}", math.nan), errors="coerce")
            recorded_impact = pd.to_numeric(event.get(f"abnormal_mv_impact_yi_{label}", math.nan), errors="coerce")
            row[f"复算CAR_{label}"] = car
            row[f"原表CAR_{label}"] = recorded_car
            row[f"CAR差异_{label}"] = car - recorded_car
            row[f"复算异常市值影响_亿元_{label}"] = impact
            row[f"原表异常市值影响_亿元_{label}"] = recorded_impact
            row[f"窗口覆盖_{label}"] = f"{actual}/{expected}"
            if abs(car - recorded_car) > CAR_TOLERANCE:
                mismatches.append(f"car_{label}")
            if pd.notna(recorded_impact) and abs(impact - recorded_impact) > IMPACT_TOLERANCE:
                mismatches.append(f"impact_{label}")
        row["复核状态"] = "pass" if not mismatches else "mismatch:" + ",".join(mismatches)
        rows.append(row)
    return pd.DataFrame(rows)


def check_outputs(panel: pd.DataFrame) -> pd.DataFrame:
    checks: list[dict[str, object]] = []

    def add_check(name: str, *, passed: bool, detail: str) -> None:
        checks.append({"检查项": name, "是否通过": "通过" if passed else "需处理", "详情": detail})

    daily_files = list((RAW_TUSHARE_DIR / "daily").glob("*.csv"))
    basic_files = list((RAW_TUSHARE_DIR / "daily_basic").glob("*.csv"))
    add_check(
        "9家公司日行情文件", passed=len(daily_files) >= EXPECTED_COMPANY_COUNT, detail=f"daily文件数={len(daily_files)}"
    )
    add_check(
        "9家公司市值估值文件",
        passed=len(basic_files) >= EXPECTED_COMPANY_COUNT,
        detail=f"daily_basic文件数={len(basic_files)}",
    )

    event_candidates = pd.read_csv(PROCESSED_DIR / "event_candidates.csv", dtype=str)
    analysis_groups = pd.read_csv(PROCESSED_DIR / "event_analysis_groups_scored.csv", dtype=str)
    status = pd.read_csv(PROCESSED_DIR / "car_status_summary.csv", dtype=str)
    add_check("事件候选池非空", passed=len(event_candidates) > 0, detail=f"行数={len(event_candidates)}")
    add_check("分析事件组非空", passed=len(analysis_groups) > 0, detail=f"行数={len(analysis_groups)}")
    add_check(
        "分析事件组小于原始候选",
        passed=len(analysis_groups) < len(event_candidates),
        detail=f"{len(analysis_groups)} < {len(event_candidates)}",
    )
    add_check("CAR状态表存在", passed=not status.empty, detail=status.to_dict(orient="records").__repr__())

    if "has_pdf" in event_candidates.columns and "local_pdf_path" in event_candidates.columns:
        pdf_rows = event_candidates[event_candidates["has_pdf"].astype(str) == "1"]
        missing_pdf = [
            path for path in pdf_rows["local_pdf_path"].dropna().head(2000) if path and not Path(path).exists()
        ]
        add_check("已挂接PDF路径存在", passed=not missing_pdf, detail=f"抽查/检查缺失数={len(missing_pdf)}")

    chinese_outputs = [
        "移为自身事件Top100_中文.csv",
        "竞品关键动作Top100_中文.csv",
        "竞品事件对移为外溢Top50_中文.csv",
        "竞品关键动作综合评分Top50_中文.csv",
        "事件类型影响汇总_中文.csv",
    ]
    missing = [name for name in chinese_outputs if not (PROCESSED_DIR / name).exists()]
    add_check("中文分析表已生成", passed=not missing, detail=f"缺失={missing}")

    max_trade_date = panel["trade_dt"].max().strftime("%Y-%m-%d")
    min_trade_date = panel["trade_dt"].min().strftime("%Y-%m-%d")
    add_check("行情日期覆盖可追溯", passed=True, detail=f"{min_trade_date} 至 {max_trade_date}")
    return pd.DataFrame(checks)


def build_sample() -> pd.DataFrame:
    groups = pd.read_csv(PROCESSED_DIR / "event_analysis_groups_scored.csv")
    groups = groups[groups["car_status"] == "ok"].copy()
    frames = [
        groups.sort_values("event_priority_score", ascending=False).head(8),
        groups.sort_values("abnormal_mv_impact_yi_p0_p20", ascending=False).head(6),
        groups.sort_values("abnormal_mv_impact_yi_p0_p20", ascending=True).head(6),
        groups.sample(n=min(10, len(groups)), random_state=20260525),
    ]
    sample = pd.concat(frames, ignore_index=True)
    return sample.drop_duplicates(subset=["analysis_group_id"]).head(30)


def write_report(checks: pd.DataFrame, recheck: pd.DataFrame) -> None:
    passed = (checks["是否通过"] == "通过").sum()
    failed = len(checks) - passed
    car_pass = (recheck["复核状态"] == "pass").sum()
    car_failed = len(recheck) - car_pass
    report = f"""# 数据与计算验证报告

## 结论

- 基础数据检查：{passed} 项通过，{failed} 项需处理。
- CAR 抽样复算：{car_pass} 条通过，{car_failed} 条不一致或未覆盖。

## 当前计算口径

- 日收益：使用 Tushare `daily.pct_chg / 100`。
- 基准收益：同日其他 8 家竞品日收益等权平均，剔除事件公司自身。
- 异常收益：公司日收益 - 剔除自身竞品组合收益。
- CAR：按交易日窗口累计异常收益。
- 异常市值影响：事件前一交易日总市值 × CAR。
- 单位：Tushare `daily_basic.total_mv` 为万元，输出异常市值影响时除以 10000 转为亿元。

## 复核产物

- `data_quality_checks.csv`：基础数据和输出完整性检查。
- `car_recheck_samples.csv`：从原始行情重新复算的 CAR 抽样明细。

## 仍需人工确认

- 事件分类是规则初版，Top 事件进入报告前要逐条复核。
- 当前是竞品组合基准，未做指数基准、滚动 beta 和显著性检验。
- 同日多事件已按公司+日期+类别聚合，但“真正是哪条事件驱动”仍需结合公告原文和时间线判断。
"""
    (VALIDATION_DIR / "validation_report.md").write_text(report, encoding="utf-8")


def main() -> int:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    panel = load_market_panel()
    checks = check_outputs(panel)
    sample = build_sample()
    recheck = recheck_car(panel, sample)
    checks.to_csv(VALIDATION_DIR / "data_quality_checks.csv", index=False, encoding="utf-8-sig")
    recheck.to_csv(VALIDATION_DIR / "car_recheck_samples.csv", index=False, encoding="utf-8-sig")
    write_report(checks, recheck)
    sys.stdout.write(f"report={VALIDATION_DIR / 'validation_report.md'}\n")
    sys.stdout.write(checks.to_string(index=False) + "\n")
    sys.stdout.write(recheck["复核状态"].value_counts(dropna=False).to_string() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

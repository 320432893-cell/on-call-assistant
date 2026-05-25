"""Collect public event-candidate datasets through AKShare wrappers."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import akshare as ak
import pandas as pd

OUTPUT_DIR = Path("market-impact-study/data/raw/akshare")
START_DATE = "20090101"
END_DATE = "20260525"

COMPANIES = [
    {"name": "移为通信", "symbol": "300590"},
    {"name": "移远通信", "symbol": "603236"},
    {"name": "高新兴", "symbol": "300098"},
    {"name": "广和通", "symbol": "300638"},
    {"name": "日海智能", "symbol": "002313"},
    {"name": "锐明技术", "symbol": "002970"},
    {"name": "有方科技", "symbol": "688159"},
    {"name": "美格智能", "symbol": "002881"},
    {"name": "博实结", "symbol": "301608"},
]


@dataclass
class Job:
    name: str
    runner: Callable[[str], pd.DataFrame]


def save_df(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def normalize_df(df: pd.DataFrame, company: dict[str, str]) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    df = df.copy()
    df.insert(0, "LOCAL_COMPANY_NAME", company["name"])
    df.insert(1, "LOCAL_SYMBOL", company["symbol"])
    return df


def run_company_job(job: Job, company: dict[str, str]) -> tuple[str, int, str]:
    path = OUTPUT_DIR / job.name / f"{company['symbol']}.csv"
    try:
        df = normalize_df(job.runner(company["symbol"]), company)
        save_df(path, df)
        return ("ok" if len(df) else "empty", len(df), "")
    except Exception as exc:  # noqa: BLE001
        return ("error", 0, f"{type(exc).__name__}: {exc}")
    finally:
        time.sleep(0.35)


def main() -> int:
    jobs = [
        Job(
            "cninfo_disclosure_report",
            lambda symbol: ak.stock_zh_a_disclosure_report_cninfo(
                symbol=symbol,
                market="沪深京",
                start_date=START_DATE,
                end_date=END_DATE,
            ),
        ),
        Job(
            "cninfo_disclosure_relation",
            lambda symbol: ak.stock_zh_a_disclosure_relation_cninfo(
                symbol=symbol,
                market="沪深京",
                start_date=START_DATE,
                end_date=END_DATE,
            ),
        ),
        Job(
            "eastmoney_individual_notice",
            lambda symbol: ak.stock_individual_notice_report(
                security=symbol,
                symbol="全部",
                begin_date=START_DATE,
                end_date=END_DATE,
            ),
        ),
        Job("eastmoney_research_report", lambda symbol: ak.stock_research_report_em(symbol=symbol)),
        Job("eastmoney_stock_news", lambda symbol: ak.stock_news_em(symbol=symbol)),
        Job("cninfo_irm_questions", lambda symbol: ak.stock_irm_cninfo(symbol=symbol)),
        Job("sina_institute_recommend", lambda symbol: ak.stock_institute_recommend_detail(symbol=symbol)),
    ]

    statuses: list[dict[str, object]] = []
    for job in jobs:
        combined: list[pd.DataFrame] = []
        read_errors: list[str] = []
        for company in COMPANIES:
            status, rows, message = run_company_job(job, company)
            path = OUTPUT_DIR / job.name / f"{company['symbol']}.csv"
            statuses.append(
                {
                    "dataset": job.name,
                    "company": company["name"],
                    "symbol": company["symbol"],
                    "status": status,
                    "rows": rows,
                    "path": str(path),
                    "message": message,
                }
            )
            if status == "ok":
                try:
                    combined.append(pd.read_csv(path))
                except (OSError, pd.errors.ParserError) as exc:
                    read_errors.append(f"{path}: {type(exc).__name__}: {exc}")
        if combined:
            save_df(OUTPUT_DIR / job.name / "all_companies.csv", pd.concat(combined, ignore_index=True))
        if read_errors:
            (OUTPUT_DIR / job.name / "_read_errors.txt").write_text("\n".join(read_errors), encoding="utf-8")

    summary_df = pd.DataFrame(statuses)
    save_df(OUTPUT_DIR / "_collection_summary.csv", summary_df)
    print(summary_df.groupby(["dataset", "status"]).size().to_string())
    print(f"summary={OUTPUT_DIR / '_collection_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

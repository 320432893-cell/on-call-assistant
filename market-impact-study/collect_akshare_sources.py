"""Collect public event-candidate datasets through AKShare wrappers."""
# 职责：通过 AKShare 采集 universe 内公司的公开公告/研报/新闻等事件候选源，落盘 data/raw/akshare。
# 不做什么：不合并/不去重/不建统一事件表；不改 universe 口径。
# 允许依赖层：标准库、akshare、pandas、peer_universe(口径)。
# 谁不应该 import：事件/建模/测试不应 import 本采集入口；它们应读 data/raw/akshare 产物。

from __future__ import annotations

import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import akshare as ak
import pandas as pd
from peer_universe import load_companies

OUTPUT_DIR = Path("market-impact-study/data/raw/akshare")
# Research subject 移为 listed 2017; pre-2016 peer events add little and make the
# eastmoney notice pagination very slow (~8s/page), so the history window starts 2016.
START_DATE = "20160101"
END_DATE = "20260615"
DEFAULT_TIMEOUT = 40  # per-call hard cap (SIGALRM); cninfo can hang with no socket timeout

COMPANIES = load_companies()


class _CallTimeoutError(Exception):
    pass


def _on_alarm(signum, frame):  # noqa: ARG001
    raise _CallTimeoutError


@dataclass
class Job:
    name: str
    runner: Callable[[str], pd.DataFrame]
    timeout: int = DEFAULT_TIMEOUT  # eastmoney notice pulls full history (~90s/firm), needs a bigger cap


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
    old_handler = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(job.timeout)
    try:
        df = normalize_df(job.runner(company["symbol"]), company)
        save_df(path, df)
        return ("ok" if len(df) else "empty", len(df), "")
    except _CallTimeoutError:
        return ("timeout", 0, f"timeout>{job.timeout}s")
    except Exception as exc:  # noqa: BLE001
        return ("error", 0, f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        time.sleep(0.35)


def main() -> int:
    # Eastmoney endpoints are fast (sub-second) and carry the primary event source
    # (individual notices); cninfo endpoints are slow/flaky, so run them LAST so the
    # core data lands first and a cninfo stall only delays the supplementary sources.
    jobs = [
        Job(
            "eastmoney_individual_notice",
            lambda symbol: ak.stock_individual_notice_report(
                security=symbol,
                symbol="全部",
                begin_date=START_DATE,
                end_date=END_DATE,
            ),
            timeout=180,
        ),
        Job("eastmoney_research_report", lambda symbol: ak.stock_research_report_em(symbol=symbol)),
        Job("eastmoney_stock_news", lambda symbol: ak.stock_news_em(symbol=symbol)),
        Job("cninfo_irm_questions", lambda symbol: ak.stock_irm_cninfo(symbol=symbol)),
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
        # sina_institute_recommend dropped: the Sina endpoint is dead (returns HTML), per project decision.
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

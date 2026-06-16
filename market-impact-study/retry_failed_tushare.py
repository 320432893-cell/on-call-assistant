"""Retry only the transient (SSL/URL) failures from the last Tushare collection.

Reads data/raw/tushare/_collection_summary.csv, re-runs every task whose status
was 'error' and whose dataset is NOT anns_d (anns_d is a genuine permission deny,
retrying is pointless). Uses exponential backoff for the flaky-SSL endpoints.
Token via TUSHARE_TOKEN, never written to disk.

Run from repo root:
  TUSHARE_TOKEN=... .venv/bin/python market-impact-study/retry_failed_tushare.py
"""
# 职责：只重跑上次 Tushare 采集里的瞬态(SSL/URL)失败任务，带指数退避，补齐落盘。
# 不做什么：不发起新一轮全量采集；不重试 anns_d(真权限拒绝)；不改 universe 口径；token 不落盘。
# 允许依赖层：标准库、pandas、同目录 collect_tushare_data(采集层)、data/raw/tushare 下的采集汇总与产物。
# 谁不应该 import：建模/特征/SSOT 脚本与测试不应 import 本维护入口；它是采集后的一次性补采工具。

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_tushare_data as c

SUMMARY = c.OUTPUT_DIR / "_collection_summary.csv"
MAX_RETRY = 4


def call_with_backoff(token, api, params, fields):
    for attempt in range(MAX_RETRY):
        resp = c.call_tushare(token, api, params, fields)
        if resp.get("code") == 0:
            return resp
        time.sleep(1.5 * (attempt + 1))
    return resp


def main() -> int:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        print("TUSHARE_TOKEN is required.", file=sys.stderr)
        return 2
    s = pd.read_csv(SUMMARY)
    failed = s[(s["status"] == "error") & (s["dataset"] != "anns_d")].copy()
    print(f"retrying {len(failed)} transient failures (anns_d permission-denies skipped)")

    by_code = {row["ts_code"]: row for _, row in pd.read_csv(c.UNIVERSE_PATH).iterrows()}
    fixed, still = 0, []
    for _, row in failed.iterrows():
        dataset = row["dataset"]
        ts_code = str(row["scope"]).split(":")[-1]
        fields = c.DATASETS.get(dataset)
        if fields is None:
            continue
        list_date = str(by_code.get(ts_code, {}).get("list_date", "20100101")).split(".")[0]
        params = {"ts_code": ts_code}
        if dataset not in {"dividend", "pledge_stat"}:
            params.update({"start_date": list_date, "end_date": c.TODAY})
        path = c.OUTPUT_DIR / dataset / f"{ts_code}.csv"
        for attempt in range(MAX_RETRY):
            try:
                resp = call_with_backoff(token, dataset, params, fields)
                if resp.get("code") != 0:
                    still.append((dataset, ts_code, str(resp.get("msg", ""))[:50]))
                    break
                fnames, rows = c.response_rows(resp)
                c.write_rows(path, fnames, rows)
                print(f"  ok  {dataset:16} {ts_code}  rows={len(rows)}")
                fixed += 1
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == MAX_RETRY - 1:
                    still.append((dataset, ts_code, f"{type(exc).__name__}"))
                else:
                    time.sleep(2.0 * (attempt + 1))
        time.sleep(0.3)

    print(f"\nfixed={fixed}  still_failing={len(still)}")
    for d, t, m in still:
        print(f"  STILL  {d:16} {t}  {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

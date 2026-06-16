"""Single source of truth for the study's company universe.

Reads data/peer_universe.csv (rows with include==1) so that expanding or trimming
the cross-section is a one-file edit, not a code change in every collector. All
collectors (Tushare market data, AKShare disclosures, Eastmoney IR) import this.

Each returned company dict has: name, ts_code (e.g. 300590.SZ), symbol (300590),
list_date (YYYYMMDD).
"""
# 职责：研究公司 universe 的单一真相源 loader——读 data/peer_universe.csv(include==1)供所有采集/管道共享。
# 不做什么：不采集/不清洗/不算任何指标；不写文件(只读口径表)。
# 允许依赖层：仅标准库 + data/peer_universe.csv；可被任何采集/管道层 import。
# 谁不应该 import：本模块不应 import 采集/建模/特征层，保持作为无业务依赖的口径底座。

from __future__ import annotations

import csv
import sys
from pathlib import Path

UNIVERSE_PATH = Path("market-impact-study/data/peer_universe.csv")

# Original 9-firm niche, used only if peer_universe.csv is absent.
_FALLBACK = [
    {"name": "移为通信", "ts_code": "300590.SZ", "list_date": "20170111"},
    {"name": "移远通信", "ts_code": "603236.SH", "list_date": "20190716"},
    {"name": "高新兴", "ts_code": "300098.SZ", "list_date": "20100728"},
    {"name": "广和通", "ts_code": "300638.SZ", "list_date": "20170413"},
    {"name": "日海智能", "ts_code": "002313.SZ", "list_date": "20091203"},
    {"name": "锐明技术", "ts_code": "002970.SZ", "list_date": "20191217"},
    {"name": "有方科技", "ts_code": "688159.SH", "list_date": "20200123"},
    {"name": "美格智能", "ts_code": "002881.SZ", "list_date": "20170622"},
    {"name": "博实结", "ts_code": "301608.SZ", "list_date": "20240801"},
]


def _with_symbol(rec: dict[str, str]) -> dict[str, str]:
    rec = dict(rec)
    rec["symbol"] = rec["ts_code"].split(".")[0]
    return rec


def load_companies() -> list[dict[str, str]]:
    if not UNIVERSE_PATH.exists():
        print(f"peer_universe.csv not found at {UNIVERSE_PATH}; using fallback 9 firms.", file=sys.stderr)
        return [_with_symbol(r) for r in _FALLBACK]
    out: list[dict[str, str]] = []
    with UNIVERSE_PATH.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("include", "")).strip() not in {"1", "1.0", "true", "True"}:
                continue
            out.append(
                _with_symbol(
                    {
                        "name": row["name"].strip(),
                        "ts_code": row["ts_code"].strip(),
                        "list_date": str(row["list_date"]).strip().split(".")[0],
                    }
                )
            )
    if not out:
        print("peer_universe.csv had no include==1 rows; using fallback 9 firms.", file=sys.stderr)
        return [_with_symbol(r) for r in _FALLBACK]
    return out

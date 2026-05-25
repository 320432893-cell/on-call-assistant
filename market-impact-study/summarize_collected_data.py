"""Summarize collected raw datasets for handoff and planning."""

from __future__ import annotations

import csv
import json
import sys
from contextlib import suppress
from pathlib import Path

RAW_DIR = Path("market-impact-study/data/raw")
OUTPUT_DIR = Path("market-impact-study/data/summary")

csv.field_size_limit(sys.maxsize)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    rows: list[dict[str, object]] = []

    for summary_path in sorted(RAW_DIR.glob("**/_collection_summary.csv")):
        source = summary_path.relative_to(RAW_DIR).parts[0]
        for row in read_csv(summary_path):
            dataset = row.get("dataset") or source
            company = row.get("company") or row.get("scope") or ""
            symbol = row.get("symbol") or ""
            status = row.get("status") or ""
            count = row.get("rows") or row.get("row_count") or "0"
            path = row.get("path") or ""
            message = (row.get("message") or "")[:500]
            rows.append(
                {
                    "source": source,
                    "dataset": dataset,
                    "company_or_scope": company,
                    "symbol": symbol,
                    "status": status,
                    "rows": count,
                    "path": path,
                    "message": message,
                }
            )

    write_csv(
        OUTPUT_DIR / "collection_inventory.csv",
        rows,
        ["source", "dataset", "company_or_scope", "symbol", "status", "rows", "path", "message"],
    )

    rollup: dict[str, dict[str, int]] = {}
    for row in rows:
        key = f"{row['source']}/{row['dataset']}"
        rollup.setdefault(key, {"ok": 0, "empty": 0, "error": 0, "rows": 0})
        status = str(row["status"])
        if status in rollup[key]:
            rollup[key][status] += 1
        with suppress(ValueError):
            rollup[key]["rows"] += int(float(str(row["rows"] or 0)))

    (OUTPUT_DIR / "collection_rollup.json").write_text(
        json.dumps(rollup, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for key, value in sorted(rollup.items()):
        print(key, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

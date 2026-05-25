"""Build a RAG ingest manifest from downloaded Eastmoney notice PDFs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = PROJECT_DIR / "data/documents/eastmoney_notice_pdf_manifest.csv"
DEFAULT_OUTPUT = PROJECT_DIR / "data/processed/rag_ingest_manifest.csv"
SOURCE_TYPE = "eastmoney_notice_pdf"

OUTPUT_FIELDS = [
    "document_id",
    "company",
    "symbol",
    "source_type",
    "title",
    "publish_date",
    "source_url",
    "pdf_url",
    "local_path",
    "event_candidate_id",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def to_ingest_row(row: dict[str, str]) -> dict[str, str]:
    code = (row.get("announcement_code") or "").strip()
    symbol = (row.get("symbol") or "").strip()
    return {
        "document_id": f"{SOURCE_TYPE}:{symbol}:{code}",
        "company": (row.get("company") or "").strip(),
        "symbol": symbol,
        "source_type": SOURCE_TYPE,
        "title": (row.get("title") or "").strip(),
        "publish_date": (row.get("notice_date") or "").strip(),
        "source_url": (row.get("source_url") or "").strip(),
        "pdf_url": (row.get("pdf_url") or "").strip(),
        "local_path": (row.get("local_path") or "").strip(),
        "event_candidate_id": "",
    }


def build_manifest(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    output: list[dict[str, str]] = []
    stats = {
        "input_rows": len(rows),
        "written_rows": 0,
        "skipped_bad_status": 0,
        "skipped_missing_code": 0,
        "skipped_missing_pdf": 0,
    }

    seen: set[str] = set()
    for row in rows:
        if row.get("status") not in {"ok", "exists"}:
            stats["skipped_bad_status"] += 1
            continue

        code = (row.get("announcement_code") or "").strip()
        if not code:
            stats["skipped_missing_code"] += 1
            continue

        local_path = Path((row.get("local_path") or "").strip())
        if not local_path.exists():
            stats["skipped_missing_pdf"] += 1
            continue

        ingest_row = to_ingest_row(row)
        document_id = ingest_row["document_id"]
        if document_id in seen:
            continue
        seen.add(document_id)
        output.append(ingest_row)

    output.sort(key=lambda item: (item["symbol"], item["publish_date"], item["document_id"]))
    stats["written_rows"] = len(output)
    return output, stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_csv(args.input)
    output_rows, stats = build_manifest(rows)
    write_csv(args.output, output_rows)

    print(f"input={args.input}")
    print(f"output={args.output}")
    print(
        " ".join(
            [
                f"input_rows={stats['input_rows']}",
                f"written_rows={stats['written_rows']}",
                f"skipped_bad_status={stats['skipped_bad_status']}",
                f"skipped_missing_code={stats['skipped_missing_code']}",
                f"skipped_missing_pdf={stats['skipped_missing_pdf']}",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

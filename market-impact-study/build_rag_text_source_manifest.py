"""生成第二轮 RAG 文本来源清单。"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_EVENTS = PROJECT_DIR / "data/processed/event_candidates_scored.csv"
DEFAULT_PDF_MANIFEST = PROJECT_DIR / "data/documents/eastmoney_notice_pdf_manifest.csv"
DEFAULT_OUTPUT = PROJECT_DIR / "data/processed/rag_text_source_manifest.csv"
DEFAULT_LEGACY_OUTPUT = PROJECT_DIR / "data/processed/rag_ingest_manifest.csv"

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
    "text_source",
    "evidence_strength",
    "source_text",
]

LEGACY_OUTPUT_FIELDS = [
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

TEXT_SOURCE_BY_EVENT_SOURCE = {
    "research_report": "research_report",
    "institution_survey": "ir_record",
    "irm_qa": "irm_qa",
    "news": "news",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def compact_text(*values: object) -> str:
    parts = [" ".join(str(value or "").split()) for value in values]
    return "\n".join(part for part in parts if part)


def announcement_code(*values: object) -> str:
    for value in values:
        match = re.search(r"(AN\d+)", str(value or ""))
        if match:
            return match.group(1)
    return ""


def evidence_strength(text_source: str) -> str:
    if text_source in {"pdf", "notice_api"}:
        return "strong"
    if text_source in {"research_report", "ir_record", "irm_qa", "news"}:
        return "auxiliary"
    return "weak"


def pdf_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    output: list[dict[str, Any]] = []
    by_code: dict[str, dict[str, str]] = {}
    for row in rows:
        code = (row.get("announcement_code") or "").strip()
        symbol = (row.get("symbol") or "").strip()
        if code:
            by_code[code] = row
        if row.get("status") not in {"ok", "exists"}:
            continue
        local_path = Path((row.get("local_path") or "").strip())
        if not code or not local_path.exists():
            continue
        output.append(
            {
                "document_id": f"eastmoney_notice_pdf:{symbol}:{code}",
                "company": (row.get("company") or "").strip(),
                "symbol": symbol,
                "source_type": "eastmoney_notice_pdf",
                "title": (row.get("title") or "").strip(),
                "publish_date": (row.get("notice_date") or "").strip(),
                "source_url": (row.get("source_url") or "").strip(),
                "pdf_url": (row.get("pdf_url") or "").strip(),
                "local_path": str(local_path),
                "event_candidate_id": "",
                "text_source": "pdf",
                "evidence_strength": "strong",
                "source_text": "",
            }
        )
    return output, by_code


def notice_api_row(event: dict[str, str], pdf_by_code: dict[str, dict[str, str]]) -> dict[str, Any] | None:
    code = announcement_code(event.get("source_url"), event.get("pdf_url"), event.get("local_pdf_path"))
    if not code:
        return None
    if code in pdf_by_code and Path((pdf_by_code[code].get("local_path") or "").strip()).exists():
        return None
    pdf = pdf_by_code.get(code, {})
    symbol = (event.get("symbol") or "").strip()
    return {
        "document_id": f"eastmoney_notice_api:{symbol}:{code}",
        "company": (event.get("company") or "").strip(),
        "symbol": symbol,
        "source_type": "announcement",
        "title": (event.get("title") or "").strip(),
        "publish_date": (event.get("event_date") or "").strip(),
        "source_url": (event.get("source_url") or pdf.get("source_url") or "").strip(),
        "pdf_url": (event.get("pdf_url") or pdf.get("pdf_url") or "").strip(),
        "local_path": "",
        "event_candidate_id": (event.get("event_id") or "").strip(),
        "text_source": "notice_api",
        "evidence_strength": "strong",
        "source_text": "",
    }


def structured_event_row(event: dict[str, str]) -> dict[str, Any] | None:
    source_type = (event.get("source_type") or "").strip()
    text_source = TEXT_SOURCE_BY_EVENT_SOURCE.get(source_type)
    if not text_source:
        return None
    text = compact_text(
        f"标题：{event.get('title', '')}",
        f"摘要：{event.get('summary', '')}",
        f"原始分类：{event.get('raw_category', '')}",
        f"评级：{event.get('rating', '')}",
        f"机构：{event.get('institution', '')}",
        f"接待人：{event.get('receptionist', '')}",
    )
    if not text:
        return None
    symbol = (event.get("symbol") or "").strip()
    event_id = (event.get("event_id") or "").strip()
    return {
        "document_id": f"{text_source}:{symbol}:{event_id}",
        "company": (event.get("company") or "").strip(),
        "symbol": symbol,
        "source_type": source_type,
        "title": (event.get("title") or "").strip(),
        "publish_date": (event.get("event_date") or "").strip(),
        "source_url": (event.get("source_url") or "").strip(),
        "pdf_url": (event.get("pdf_url") or "").strip(),
        "local_path": (event.get("local_pdf_path") or "").strip(),
        "event_candidate_id": event_id,
        "text_source": text_source,
        "evidence_strength": evidence_strength(text_source),
        "source_text": text,
    }


def build_manifest(
    events: list[dict[str, str]], pdf_manifest: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows, pdf_by_code = pdf_rows(pdf_manifest)
    stats = {
        "pdf_rows": len(rows),
        "notice_api_rows": 0,
        "structured_rows": 0,
        "deduped_rows": 0,
    }

    for event in events:
        if (event.get("source_type") or "").strip() == "announcement":
            row = notice_api_row(event, pdf_by_code)
            if row:
                rows.append(row)
                stats["notice_api_rows"] += 1
                continue
        row = structured_event_row(event)
        if row:
            rows.append(row)
            stats["structured_rows"] += 1

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        document_id = str(row.get("document_id", ""))
        if document_id and document_id not in deduped:
            deduped[document_id] = row
    output = sorted(deduped.values(), key=lambda item: (item["symbol"], item["publish_date"], item["document_id"]))
    stats["deduped_rows"] = len(output)
    return output, stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--pdf-manifest", type=Path, default=DEFAULT_PDF_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--legacy-output", type=Path, default=DEFAULT_LEGACY_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, stats = build_manifest(read_csv(args.events), read_csv(args.pdf_manifest))
    write_csv(args.output, rows, OUTPUT_FIELDS)
    legacy_rows = [row for row in rows if row.get("text_source") == "pdf"]
    write_csv(args.legacy_output, legacy_rows, LEGACY_OUTPUT_FIELDS)
    print(f"events={args.events}")
    print(f"output={args.output}")
    print(f"legacy_output={args.legacy_output}")
    print(" ".join(f"{key}={value}" for key, value in stats.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

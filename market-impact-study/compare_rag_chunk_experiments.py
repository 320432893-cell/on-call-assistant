"""对比 RAG chunk 预处理实验组合的体积和切分结果。"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from extract_rag_notice_texts import (
    DEFAULT_MANIFEST,
    EXPERIMENT_OVERLAP_CHARS,
    MAX_CHUNK_CHARS,
    OVERLAP_CHARS,
    extract_chunks,
    extract_experiment_chunks,
    read_manifest,
)

DEFAULT_OUTPUT = PROJECT_DIR / "data/processed/rag_chunk_experiment_summary.csv"
DEFAULT_SAMPLE_OUTPUT = PROJECT_DIR / "data/processed/rag_chunk_experiment_samples.csv"
DEFAULT_TEXT_SOURCES = ["pdf", "research_report", "ir_record", "irm_qa", "news"]

SUMMARY_FIELDS = [
    "strategy",
    "preprocess",
    "has_prefix",
    "max_chars",
    "overlap",
    "input_rows",
    "documents_with_chunks",
    "documents_failed",
    "chunks",
    "total_chars",
    "avg_chunk_chars",
    "max_chunk_chars_observed",
    "chunks_per_document",
]

SAMPLE_FIELDS = [
    "strategy",
    "document_id",
    "company",
    "symbol",
    "text_source",
    "title",
    "chunk_id",
    "n_chars",
    "text_sample",
]

EXPERIMENT_STRATEGIES = [
    {
        "strategy": "baseline_current",
        "mode": "baseline",
        "preprocess": "basic",
        "has_prefix": False,
        "max_chars": MAX_CHUNK_CHARS,
        "overlap": OVERLAP_CHARS,
    },
    {
        "strategy": "enhanced_clean_only",
        "mode": "experiment",
        "preprocess": "enhanced",
        "has_prefix": False,
        "max_chars": MAX_CHUNK_CHARS,
        "overlap": OVERLAP_CHARS,
    },
    {
        "strategy": "enhanced_prefix_1400_240",
        "mode": "experiment",
        "preprocess": "enhanced",
        "has_prefix": True,
        "max_chars": 1400,
        "overlap": EXPERIMENT_OVERLAP_CHARS,
    },
    {
        "strategy": "enhanced_prefix_1200_240",
        "mode": "experiment",
        "preprocess": "enhanced",
        "has_prefix": True,
        "max_chars": 1200,
        "overlap": EXPERIMENT_OVERLAP_CHARS,
    },
    {
        "strategy": "enhanced_prefix_1000_300",
        "mode": "experiment",
        "preprocess": "enhanced",
        "has_prefix": True,
        "max_chars": 1000,
        "overlap": 300,
    },
]


def filter_rows(rows: list[dict[str, str]], text_sources: set[str]) -> list[dict[str, str]]:
    return [row for row in rows if (row.get("text_source") or "pdf") in text_sources]


def chunk_summary(strategy: dict[str, Any], stats: dict[str, int], chunks: list[dict[str, object]]) -> dict[str, Any]:
    total_chars = sum(int(chunk.get("n_chars") or len(str(chunk.get("text", "")))) for chunk in chunks)
    documents_with_chunks = stats["documents_with_chunks"]
    return {
        "strategy": strategy["strategy"],
        "preprocess": strategy["preprocess"],
        "has_prefix": "1" if strategy["has_prefix"] else "0",
        "max_chars": strategy["max_chars"],
        "overlap": strategy["overlap"],
        "input_rows": stats["input_rows"],
        "documents_with_chunks": documents_with_chunks,
        "documents_failed": stats["documents_failed"],
        "chunks": len(chunks),
        "total_chars": total_chars,
        "avg_chunk_chars": round(total_chars / len(chunks), 2) if chunks else 0,
        "max_chunk_chars_observed": max((int(chunk.get("n_chars") or 0) for chunk in chunks), default=0),
        "chunks_per_document": round(len(chunks) / documents_with_chunks, 2) if documents_with_chunks else 0,
    }


def sample_rows(strategy: str, chunks: list[dict[str, object]], *, limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunks[:limit]:
        rows.append(
            {
                "strategy": strategy,
                "document_id": chunk.get("document_id", ""),
                "company": chunk.get("company", ""),
                "symbol": chunk.get("symbol", ""),
                "text_source": chunk.get("text_source", ""),
                "title": chunk.get("title", ""),
                "chunk_id": chunk.get("chunk_id", ""),
                "n_chars": chunk.get("n_chars", ""),
                "text_sample": " ".join(str(chunk.get("text", "")).split())[:360],
            }
        )
    return rows


def run_strategy(
    strategy: dict[str, Any],
    rows: list[dict[str, str]],
    *,
    limit: int | None,
    text_sources: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    filtered = filter_rows(rows, text_sources)
    if strategy["mode"] == "baseline":
        chunks, stats = extract_chunks(filtered, limit=limit)
    else:
        chunks, stats = extract_experiment_chunks(
            filtered,
            limit=limit,
            preprocess=strategy["preprocess"],
            add_prefix=bool(strategy["has_prefix"]),
            max_chars=int(strategy["max_chars"]),
            overlap=int(strategy["overlap"]),
        )
    return chunk_summary(strategy, stats, chunks), sample_rows(strategy["strategy"], chunks)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--include-text-source", action="append", default=DEFAULT_TEXT_SOURCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-output", type=Path, default=DEFAULT_SAMPLE_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_manifest(args.manifest)
    text_sources = set(args.include_text_source)
    summaries: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for strategy in EXPERIMENT_STRATEGIES:
        summary, sample = run_strategy(strategy, rows, limit=args.limit, text_sources=text_sources)
        summaries.append(summary)
        samples.extend(sample)

    write_csv(args.output, summaries, SUMMARY_FIELDS)
    write_csv(args.sample_output, samples, SAMPLE_FIELDS)
    print(f"output={args.output} rows={len(summaries)}")
    print(f"sample_output={args.sample_output} rows={len(samples)}")
    for summary in summaries:
        print(
            " ".join(
                [
                    f"strategy={summary['strategy']}",
                    f"input_rows={summary['input_rows']}",
                    f"chunks={summary['chunks']}",
                    f"avg_chars={summary['avg_chunk_chars']}",
                    f"chunks_per_doc={summary['chunks_per_document']}",
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

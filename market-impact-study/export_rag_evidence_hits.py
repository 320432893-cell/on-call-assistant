"""Export RAG evidence search hits for market-impact analysis."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest_market_evidence_rag import COLLECTION, close_vectorstore, configure_embedder, load_jsonl, parse_filters

from app.services import get_embedder, get_vectorstore

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CHUNKS = PROJECT_DIR / "data/processed/rag_notice_chunks.jsonl"
DEFAULT_EVENTS = PROJECT_DIR / "data/processed/event_candidates_scored.csv"
DEFAULT_OUTPUT = PROJECT_DIR / "data/processed/rag_evidence_hits.csv"
CSV_FIELDS = [
    "query",
    "rank",
    "score",
    "chunk_id",
    "document_id",
    "company",
    "symbol",
    "source_type",
    "title",
    "publish_date",
    "page_start",
    "page_end",
    "chunk_index",
    "text_source",
    "snippet",
    "source_url",
    "pdf_url",
    "local_path",
    "event_candidate_id",
    "event_title",
    "event_date",
    "date_diff_days",
]

SUMMARY_FIELDS = [
    "event_candidate_id",
    "event_date",
    "event_title",
    "evidence_count",
    "best_score",
    "best_date_diff_days",
    "best_company",
    "best_symbol",
    "best_publish_date",
    "best_title",
    "best_page_start",
    "best_pdf_url",
    "best_local_path",
    "evidence_refs",
]


def compact_text(value: Any, *, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def date_diff_days(left: Any, right: Any) -> int | None:
    left_date = parse_date(left)
    right_date = parse_date(right)
    if left_date is None or right_date is None:
        return None
    return abs((left_date - right_date).days)


def payload_to_row(
    query: str,
    rank: int,
    score: float,
    chunk_id: str,
    payload: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = event or {}
    diff_days = date_diff_days(event.get("event_date"), payload.get("publish_date"))
    return {
        "query": query,
        "rank": rank,
        "score": f"{score:.6f}",
        "chunk_id": chunk_id,
        "document_id": payload.get("document_id", ""),
        "company": payload.get("company", ""),
        "symbol": payload.get("symbol", ""),
        "source_type": payload.get("source_type", ""),
        "title": payload.get("title", ""),
        "publish_date": payload.get("publish_date", ""),
        "page_start": payload.get("page_start", ""),
        "page_end": payload.get("page_end", ""),
        "chunk_index": payload.get("chunk_index", ""),
        "text_source": payload.get("text_source", ""),
        "snippet": payload.get("snippet") or compact_text(payload.get("text")),
        "source_url": payload.get("source_url", ""),
        "pdf_url": payload.get("pdf_url", ""),
        "local_path": payload.get("local_path", ""),
        "event_candidate_id": event.get("event_id") or payload.get("event_candidate_id", ""),
        "event_title": event.get("title", ""),
        "event_date": event.get("event_date", ""),
        "date_diff_days": "" if diff_days is None else diff_days,
    }


def semantic_search(query: str, *, filters: dict[str, str] | None, limit: int) -> list[dict[str, Any]]:
    embedder = get_embedder()
    configure_embedder(embedder)
    vectorstore = get_vectorstore()
    try:
        vector = embedder.encode(query, is_query=True)
        if vector is None:
            raise RuntimeError("embedding failed")
        hits = vectorstore.search_in(COLLECTION, query_vector=vector, limit=limit, filters=filters or None)
        return [payload_to_row(query, rank, hit.score, hit.id, hit.payload) for rank, hit in enumerate(hits, start=1)]
    finally:
        close_vectorstore(vectorstore)


def query_terms(query: str) -> list[str]:
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    return terms or [query.strip()]


def event_title_terms(title: str) -> list[str]:
    normalized = re.sub(r"\s+", "", title.strip())
    if not normalized:
        return []
    if len(normalized) < 6 and not re.search(
        r"\d{4}|问询|回复|激励|回购|减持|增持|定增|重组|收购|出售|分红|业绩|调研", normalized
    ):
        return []

    stopwords = {
        "公告",
        "的公告",
        "关于",
        "公司",
        "股份",
        "有限公司",
        "年度",
        "半年度",
        "报告",
        "全文",
    }
    terms = [normalized]
    for term in re.split(r"[，,。；;：:（）()【】\\[\\]“”\"'、\\s]+", title):
        term = term.strip()
        if len(term) < 3 or term in stopwords:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def keyword_score(text: str, terms: list[str]) -> float:
    if not text:
        return 0.0
    score = 0
    for term in terms:
        score += text.count(term) * max(len(term), 1)
    return float(score)


def matches_filters(row: dict[str, Any], filters: dict[str, str] | None) -> bool:
    if not filters:
        return True
    return all(str(row.get(key, "")) == value for key, value in filters.items())


def chunk_haystack(chunk: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(chunk.get("company", "")),
            str(chunk.get("symbol", "")),
            str(chunk.get("title", "")),
            str(chunk.get("publish_date", "")),
            str(chunk.get("text", "")),
        ]
    )


def keyword_search(
    query: str,
    *,
    chunks_path: Path,
    filters: dict[str, str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    terms = query_terms(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in load_jsonl(chunks_path):
        if not matches_filters(chunk, filters):
            continue
        score = keyword_score(chunk_haystack(chunk), terms)
        if score <= 0:
            continue
        scored.append((score, chunk))

    scored.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("publish_date", "")),
            str(item[1].get("document_id", "")),
            int(item[1].get("chunk_index") or 0),
        )
    )
    rows: list[dict[str, Any]] = []
    for rank, (score, chunk) in enumerate(scored[:limit], start=1):
        payload = {**chunk, "snippet": compact_text(chunk.get("text"))}
        rows.append(payload_to_row(query, rank, score, str(chunk.get("chunk_id", "")), payload))
    return rows


def event_query(event: dict[str, Any], *, max_title_chars: int = 80) -> str:
    company = str(event.get("company", "")).strip()
    title = compact_text(event.get("title", ""), limit=max_title_chars)
    return " ".join(part for part in [company, title] if part)


def event_filters(event: dict[str, Any]) -> dict[str, str]:
    symbol = str(event.get("symbol", "")).strip()
    return {"symbol": symbol} if symbol else {}


def batch_keyword_search(
    *,
    events_path: Path,
    chunks_path: Path,
    limit_per_event: int,
    max_events: int | None = None,
    max_date_diff_days: int | None = 370,
) -> list[dict[str, Any]]:
    chunks = load_jsonl(chunks_path)
    chunks_by_symbol: dict[str, list[tuple[dict[str, Any], str]]] = {}
    all_chunks: list[tuple[dict[str, Any], str]] = []
    for chunk in chunks:
        indexed = (chunk, chunk_haystack(chunk))
        all_chunks.append(indexed)
        symbol = str(chunk.get("symbol", "")).strip()
        if symbol:
            chunks_by_symbol.setdefault(symbol, []).append(indexed)

    rows: list[dict[str, Any]] = []
    with events_path.open(encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        for event_index, event in enumerate(reader, start=1):
            if max_events is not None and event_index > max_events:
                break
            query = event_query(event)
            if not query:
                continue
            filters = event_filters(event)
            candidate_chunks = chunks_by_symbol.get(filters["symbol"], []) if filters.get("symbol") else all_chunks
            terms = event_title_terms(str(event.get("title", "")))
            if not terms:
                continue
            scored: list[tuple[float, dict[str, Any]]] = []
            for chunk, haystack in candidate_chunks:
                if not matches_filters(chunk, filters):
                    continue
                diff_days = date_diff_days(event.get("event_date"), chunk.get("publish_date"))
                if max_date_diff_days is not None and diff_days is not None and diff_days > max_date_diff_days:
                    continue
                score = keyword_score(haystack, terms)
                if score <= 0:
                    continue
                scored.append((score, chunk))
            scored.sort(
                key=lambda item: (
                    -item[0],
                    date_diff_days(event.get("event_date"), item[1].get("publish_date")) or 999999,
                    abs(int(item[1].get("chunk_index") or 0)),
                    str(item[1].get("publish_date", "")),
                )
            )
            for rank, (score, chunk) in enumerate(scored[:limit_per_event], start=1):
                payload = {**chunk, "snippet": compact_text(chunk.get("text"))}
                rows.append(payload_to_row(query, rank, score, str(chunk.get("chunk_id", "")), payload, event=event))
    return rows


def write_csv(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def summarize_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        event_id = row.get("event_candidate_id", "")
        if not event_id:
            continue
        grouped.setdefault(event_id, []).append(row)

    summaries: list[dict[str, Any]] = []
    for event_id, event_rows in grouped.items():
        event_rows.sort(
            key=lambda row: (
                int(row.get("rank") or 999999),
                int(row.get("date_diff_days") or 999999),
                -float(row.get("score") or 0),
            )
        )
        best = event_rows[0]
        refs = []
        for row in event_rows[:3]:
            page = row.get("page_start", "")
            refs.append(f"{row.get('publish_date', '')}《{row.get('title', '')}》p{page}: {row.get('snippet', '')}")
        summaries.append(
            {
                "event_candidate_id": event_id,
                "event_date": best.get("event_date", ""),
                "event_title": best.get("event_title", ""),
                "evidence_count": len(event_rows),
                "best_score": best.get("score", ""),
                "best_date_diff_days": best.get("date_diff_days", ""),
                "best_company": best.get("company", ""),
                "best_symbol": best.get("symbol", ""),
                "best_publish_date": best.get("publish_date", ""),
                "best_title": best.get("title", ""),
                "best_page_start": best.get("page_start", ""),
                "best_pdf_url": best.get("pdf_url", ""),
                "best_local_path": best.get("local_path", ""),
                "evidence_refs": " || ".join(refs),
            }
        )
    summaries.sort(key=lambda row: (row.get("event_date", ""), row.get("event_candidate_id", "")))
    return summaries


def write_summary_csv(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--mode", choices=["semantic", "keyword"], default="semantic")
    search_parser.add_argument("--filter", action="append", default=[], help="Payload filter, e.g. symbol=300590")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    search_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    search_parser.add_argument("--jsonl-output", type=Path, default=None)

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    batch_parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    batch_parser.add_argument("--limit-per-event", type=int, default=3)
    batch_parser.add_argument("--max-events", type=int, default=None)
    batch_parser.add_argument("--max-date-diff-days", type=int, default=370)
    batch_parser.add_argument("--output", type=Path, default=PROJECT_DIR / "data/processed/rag_event_evidence_hits.csv")
    batch_parser.add_argument("--jsonl-output", type=Path, default=None)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument(
        "--hits", type=Path, default=PROJECT_DIR / "data/processed/rag_event_evidence_hits.csv"
    )
    summarize_parser.add_argument(
        "--output", type=Path, default=PROJECT_DIR / "data/processed/rag_event_evidence_summary.csv"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "search":
        filters = parse_filters(args.filter)
        if args.mode == "semantic":
            rows = semantic_search(args.query, filters=filters, limit=args.limit)
        else:
            rows = keyword_search(args.query, chunks_path=args.chunks, filters=filters, limit=args.limit)
        mode_label = args.mode
    elif args.command == "batch":
        rows = batch_keyword_search(
            events_path=args.events,
            chunks_path=args.chunks,
            limit_per_event=args.limit_per_event,
            max_events=args.max_events,
            max_date_diff_days=args.max_date_diff_days,
        )
        mode_label = "batch_keyword"
    else:
        rows = summarize_evidence(read_csv(args.hits))
        write_summary_csv(rows, args.output)
        print(f"mode=summarize rows={len(rows)} output={args.output}")
        return 0

    write_csv(rows, args.output)
    if args.jsonl_output:
        write_jsonl(rows, args.jsonl_output)

    print(f"mode={mode_label} rows={len(rows)} output={args.output}")
    if args.jsonl_output:
        print(f"jsonl_output={args.jsonl_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

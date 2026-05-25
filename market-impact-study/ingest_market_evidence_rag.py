"""Ingest and search market evidence chunks in an isolated Qdrant collection."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import get_embedder, get_vectorstore

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CHUNKS = PROJECT_DIR / "data/processed/rag_notice_chunks.jsonl"
COLLECTION = "market_evidence_documents"
INGEST_BATCH = 16
EMBED_TEXT_CHARS = 600
EMBED_MAX_SEQ_LENGTH = 512


def close_vectorstore(vectorstore: Any) -> None:
    """Close embedded Qdrant so one-shot CLI commands release the local lock."""
    client = getattr(vectorstore, "_client", None)
    close = getattr(client, "close", None)
    if callable(close):
        close()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def configure_embedder(embedder: Any) -> None:
    model = getattr(embedder, "_model", None)
    if model is not None and hasattr(model, "max_seq_length"):
        model.max_seq_length = EMBED_MAX_SEQ_LENGTH


def build_passage(chunk: dict[str, Any]) -> str:
    text = " ".join(str(chunk.get("text", "")).split())
    if len(text) > EMBED_TEXT_CHARS:
        text = text[:EMBED_TEXT_CHARS]
    parts = [
        f"公司：{chunk.get('company', '')}",
        f"证券代码：{chunk.get('symbol', '')}",
        f"来源类型：{chunk.get('source_type', '')}",
        f"发布日期：{chunk.get('publish_date', '')}",
        f"标题：{chunk.get('title', '')}",
        "",
        text,
    ]
    return "\n".join(parts)


def payload_from_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    keys = [
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
        "page_start",
        "page_end",
        "chunk_index",
        "n_chars",
        "text",
    ]
    payload = {key: chunk.get(key, "") for key in keys}
    payload["snippet"] = " ".join(str(chunk.get("text", "")).split())[:240]
    return payload


def ingest(path: Path, *, limit: int | None = None, batch_size: int = INGEST_BATCH) -> int:
    chunks = load_jsonl(path)
    if limit is not None:
        chunks = chunks[:limit]
    if not chunks:
        print("no chunks to ingest")
        return 0

    embedder = get_embedder()
    configure_embedder(embedder)
    vectorstore = get_vectorstore()
    try:
        vectorstore.ensure_collection(COLLECTION)

        total = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embedder.encode([build_passage(chunk) for chunk in batch], is_query=False)
            if vectors is None:
                continue

            items = [
                {
                    "id": chunk["chunk_id"],
                    "vector": vector,
                    "payload": payload_from_chunk(chunk),
                }
                for chunk, vector in zip(batch, vectors, strict=False)
            ]
            total += vectorstore.upsert_batch_to(COLLECTION, items)
            print(f"indexed={total}/{len(chunks)}", flush=True)

        print(f"collection={COLLECTION} chunks_read={len(chunks)} chunks_indexed={total}")
        return total
    finally:
        close_vectorstore(vectorstore)


def parse_filters(values: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"filter must be key=value: {value}")
        key, val = value.split("=", 1)
        key = key.strip()
        if key not in {"company", "symbol", "source_type", "publish_date", "document_id", "event_candidate_id"}:
            raise ValueError(f"unsupported filter: {key}")
        filters[key] = val.strip()
    return filters


def search(query: str, *, filters: dict[str, str] | None = None, limit: int = 8) -> int:
    embedder = get_embedder()
    configure_embedder(embedder)
    vectorstore = get_vectorstore()
    try:
        vector = embedder.encode(query, is_query=True)
        if vector is None:
            print("embedding failed")
            return 2
        hits = vectorstore.search_in(COLLECTION, query_vector=vector, limit=limit, filters=filters or None)
        for index, hit in enumerate(hits, start=1):
            payload = hit.payload
            print(
                f"[{index}] score={hit.score:.4f} {payload.get('company')} {payload.get('symbol')} "
                f"{payload.get('publish_date')} p{payload.get('page_start')}-{payload.get('page_end')}"
            )
            print(f"    {payload.get('title')}")
            print(f"    chunk_id={hit.id}")
            print(f"    {payload.get('snippet')}")
        print(f"hits={len(hits)} collection={COLLECTION}")
        return 0
    finally:
        close_vectorstore(vectorstore)


def count() -> int:
    vectorstore = get_vectorstore()
    try:
        total = vectorstore.count_in(COLLECTION)
        print(f"collection={COLLECTION} count={total}")
        return 0
    finally:
        close_vectorstore(vectorstore)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    ingest_parser.add_argument("--limit", type=int, default=None)
    ingest_parser.add_argument("--batch-size", type=int, default=INGEST_BATCH)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=8)
    search_parser.add_argument("--filter", action="append", default=[], help="Payload filter, e.g. symbol=300590")

    subparsers.add_parser("count")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "ingest":
        ingest(args.chunks, limit=args.limit, batch_size=args.batch_size)
        return 0
    if args.command == "search":
        return search(args.query, filters=parse_filters(args.filter), limit=args.limit)
    if args.command == "count":
        return count()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

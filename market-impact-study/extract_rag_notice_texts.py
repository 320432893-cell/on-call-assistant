"""Extract notice PDF text into JSONL chunks for market evidence RAG."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pymupdf

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PROJECT_DIR / "data/processed/rag_ingest_manifest.csv"
DEFAULT_OUTPUT = PROJECT_DIR / "data/processed/rag_notice_chunks.jsonl"
EASTMONEY_CONTENT_API = "https://np-cnotice-stock.eastmoney.com/api/content/ann"

MIN_CHUNK_CHARS = 80
MAX_CHUNK_CHARS = 1800
OVERLAP_CHARS = 160


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    text = normalize_text(text)
    if len(text) <= max_chars:
        return [text] if len(text) >= MIN_CHUNK_CHARS else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            split_at = max(text.rfind("\n\n", start, end), text.rfind("。", start, end), text.rfind("\n", start, end))
            if split_at > start + max_chars // 2:
                end = split_at + 1
        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_CHARS:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf_pages(path: Path) -> list[dict[str, object]]:
    doc = pymupdf.open(str(path))
    try:
        pages: list[dict[str, object]] = []
        for index in range(doc.page_count):
            text = normalize_text(doc.load_page(index).get_text("text"))
            if text:
                pages.append({"page": index + 1, "text": text})
        return pages
    finally:
        doc.close()


def announcement_code(document_id: str, source_url: str) -> str:
    match = re.search(r"(AN\d+)", document_id) or re.search(r"(AN\d+)", source_url or "")
    return match.group(1) if match else ""


def fetch_eastmoney_content(code: str, timeout: int = 15) -> dict[str, object] | None:
    if not code:
        return None
    params = urlencode({"client_source": "web", "page_index": 1, "art_code": code})
    request = Request(
        f"{EASTMONEY_CONTENT_API}?{params}",
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://data.eastmoney.com/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else None


def base_metadata(row: dict[str, str]) -> dict[str, str]:
    return {
        "document_id": row.get("document_id", ""),
        "company": row.get("company", ""),
        "symbol": row.get("symbol", ""),
        "source_type": row.get("source_type", ""),
        "title": row.get("title", ""),
        "publish_date": row.get("publish_date", ""),
        "source_url": row.get("source_url", ""),
        "pdf_url": row.get("pdf_url", ""),
        "local_path": row.get("local_path", ""),
        "event_candidate_id": row.get("event_candidate_id", ""),
    }


def chunks_from_pdf(row: dict[str, str]) -> list[dict[str, object]]:
    path = Path(row.get("local_path", ""))
    if not path.exists():
        return []

    output: list[dict[str, object]] = []
    meta = base_metadata(row)
    for page in extract_pdf_pages(path):
        page_no = int(page["page"])
        for part_index, text in enumerate(split_text(str(page["text"])), start=1):
            chunk_id = f"{meta['document_id']}#p{page_no}"
            if part_index > 1:
                chunk_id = f"{chunk_id}.{part_index}"
            output.append(
                {
                    **meta,
                    "chunk_id": chunk_id,
                    "text": text,
                    "text_source": "pdf",
                    "page_start": page_no,
                    "page_end": page_no,
                    "chunk_index": len(output) + 1,
                    "n_chars": len(text),
                }
            )
    return output


def chunks_from_eastmoney(row: dict[str, str]) -> list[dict[str, object]]:
    code = announcement_code(row.get("document_id", ""), row.get("source_url", ""))
    data = fetch_eastmoney_content(code)
    if not data:
        return []
    text = normalize_text(str(data.get("notice_content") or ""))
    if not text:
        return []

    meta = base_metadata(row)
    title = str(data.get("notice_title") or "").strip()
    if title:
        meta["title"] = title
    attach_url = str(data.get("attach_url_web") or data.get("attach_url") or "").strip()
    if attach_url:
        meta["pdf_url"] = attach_url

    output: list[dict[str, object]] = []
    for index, chunk_text in enumerate(split_text(text), start=1):
        output.append(
            {
                **meta,
                "chunk_id": f"{meta['document_id']}#api{index}",
                "text": chunk_text,
                "text_source": "eastmoney_content_api",
                "page_start": "",
                "page_end": "",
                "chunk_index": index,
                "n_chars": len(chunk_text),
            }
        )
    return output


def extract_chunks(
    rows: list[dict[str, str]], *, limit: int | None = None, sleep_sec: float = 0.0
) -> tuple[list[dict[str, object]], dict[str, int]]:
    selected = rows[:limit] if limit is not None else rows
    stats = {
        "input_rows": len(selected),
        "documents_with_chunks": 0,
        "documents_pdf": 0,
        "documents_api_fallback": 0,
        "documents_failed": 0,
        "chunks": 0,
    }
    all_chunks: list[dict[str, object]] = []

    for row in selected:
        chunks = chunks_from_pdf(row)
        if chunks:
            stats["documents_pdf"] += 1
        else:
            chunks = chunks_from_eastmoney(row)
            if chunks:
                stats["documents_api_fallback"] += 1
                if sleep_sec > 0:
                    time.sleep(sleep_sec)

        if chunks:
            stats["documents_with_chunks"] += 1
            all_chunks.extend(chunks)
        else:
            stats["documents_failed"] += 1

    stats["chunks"] = len(all_chunks)
    return all_chunks, stats


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N manifest rows.")
    parser.add_argument("--sleep-sec", type=float, default=0.1, help="Delay after API fallback requests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_manifest(args.manifest)
    chunks, stats = extract_chunks(rows, limit=args.limit, sleep_sec=args.sleep_sec)
    write_jsonl(args.output, chunks)
    print(f"manifest={args.manifest}")
    print(f"output={args.output}")
    print(" ".join(f"{key}={value}" for key, value in stats.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

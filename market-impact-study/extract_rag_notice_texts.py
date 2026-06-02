"""Extract market evidence text into JSONL chunks for RAG."""

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
DEFAULT_MANIFEST = PROJECT_DIR / "data/processed/rag_text_source_manifest.csv"
LEGACY_MANIFEST = PROJECT_DIR / "data/processed/rag_ingest_manifest.csv"
DEFAULT_OUTPUT = PROJECT_DIR / "data/processed/rag_notice_chunks.jsonl"
EASTMONEY_CONTENT_API = "https://np-cnotice-stock.eastmoney.com/api/content/ann"

MIN_CHUNK_CHARS = 80
MAX_CHUNK_CHARS = 1800
OVERLAP_CHARS = 160
EXPERIMENT_MAX_CHUNK_CHARS = 1400
EXPERIMENT_OVERLAP_CHARS = 240
PREFIX_MAX_CHARS = 220

PAGE_NO_RE = re.compile(r"^\s*(?:第\s*)?\d{1,4}\s*(?:页|/|／)?\s*$")
LEGAL_BOILERPLATE_PATTERNS = [
    re.compile(r"本公司及董事会全体成员保证信息披露内容的真实、准确和完整[^。]*?重大遗漏。"),
    re.compile(r"本公司及董事会全体成员保证公告内容[^。]*?重大遗漏。"),
    re.compile(r"本公司及董事会全体成员保证本公告内容[^。]*?重大遗漏。"),
    re.compile(r"没有虚假记载、?\s*误导性陈述或者重大遗漏。"),
]
STRUCTURED_TITLE_RE = re.compile(r"^标题：.*?(?:\n|$)")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def default_manifest_path() -> Path:
    return DEFAULT_MANIFEST if DEFAULT_MANIFEST.exists() else LEGACY_MANIFEST


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def enhanced_clean_text(text: str) -> str:
    lines: list[str] = []
    previous = ""
    for line in normalize_text(text).splitlines():
        current = line.strip()
        if not current or PAGE_NO_RE.match(current):
            continue
        if current == previous and len(current) <= 40:
            continue
        lines.append(current)
        previous = current
    cleaned = "\n".join(lines)
    for pattern in LEGAL_BOILERPLATE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return normalize_text(cleaned)


def build_text_prefix(row: dict[str, str]) -> str:
    parts = [
        f"公司：{row.get('company', '')}",
        f"代码：{row.get('symbol', '')}",
        f"来源：{row.get('text_source') or row.get('source_type', '')}",
        f"证据强度：{row.get('evidence_strength', '')}",
        f"日期：{row.get('publish_date', '')}",
        f"标题：{row.get('title', '')}",
    ]
    prefix = "\n".join(part for part in parts if not part.endswith("："))
    return prefix[:PREFIX_MAX_CHARS]


def apply_text_options(text: str, row: dict[str, str], *, preprocess: str, add_prefix: bool) -> str:
    output = enhanced_clean_text(text) if preprocess == "enhanced" else normalize_text(text)
    if add_prefix and row.get("source_text") == text:
        output = STRUCTURED_TITLE_RE.sub("", output, count=1).strip()
    if add_prefix:
        prefix = build_text_prefix(row)
        if prefix:
            output = f"{prefix}\n\n正文：{output}"
    return output


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
        "evidence_strength": row.get("evidence_strength", ""),
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
                    "text_source": row.get("text_source") or "pdf",
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
                "text_source": row.get("text_source") or "notice_api",
                "page_start": "",
                "page_end": "",
                "chunk_index": index,
                "n_chars": len(chunk_text),
            }
        )
    return output


def chunks_from_structured_text(row: dict[str, str]) -> list[dict[str, object]]:
    text = normalize_text(row.get("source_text", ""))
    if not text:
        return []

    meta = base_metadata(row)
    text_source = row.get("text_source") or row.get("source_type") or "structured"
    output: list[dict[str, object]] = []
    for index, chunk_text in enumerate(split_text(text), start=1):
        output.append(
            {
                **meta,
                "chunk_id": f"{meta['document_id']}#text{index}",
                "text": chunk_text,
                "text_source": text_source,
                "page_start": "",
                "page_end": "",
                "chunk_index": index,
                "n_chars": len(chunk_text),
            }
        )
    return output


def chunks_from_pdf_experiment(
    row: dict[str, str],
    *,
    preprocess: str,
    add_prefix: bool,
    max_chars: int,
    overlap: int,
) -> list[dict[str, object]]:
    path = Path(row.get("local_path", ""))
    if not path.exists():
        return []

    output: list[dict[str, object]] = []
    meta = base_metadata(row)
    for page in extract_pdf_pages(path):
        page_no = int(page["page"])
        page_text = apply_text_options(str(page["text"]), {**row, **meta}, preprocess=preprocess, add_prefix=add_prefix)
        for part_index, text in enumerate(split_text(page_text, max_chars=max_chars, overlap=overlap), start=1):
            chunk_id = f"{meta['document_id']}#exp-p{page_no}"
            if part_index > 1:
                chunk_id = f"{chunk_id}.{part_index}"
            output.append(
                {
                    **meta,
                    "chunk_id": chunk_id,
                    "text": text,
                    "text_source": row.get("text_source") or "pdf",
                    "page_start": page_no,
                    "page_end": page_no,
                    "chunk_index": len(output) + 1,
                    "n_chars": len(text),
                    "preprocess": preprocess,
                    "has_prefix": "1" if add_prefix else "0",
                }
            )
    return output


def chunks_from_structured_text_experiment(
    row: dict[str, str],
    *,
    preprocess: str,
    add_prefix: bool,
    max_chars: int,
    overlap: int,
) -> list[dict[str, object]]:
    text = apply_text_options(row.get("source_text", ""), row, preprocess=preprocess, add_prefix=add_prefix)
    if not text:
        return []

    meta = base_metadata(row)
    text_source = row.get("text_source") or row.get("source_type") or "structured"
    output: list[dict[str, object]] = []
    for index, chunk_text in enumerate(split_text(text, max_chars=max_chars, overlap=overlap), start=1):
        output.append(
            {
                **meta,
                "chunk_id": f"{meta['document_id']}#exp-text{index}",
                "text": chunk_text,
                "text_source": text_source,
                "page_start": "",
                "page_end": "",
                "chunk_index": index,
                "n_chars": len(chunk_text),
                "preprocess": preprocess,
                "has_prefix": "1" if add_prefix else "0",
            }
        )
    return output


def extract_chunks(
    rows: list[dict[str, str]],
    *,
    limit: int | None = None,
    sleep_sec: float = 0.0,
    include_text_sources: set[str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    if include_text_sources is not None:
        rows = [row for row in rows if (row.get("text_source") or "pdf") in include_text_sources]
    selected = rows[:limit] if limit is not None else rows
    stats = {
        "input_rows": len(selected),
        "documents_with_chunks": 0,
        "documents_pdf": 0,
        "documents_notice_api": 0,
        "documents_structured_text": 0,
        "documents_failed": 0,
        "chunks": 0,
    }
    all_chunks: list[dict[str, object]] = []

    for row in selected:
        text_source = row.get("text_source", "")
        chunks: list[dict[str, object]] = []
        if text_source in {"", "pdf"}:
            chunks = chunks_from_pdf(row)
            if chunks:
                stats["documents_pdf"] += 1
        if not chunks and text_source in {"", "notice_api"}:
            chunks = chunks_from_eastmoney(row)
            if chunks:
                stats["documents_notice_api"] += 1
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
        if not chunks:
            chunks = chunks_from_structured_text(row)
            if chunks:
                stats["documents_structured_text"] += 1

        if chunks:
            stats["documents_with_chunks"] += 1
            all_chunks.extend(chunks)
        else:
            stats["documents_failed"] += 1

    stats["chunks"] = len(all_chunks)
    return all_chunks, stats


def extract_experiment_chunks(
    rows: list[dict[str, str]],
    *,
    limit: int | None = None,
    include_text_sources: set[str] | None = None,
    preprocess: str = "enhanced",
    add_prefix: bool = True,
    max_chars: int = EXPERIMENT_MAX_CHUNK_CHARS,
    overlap: int = EXPERIMENT_OVERLAP_CHARS,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    if include_text_sources is not None:
        rows = [row for row in rows if (row.get("text_source") or "pdf") in include_text_sources]
    selected = rows[:limit] if limit is not None else rows
    stats = {
        "input_rows": len(selected),
        "documents_with_chunks": 0,
        "documents_pdf": 0,
        "documents_structured_text": 0,
        "documents_failed": 0,
        "chunks": 0,
    }
    all_chunks: list[dict[str, object]] = []
    for row in selected:
        text_source = row.get("text_source", "")
        chunks: list[dict[str, object]] = []
        if text_source in {"", "pdf"}:
            chunks = chunks_from_pdf_experiment(
                row,
                preprocess=preprocess,
                add_prefix=add_prefix,
                max_chars=max_chars,
                overlap=overlap,
            )
            if chunks:
                stats["documents_pdf"] += 1
        if not chunks:
            chunks = chunks_from_structured_text_experiment(
                row,
                preprocess=preprocess,
                add_prefix=add_prefix,
                max_chars=max_chars,
                overlap=overlap,
            )
            if chunks:
                stats["documents_structured_text"] += 1

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
    parser.add_argument("--manifest", type=Path, default=default_manifest_path())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N manifest rows.")
    parser.add_argument("--sleep-sec", type=float, default=0.1, help="Delay after API fallback requests.")
    parser.add_argument(
        "--include-text-source",
        action="append",
        default=None,
        help="Only process a text_source value. Repeat for multiple sources.",
    )
    parser.add_argument("--experiment", action="store_true", help="Use enhanced cleaning, prefix, and sliding window.")
    parser.add_argument("--preprocess", choices=["basic", "enhanced"], default="enhanced")
    parser.add_argument("--add-prefix", action="store_true")
    parser.add_argument("--max-chars", type=int, default=EXPERIMENT_MAX_CHUNK_CHARS)
    parser.add_argument("--overlap", type=int, default=EXPERIMENT_OVERLAP_CHARS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_manifest(args.manifest)
    include_text_sources = set(args.include_text_source) if args.include_text_source else None
    if args.experiment:
        chunks, stats = extract_experiment_chunks(
            rows,
            limit=args.limit,
            include_text_sources=include_text_sources,
            preprocess=args.preprocess,
            add_prefix=args.add_prefix,
            max_chars=args.max_chars,
            overlap=args.overlap,
        )
    else:
        chunks, stats = extract_chunks(
            rows,
            limit=args.limit,
            sleep_sec=args.sleep_sec,
            include_text_sources=include_text_sources,
        )
    write_jsonl(args.output, chunks)
    print(f"manifest={args.manifest}")
    print(f"output={args.output}")
    print(" ".join(f"{key}={value}" for key, value in stats.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

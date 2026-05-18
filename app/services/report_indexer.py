# 年报章节级 chunks → Qdrant 灌库
#
# 输入：data/processed/annual_reports/{company}_{year}/chunks.jsonl
# 输出：写入 Qdrant collection `annual_reports`
#
# passage 构造策略（沿用 v2 经验：前置元信息 + 双侧前缀）：
#   "公司：移远通信\n年度：2025\n章节：第三节/管理层讨论与分析/(四) 可能面对的风险\n\n{text}\n\n表格：\n{table_md}\n..."
#
# chunk_id 用 md5 → 稳定 64-bit point_id（vectorstore._stable_point_id）。

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import List, Optional

from app.services.report_pdf import ReportChunk, parse_annual_report, chunks_to_jsonl
from app.services import get_embedder, get_vectorstore

REPORT_COLLECTION = "annual_reports"

# 单次灌库批量大小（bge-m3 单进程 CPU 推理，过大会爆内存）
INGEST_BATCH = 16

# snippet 渲染时剔除的模板占位串（仅影响展示用 snippet，chunk.text 主体不动）
_SNIPPET_PLACEHOLDER_RE = re.compile(
    r"√\s*适用\s*□?\s*不适用|"
    r"□\s*适用\s*√?\s*不适用|"
    r"√\s*适用|□\s*适用|"
    r"√\s*不适用|□\s*不适用|"
    r"√\s*是\s*□?\s*否|□\s*是\s*√?\s*否"
)


def _build_passage(chunk: ReportChunk) -> str:
    """章节 chunk → 灌库 passage：前置元信息 + 正文 + 表格"""
    parts = [
        f"公司：{chunk.company}",
        f"年度：{chunk.year}",
        f"章节：{chunk.section_path}",
        "",
        chunk.text,
    ]
    if chunk.tables:
        parts.append("")
        for i, tab in enumerate(chunk.tables, 1):
            parts.append(f"表 {i}：")
            parts.append(tab)
    return "\n".join(parts)


def _snippet(text: str, n: int = 200) -> str:
    """生成展示用 snippet：先剥模板占位串，再压空白，再截前 n 字。

    向量库 chunk.text 主体不变；只清洗 snippet。
    """
    s = _SNIPPET_PLACEHOLDER_RE.sub("", text)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]


def load_chunks_jsonl(jsonl_path: str | Path) -> List[ReportChunk]:
    """从 jsonl 反序列化为 ReportChunk 列表"""
    out: List[ReportChunk] = []
    with Path(jsonl_path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(ReportChunk(**d))
    return out


def ingest_chunks(
    chunks: List[ReportChunk],
    batch_size: int = INGEST_BATCH,
    on_progress: Optional[callable] = None,
) -> int:
    """把 chunks 向量化后写入 Qdrant annual_reports collection

    Returns:
        实际成功写入的 chunk 数
    """
    if not chunks:
        return 0

    embedder = get_embedder()
    vs = get_vectorstore()
    vs.ensure_collection(REPORT_COLLECTION)

    total_written = 0
    pending: list[dict] = []

    for i, chunk in enumerate(chunks):
        passage = _build_passage(chunk)
        vec = embedder.encode(passage, is_query=False)
        if vec is None:
            continue
        pending.append({
            "id": chunk.chunk_id,
            "vector": vec,
            "payload": {
                "company": chunk.company,
                "year": chunk.year,
                "section_path": chunk.section_path,
                "section_title": chunk.section_title,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "snippet": _snippet(chunk.text, 200),
                "text": chunk.text,
                "tables": chunk.tables,
                "n_chars": chunk.n_chars,
                "has_tables": bool(chunk.tables),
            },
        })

        if len(pending) >= batch_size:
            total_written += vs.upsert_batch_to(REPORT_COLLECTION, pending)
            pending.clear()
            if on_progress:
                on_progress(i + 1, len(chunks))

    if pending:
        total_written += vs.upsert_batch_to(REPORT_COLLECTION, pending)
        if on_progress:
            on_progress(len(chunks), len(chunks))

    return total_written


def ingest_from_pdf(
    pdf_path: str | Path,
    company: str,
    year: int,
    out_jsonl: Optional[str | Path] = None,
) -> dict:
    """端到端：PDF → chunks → (可选写 jsonl) → Qdrant

    Returns:
        {"company", "year", "n_chunks", "n_indexed", "elapsed_sec"}
    """
    t0 = time.time()
    chunks = parse_annual_report(pdf_path, company=company, year=year)
    if out_jsonl:
        chunks_to_jsonl(chunks, out_jsonl)
    n_indexed = ingest_chunks(chunks)
    return {
        "company": company,
        "year": year,
        "n_chunks": len(chunks),
        "n_indexed": n_indexed,
        "elapsed_sec": round(time.time() - t0, 2),
    }


def ingest_from_jsonl(jsonl_path: str | Path) -> dict:
    """从已有 jsonl 灌库（跳过 PDF 解析，用于 chunks 已落盘的场景）"""
    t0 = time.time()
    chunks = load_chunks_jsonl(jsonl_path)
    if not chunks:
        return {"n_chunks": 0, "n_indexed": 0, "elapsed_sec": 0.0}
    n_indexed = ingest_chunks(chunks)
    return {
        "company": chunks[0].company,
        "year": chunks[0].year,
        "n_chunks": len(chunks),
        "n_indexed": n_indexed,
        "elapsed_sec": round(time.time() - t0, 2),
    }

# Phase4: 年报 RAG API
#
# 路由：
#   POST /v4/ingest      手动触发年报解析+灌库（3-5 分钟，body 指定 PDF 路径或公司）
#   GET  /v4/search      在 annual_reports collection 内做语义检索（支持 company/year filter）
#   GET  /v4/companies   列出已灌库的 (company, year) 组合
#   GET  /v4/health      v4 健康检查（含 collection 文档数）
#
# 灌库默认从 data/processed/annual_reports/{company}_{year}/chunks.jsonl 读取已解析产物；
# 若指定 pdf_path 且 chunks.jsonl 不存在则现场解析。

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import get_embedder, get_vectorstore
from app.services.report_indexer import (
    REPORT_COLLECTION,
    ingest_from_jsonl,
    ingest_from_pdf,
)

router = APIRouter(prefix="/v4", tags=["Phase4-年报RAG"])

# 默认产物根目录
PROCESSED_ROOT = Path("data/processed/annual_reports")
RAW_ROOT = Path("data/raw/annual_reports")


class IngestRequest(BaseModel):
    company: str = Field(..., description="公司名，例：移远通信")
    year: int = Field(..., description="年报年度，例：2025")
    pdf_path: str | None = Field(
        None,
        description="PDF 绝对/相对路径；不传则用默认 data/raw/annual_reports/{company}_{year}.pdf；"
        "若对应 chunks.jsonl 已存在则直接复用，不重新解析",
    )
    force_reparse: bool = Field(default=False, description="强制重新解析 PDF（即使 jsonl 已存在）")


class IngestResponse(BaseModel):
    company: str
    year: int
    n_chunks: int
    n_indexed: int
    elapsed_sec: float
    source: str  # "jsonl" | "pdf"


class ReportSearchHit(BaseModel):
    chunk_id: str
    company: str
    year: int
    section_path: str
    section_title: str
    page_start: int
    page_end: int
    snippet: str
    score: float
    has_tables: bool


class ReportSearchResponse(BaseModel):
    query: str
    n_hits: int
    results: list[ReportSearchHit]


class CompanyInfo(BaseModel):
    company: str
    year: int


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest):
    """手动触发年报灌库

    优先用已有 chunks.jsonl；缺失或 force_reparse=True 时从 PDF 解析。
    """
    jsonl_path = PROCESSED_ROOT / f"{req.company}_{req.year}" / "chunks.jsonl"

    if jsonl_path.exists() and not req.force_reparse:
        stat = ingest_from_jsonl(jsonl_path)
        return IngestResponse(
            company=stat.get("company", req.company),
            year=stat.get("year", req.year),
            n_chunks=stat["n_chunks"],
            n_indexed=stat["n_indexed"],
            elapsed_sec=stat["elapsed_sec"],
            source="jsonl",
        )

    pdf_path = Path(req.pdf_path) if req.pdf_path else RAW_ROOT / f"{req.company}_{req.year}.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF 不存在: {pdf_path}（且 jsonl 缓存也不在 {jsonl_path}）",
        )

    stat = ingest_from_pdf(
        pdf_path=pdf_path,
        company=req.company,
        year=req.year,
        out_jsonl=jsonl_path,
    )
    return IngestResponse(
        company=req.company,
        year=req.year,
        n_chunks=stat["n_chunks"],
        n_indexed=stat["n_indexed"],
        elapsed_sec=stat["elapsed_sec"],
        source="pdf",
    )


@router.get("/search", response_model=ReportSearchResponse)
def search(
    q: str,
    company: str | None = None,
    year: int | None = None,
    limit: int = 10,
):
    """年报语义检索（可选 company/year 过滤）"""
    if not q:
        raise HTTPException(status_code=400, detail="查询词不能为空")

    embedder = get_embedder()
    vs = get_vectorstore()

    vec = embedder.encode(q, is_query=True)
    if vec is None:
        raise HTTPException(status_code=500, detail="Embedding 生成失败")

    filters = {}
    if company:
        filters["company"] = company
    if year is not None:
        filters["year"] = year

    raw = vs.search_in(
        collection=REPORT_COLLECTION,
        query_vector=vec,
        limit=limit,
        filters=filters or None,
    )

    hits = [
        ReportSearchHit(
            chunk_id=r.id,
            company=r.payload.get("company", ""),
            year=int(r.payload.get("year", 0) or 0),
            section_path=r.payload.get("section_path", ""),
            section_title=r.payload.get("section_title", ""),
            page_start=int(r.payload.get("page_start", 0) or 0),
            page_end=int(r.payload.get("page_end", 0) or 0),
            snippet=r.payload.get("snippet", ""),
            score=round(float(r.score), 4),
            has_tables=bool(r.payload.get("has_tables", False)),
        )
        for r in raw
    ]
    return ReportSearchResponse(query=q, n_hits=len(hits), results=hits)


@router.get("/companies", response_model=list[CompanyInfo])
def companies():
    """列出已灌库的 (company, year) 组合"""
    vs = get_vectorstore()
    rows = vs.scroll_distinct(REPORT_COLLECTION, fields=["company", "year"], limit=10000)
    out = []
    for r in rows:
        c = r.get("company")
        y = r.get("year")
        if c is None or y is None:
            continue
        out.append(CompanyInfo(company=str(c), year=int(y)))
    out.sort(key=lambda x: (x.company, x.year))
    return out


@router.get("/health")
def health():
    vs = get_vectorstore()
    return {
        "status": "ok" if vs.health_check() else "degraded",
        "collection": REPORT_COLLECTION,
        "n_indexed": vs.count_in(REPORT_COLLECTION),
    }

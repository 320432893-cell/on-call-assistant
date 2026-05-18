# Phase1: 关键词搜索 API

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List

from app.config import get_settings
from app.services import get_preprocessor, get_indexer
from app.models import DocumentInput, DocumentResponse, SearchResult, SearchResponse

settings = get_settings()

router = APIRouter(prefix="/v1", tags=["Phase1-关键词搜索"])


# =============== API Endpoints ===============


class DocumentInputV1(BaseModel):
    """文档入库请求（与通用模型一致）"""
    id: str = Field(..., description="文档ID，如 sop-001")
    html: str = Field(..., description="HTML原文")


class DocumentResponseV1(BaseModel):
    """文档入库响应"""
    id: str
    title: str


class SearchResponseV1(BaseModel):
    """搜索响应"""
    query: str
    results: List[SearchResult]


@router.post("/documents", response_model=DocumentResponseV1, status_code=201)
async def create_document(doc_input: DocumentInputV1):
    """
    文档入库

    - 解析HTML提取内容
    - 生成jieba分词
    - 写入Tantivy索引
    """
    # 获取服务
    preprocessor = get_preprocessor()
    indexer = get_indexer()

    try:
        # 预处理
        processed = preprocessor.parse_html(doc_input.html, doc_input.id)

        # 添加到索引（先不commit，后面批量或单条）
        success = indexer.add_document(
            doc_id=processed.id,
            title=processed.title,
            content=processed.content,
            content_raw=processed.content_raw,
            department=processed.department,
            tags=processed.tags,
        )

        if not success:
            raise HTTPException(status_code=500, detail="索引添加失败")

        # commit
        indexer.commit()

        return DocumentResponseV1(
            id=processed.id,
            title=processed.title,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.get("/search", response_model=SearchResponseV1)
async def search_documents(q: str, limit: int = 10):
    """
    关键词搜索

    - 支持中文关键词
    - 返回BM25相关性评分
    - 自动高亮匹配片段
    - 纯标点查询（如 &、<）走 substring 兜底（Tantivy 不索引这类 token）
    """
    if not q:
        raise HTTPException(status_code=400, detail="查询词不能为空")

    indexer = get_indexer()

    try:
        # 1) 主路径：Tantivy 索引检索
        results = indexer.search(q, limit=limit)

        # 2) 兜底：查询是"纯标点/特殊字符"且主路径返回空 → 扫原文做 substring 匹配
        #    这覆盖题面 q=& 用例（Tantivy whitespace tokenizer 不切 "网络&CDN" 这种粘连字符串）
        if not results and not any(c.isalnum() for c in q):
            results = _substring_fallback(q, limit=limit)

        return SearchResponseV1(
            query=q,
            results=[
                SearchResult(
                    id=r.id,
                    title=r.title,
                    snippet=r.snippet,
                    score=round(r.score, 4),
                )
                for r in results
            ],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


def _substring_fallback(q: str, limit: int = 10) -> list:
    """扫 data/raw/*.html，返回原文（去标签后）含 q 的文档"""
    from pathlib import Path
    from bs4 import BeautifulSoup
    from app.services.indexer import SearchResult as IndexerResult

    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        return []

    hits = []
    for html_file in sorted(raw_dir.glob("sop-*.html")):
        try:
            html = html_file.read_text(encoding="utf-8")
            soup = BeautifulSoup(html, "lxml")
            for t in soup(["script", "style"]):
                t.decompose()
            text = soup.get_text(separator=" ", strip=True)
            if q in text:
                title_tag = soup.find("title") or soup.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else html_file.stem
                idx = text.index(q)
                snippet = text[max(0, idx-60):idx+60]
                hits.append(IndexerResult(
                    doc_id=html_file.stem,
                    title=title,
                    snippet=snippet,
                    score=1.0,  # 纯匹配，无分差
                ))
                if len(hits) >= limit:
                    break
        except Exception:  # noqa: BLE001, S112 — 单 collection 失败不阻断其他 collection 检索
            continue
    return hits


@router.get("/", response_class=HTMLResponse)
async def search_page(request: Request):
    """搜索页面"""
    template = request.app.templates
    return template.TemplateResponse(request, "v1_search.html")

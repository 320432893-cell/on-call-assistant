# Phase2: 语义搜索 API（章节级 chunk + lexical rerank）

import jieba
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List

from app.services import get_preprocessor, get_embedder, get_vectorstore, get_indexer
from app.models import SearchResult

router = APIRouter(prefix="/v2", tags=["Phase2-语义搜索"])


# rerank 权重：向量 0.7 + lexical 0.3
RERANK_ALPHA = 0.7


class SearchResponseV2(BaseModel):
    query: str
    results: List[SearchResult]


def _build_chunk_text(processed, section: dict) -> str:
    """构造章节级灌库文本：标题+部门+章节标题+章节正文"""
    return (
        f"标题：{processed.title}\n"
        f"部门：{processed.department}\n"
        f"章节：{section.get('heading','')}\n\n"
        f"{section.get('content','')}"
    )


def _ensure_indexed():
    """首次访问时把 data/raw/*.html 按章节拆 chunk 灌入向量库

    章节数 ≈ 每篇 12-13 个，10 篇约 120 个 chunk。
    chunk_id 形如 'sop-001#3'（# 后是 section 在文档中的顺序）。
    """
    vectorstore = get_vectorstore()
    # 至少灌过 100 个 chunk 才认为完成（10 篇 × ~12 章节）
    if vectorstore.count() >= 100:
        return

    from pathlib import Path
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        return

    preprocessor = get_preprocessor()
    embedder = get_embedder()

    for html_file in sorted(raw_dir.glob("sop-*.html")):
        doc_id = html_file.stem
        html = html_file.read_text(encoding="utf-8")
        processed = preprocessor.parse_html(html, doc_id)

        # 按章节拆 chunk
        for idx, section in enumerate(processed.sections):
            if not section.get("content", "").strip():
                continue
            chunk_id = f"{doc_id}#{idx}"
            passage = _build_chunk_text(processed, section)
            vec = embedder.encode(passage, is_query=False)
            if vec is None:
                continue
            # snippet 取章节正文前 200 字
            snippet = section.get("content", "")[:200].strip()
            vectorstore.upsert(
                doc_id=chunk_id,
                vector=vec,
                payload={
                    "doc_id_root": doc_id,
                    "title": processed.title,
                    "department": processed.department,
                    "section_heading": section.get("heading", ""),
                    "section_idx": idx,
                    "snippet": snippet,
                },
            )


@router.get("/search", response_model=SearchResponseV2)
async def semantic_search(q: str, limit: int = 10):
    """语义搜索：章节级 chunk 检索 + lexical rerank，按文档去重返回 Top1 章节"""
    if not q:
        raise HTTPException(status_code=400, detail="查询词不能为空")

    _ensure_indexed()

    embedder = get_embedder()
    vectorstore = get_vectorstore()

    query_vec = embedder.encode(q, is_query=True)
    if query_vec is None:
        raise HTTPException(status_code=500, detail="Embedding 生成失败")

    # 取 limit*3 候选给 rerank + 去重留余量
    raw_results = vectorstore.search(query_vec, limit=limit * 3)

    # lexical rerank：jieba 切 query → 看 chunk 的 title+部门+章节标题命中几个关键词
    query_words = _query_keywords(q)
    rescored = []
    for r in raw_results:
        candidate_text = (
            r.payload.get("title", "")
            + " " + r.payload.get("department", "")
            + " " + r.payload.get("section_heading", "")
        )
        kw_score = _keyword_boost(query_words, candidate_text)
        final_score = RERANK_ALPHA * float(r.score) + (1 - RERANK_ALPHA) * kw_score
        rescored.append((final_score, r))

    # 按 rerank 后分数倒序
    rescored.sort(key=lambda x: -x[0])

    # 按 doc_id_root 去重：同一文档保留 score 最高的章节
    seen = set()
    deduped = []
    for final_score, r in rescored:
        doc_root = r.payload.get("doc_id_root", r.id.split("#")[0])
        if doc_root in seen:
            continue
        seen.add(doc_root)
        deduped.append((doc_root, final_score, r))
        if len(deduped) >= limit:
            break

    return SearchResponseV2(
        query=q,
        results=[
            SearchResult(
                id=doc_root,
                title=f"{r.payload.get('title', '')} - {r.payload.get('section_heading', '')}",
                snippet=r.payload.get("snippet", ""),
                score=round(float(final_score), 4),
            )
            for doc_root, final_score, r in deduped
        ],
    )


def _query_keywords(q: str) -> list[str]:
    """jieba 切 query 提取关键词（长度 >= 2 的词）"""
    words = list(jieba.cut_for_search(q))
    return [w for w in words if len(w) >= 2]


def _keyword_boost(query_words: list[str], candidate_text: str) -> float:
    """命中率：query 切出的关键词在 candidate_text 中命中比例（0-1）"""
    if not query_words:
        return 0.0
    matches = sum(1 for w in query_words if w in candidate_text)
    return matches / len(query_words)


@router.get("/", response_class=HTMLResponse)
async def search_page(request: Request):
    """语义搜索页面"""
    template = request.app.templates
    return template.TemplateResponse(request, "v2_search.html")

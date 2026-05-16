# 年报 PDF 解析：书签驱动的章节级 chunk + 表格抽取
# 输入：单份年报 PDF 路径 + (company, year)
# 输出：List[ReportChunk]（可写 jsonl 或直接灌库）
#
# 核心算法：
#   1. 拼出全文 full_text（已剔页眉/页码），同时记录每页起始 offset
#   2. 在 full_text 上按 TOC 顺序定位每个【叶子】标题的 offset
#   3. 第 i 个叶子 chunk = full_text[第 i 个标题结束位置 : 第 i+1 个标题起始位置]
#   4. 按起止 offset 反查页码 → page_start/page_end
#   5. 表格按页范围抽取并附到所属 chunk

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional, Tuple

import pymupdf

# 页眉模式：每页重复出现，需剔除
_HEADER_PATTERNS = [
    re.compile(r"^.*年年度报告\s*$"),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),  # 页码 "31 / 232"
]

# chunk 大小阈值
MIN_CHUNK_CHARS = 30          # 太短的章节直接丢弃（仅含"□适用√不适用"等占位）
MAX_CHUNK_CHARS = 4000        # 超长章节按 ~3000 字软切，避免向量被稀释

# 占位串（用于判断章节是否只剩模板占位、无实质内容）
_PLACEHOLDER_RE = re.compile(
    r"□\s*适用\s*√\s*不适用|"
    r"√\s*适用\s*□\s*不适用|"
    r"□\s*适用|"
    r"√\s*不适用|"
    r"不适用|"
    r"□\s*是\s*√\s*否|"
    r"√\s*是\s*□\s*否"
)


@dataclass
class ReportChunk:
    """一份年报的一个 chunk（章节级）"""
    chunk_id: str                       # 例: 移远通信_2025#第三节/管理层讨论与分析/六/(四)
    company: str
    year: int
    section_path: str                   # 例: 第三节/管理层讨论与分析/六/(四)
    section_title: str                  # 叶子标题，例: (四) 可能面对的风险
    page_start: int                     # 1-based
    page_end: int                       # 1-based, inclusive
    text: str                           # 正文（已剔页眉/页码）
    tables: List[str] = field(default_factory=list)   # 表格 markdown
    n_chars: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# --------- 文本清洗 ---------


def _strip_header_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    for pat in _HEADER_PATTERNS:
        if pat.match(s):
            return True
    return False


def _clean_page_text(raw: str) -> str:
    """剔除页眉/页码（保留段落结构，行内换行不动）"""
    lines = raw.splitlines()
    kept = [ln for ln in lines if not _strip_header_line(ln)]
    return "\n".join(kept).strip()


def _normalize_whitespace(s: str) -> str:
    """合并多余空白：行内连续空格压缩，三个及以上换行合并为段间空行"""
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _is_placeholder_only(text: str) -> bool:
    """剔除占位后剩余字符 < 20 视为占位章节"""
    cleaned = _PLACEHOLDER_RE.sub("", text)
    cleaned = re.sub(r"\s+", "", cleaned)
    return len(cleaned) < 20


def _table_to_markdown(rows: List[List[Optional[str]]]) -> str:
    """二维表格转 markdown"""
    if not rows:
        return ""

    def fmt(c: Optional[str]) -> str:
        if c is None:
            return ""
        return c.replace("\n", " ").replace("|", "\\|").strip()

    n_cols = max(len(r) for r in rows)
    norm = [[fmt(c) for c in r] + [""] * (n_cols - len(r)) for r in rows]
    header = "| " + " | ".join(norm[0]) + " |"
    sep = "| " + " | ".join(["---"] * n_cols) + " |"
    body = ["| " + " | ".join(r) + " |" for r in norm[1:]]
    return "\n".join([header, sep] + body)


# --------- 全文 + 标题定位 ---------


def _build_full_text(doc: pymupdf.Document) -> Tuple[str, List[int]]:
    """全文拼接，返回 (full_text, page_starts)
    page_starts[i] 是第 i 页（0-based）在 full_text 中的起始 offset
    page_starts[len(pages)] = len(full_text)（哨兵）
    """
    parts: List[str] = []
    starts: List[int] = []
    cursor = 0
    for pg in range(doc.page_count):
        starts.append(cursor)
        cleaned = _clean_page_text(doc.load_page(pg).get_text("text"))
        block = cleaned + "\n\n"  # 页间用空行分隔
        parts.append(block)
        cursor += len(block)
    starts.append(cursor)
    return "".join(parts), starts


def _build_norm_index(full_text: str) -> Tuple[str, List[int]]:
    """构造去空白文本 + norm_idx -> orig_idx 映射，用于跨空白匹配标题"""
    norm_chars: List[str] = []
    mapping: List[int] = []
    for i, ch in enumerate(full_text):
        if ch.isspace():
            continue
        norm_chars.append(ch)
        mapping.append(i)
    return "".join(norm_chars), mapping


def _offset_to_page(page_starts: List[int], offset: int) -> int:
    """offset 反查页码（0-based）"""
    lo, hi = 0, len(page_starts) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if page_starts[mid] <= offset:
            lo = mid
        else:
            hi = mid
    return lo


def _flatten_leaves(toc: List[List]) -> List[Tuple[str, str, int]]:
    """从 TOC 提取叶子节点

    Returns:
        [(section_path, leaf_title, toc_page_hint), ...]
        toc_page_hint 是 TOC 给的起始页（1-based），用于校验/兜底
    """
    n = len(toc)
    leaves: List[Tuple[str, str, int]] = []
    ancestors: List[Tuple[int, str]] = []

    for i, (level, title, page) in enumerate(toc):
        title = title.strip()
        ancestors = [a for a in ancestors if a[0] < level]

        is_leaf = not (i + 1 < n and toc[i + 1][0] > level)
        if is_leaf:
            section_path = "/".join([a[1] for a in ancestors] + [title])
            leaves.append((section_path, title, page))
        ancestors.append((level, title))

    return leaves


# --------- 内容切片 ---------


def _split_long_chunk(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """超长 chunk 按段落软切，单段超长再按句切"""
    if len(text) <= max_chars:
        return [text]

    parts: List[str] = []
    buf = ""
    for para in re.split(r"\n{2,}", text):
        if not para.strip():
            continue
        if len(buf) + len(para) + 2 <= max_chars:
            buf = (buf + "\n\n" + para) if buf else para
        else:
            if buf:
                parts.append(buf)
            if len(para) <= max_chars:
                buf = para
            else:
                sents = re.split(r"(?<=[。！？!?])", para)
                sbuf = ""
                for s in sents:
                    if len(sbuf) + len(s) <= max_chars:
                        sbuf += s
                    else:
                        if sbuf:
                            parts.append(sbuf)
                        sbuf = s
                buf = sbuf
    if buf:
        parts.append(buf)
    return parts


# --------- 主入口 ---------


def parse_annual_report(
    pdf_path: str | Path,
    company: str,
    year: int,
    extract_tables: bool = True,
) -> List[ReportChunk]:
    """解析年报 PDF 为章节级 chunks"""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))
    try:
        toc = doc.get_toc()
        if not toc:
            raise ValueError(f"PDF 无书签目录，暂不支持: {pdf_path}")

        total_pages = doc.page_count
        full_text, page_starts = _build_full_text(doc)
        norm_text, norm_to_orig = _build_norm_index(full_text)

        leaves = _flatten_leaves(toc)
        if not leaves:
            return []

        # 1) 顺序定位每个叶子标题在 full_text 中的位置
        # 用单调指针 search_from_norm，确保后面的标题不会匹配到前面去
        title_offsets: List[Optional[Tuple[int, int]]] = []  # 每个叶子: (orig_start, orig_end)
        search_from_norm = 0
        for sec_path, leaf_title, hint_page in leaves:
            # 优先匹配完整 section_path 的最后两层（"section_path 的叶子"），
            # 直接匹配 leaf_title 即可，因为 TOC 的 leaf_title 在正文中独立成行
            norm_leaf = re.sub(r"\s+", "", leaf_title)
            if not norm_leaf:
                title_offsets.append(None)
                continue
            pos = norm_text.find(norm_leaf, search_from_norm)
            if pos == -1:
                # 退化策略：从 hint_page 起始 offset 的归一化位置开始重搜
                hint_page_idx = max(0, hint_page - 1)
                if hint_page_idx < len(page_starts):
                    page_orig_start = page_starts[hint_page_idx]
                    # orig -> norm 索引（线性扫，叶子总数有限，这里 631 个，O(n*m) 可接受）
                    norm_anchor = 0
                    for k, m in enumerate(norm_to_orig):
                        if m >= page_orig_start:
                            norm_anchor = k
                            break
                    pos = norm_text.find(norm_leaf, norm_anchor)
            if pos == -1:
                title_offsets.append(None)
                # 不推进 search_from_norm，让后面节点继续从原位置找
                continue

            end_pos = pos + len(norm_leaf)
            orig_start = norm_to_orig[pos] if pos < len(norm_to_orig) else len(full_text)
            orig_end = norm_to_orig[end_pos] if end_pos < len(norm_to_orig) else len(full_text)
            title_offsets.append((orig_start, orig_end))
            search_from_norm = end_pos  # 推进指针

        # 2) 计算每个叶子的内容范围 = [本叶子标题结束, 下一叶子标题起始)
        chunks: List[ReportChunk] = []
        n_leaves = len(leaves)

        for idx, (sec_path, leaf_title, hint_page) in enumerate(leaves):
            if title_offsets[idx] is None:
                continue
            _, content_start = title_offsets[idx]

            # 找下一个匹配成功的叶子作为切尾
            content_end = len(full_text)
            for j in range(idx + 1, n_leaves):
                if title_offsets[j] is not None:
                    content_end = title_offsets[j][0]
                    break

            raw_segment = full_text[content_start:content_end]
            text = _normalize_whitespace(raw_segment)

            if len(text) < MIN_CHUNK_CHARS:
                continue
            if _is_placeholder_only(text):
                continue

            # 反查页码
            p_start = _offset_to_page(page_starts, content_start) + 1
            p_end_offset = max(content_start, content_end - 1)
            p_end = _offset_to_page(page_starts, p_end_offset) + 1
            if p_end > total_pages:
                p_end = total_pages
            if p_start > total_pages:
                p_start = total_pages

            # 表格抽取（按页范围）
            tables_md: List[str] = []
            if extract_tables:
                seen_signatures = set()  # 跨页表格去重（同一表格在 find_tables 可能跨页时被重复抽）
                for pg in range(p_start - 1, p_end):
                    if pg < 0 or pg >= total_pages:
                        continue
                    page = doc.load_page(pg)
                    try:
                        tabs = page.find_tables()
                    except Exception:
                        continue
                    for t in tabs.tables:
                        try:
                            rows = t.extract()
                        except Exception:
                            continue
                        md = _table_to_markdown(rows)
                        if not md:
                            continue
                        sig = md[:100]  # 前 100 字签名做重复判断
                        if sig in seen_signatures:
                            continue
                        seen_signatures.add(sig)
                        tables_md.append(md)

            # 超长软切
            parts = _split_long_chunk(text)
            for pi, part in enumerate(parts):
                suffix = f"#part{pi+1}" if len(parts) > 1 else ""
                chunk_id = f"{company}_{year}#{sec_path}{suffix}"
                attached_tables = tables_md if pi == 0 else []
                chunks.append(
                    ReportChunk(
                        chunk_id=chunk_id,
                        company=company,
                        year=year,
                        section_path=sec_path,
                        section_title=leaf_title,
                        page_start=p_start,
                        page_end=p_end,
                        text=part,
                        tables=attached_tables,
                        n_chars=len(part),
                    )
                )

        return chunks

    finally:
        doc.close()


def chunks_to_jsonl(chunks: List[ReportChunk], out_path: str | Path) -> int:
    """把 chunks 写成 jsonl"""
    import json

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    return len(chunks)

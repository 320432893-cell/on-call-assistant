# Tantivy 全文索引服务

from typing import Optional, List
from pathlib import Path
import tantivy
import re

from app.config import get_settings

settings = get_settings()


class SearchResult:
    """搜索结果"""

    def __init__(self, doc_id: str, title: str, snippet: str, score: float):
        self.id = doc_id
        self.title = title
        self.snippet = snippet
        self.score = score


class TantivyIndexer:
    """Tantivy索引管理器"""

    _instance: Optional["TantivyIndexer"] = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if TantivyIndexer._initialized:
            return

        self.index_path = Path(settings.TANTIVY_INDEX_PATH)
        self.index_path.mkdir(parents=True, exist_ok=True)

        self.index: Optional[tantivy.Index] = None
        self.writer: Optional[tantivy.IndexWriter] = None

        self._schema = self._build_schema()
        self._init_index()

        TantivyIndexer._initialized = True

    def _build_schema(self) -> tantivy.Schema:
        """构建索引Schema"""
        schema_builder = tantivy.SchemaBuilder()

        # id: 主键，精确匹配
        schema_builder.add_text_field("id", stored=True, tokenizer_name="raw")

        # title: 文本，用 whitespace 保留标点（"AI & 算法"中的 &）
        # 标题短、信息密度高，按空白切分足够；这样 q=& 也能命中 title
        schema_builder.add_text_field(
            "title",
            stored=True,
            tokenizer_name="whitespace",
            index_option="position",
        )

        # content: 正文（已jieba分词），用于检索
        schema_builder.add_text_field(
            "content",
            stored=True,
            tokenizer_name="default",
            index_option="position",
        )

        # content_raw: 原始文本，用于 snippet + 标点字符检索（& / < / / 等）
        # 用 whitespace tokenizer：按空白切分，保留所有非空白字符（含标点）
        schema_builder.add_text_field(
            "content_raw",
            stored=True,
            tokenizer_name="whitespace",
            index_option="position",
        )

        # department: 部门，过滤用
        schema_builder.add_text_field("department", stored=True, tokenizer_name="raw")

        # tags: 标签，文本检索
        schema_builder.add_text_field("tags", stored=True, tokenizer_name="default")

        return schema_builder.build()

    def _init_index(self):
        """初始化索引（带 stale lock 自愈）"""
        index_dir = str(self.index_path)

        # tantivy.Index(schema, path, reuse=True) 自动判断创建或打开
        try:
            self.index = tantivy.Index(self._schema, path=index_dir, reuse=True)
        except Exception:
            # 强制创建新索引
            self.index = tantivy.Index(self._schema, path=index_dir, reuse=False)

        # 初始化 writer（50MB 堆大小）。如果锁被僵尸进程残留，删掉重试一次。
        try:
            self.writer = self.index.writer(heap_size=50_000_000)
        except ValueError as e:
            if "LockBusy" not in str(e) and "lock" not in str(e).lower():
                raise
            print(f"[TantivyIndexer] 检测到 stale lock，自动清理后重试: {e}")
            self._clear_stale_locks()
            self.writer = self.index.writer(heap_size=50_000_000)

    def _clear_stale_locks(self):
        """清理 Tantivy 残留 lock 文件（仅在判定无活跃 writer 时调用）"""
        for lock_name in (".tantivy-writer.lock", ".tantivy-meta.lock"):
            lock_path = self.index_path / lock_name
            if lock_path.exists():
                try:
                    lock_path.unlink()
                    print(f"[TantivyIndexer] 已删除 {lock_path}")
                except OSError as e:
                    print(f"[TantivyIndexer] 删除锁失败 {lock_path}: {e}")

    def add_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        content_raw: str,
        department: str,
        tags: List[str],
    ) -> bool:
        """添加文档到索引"""
        if not self.writer:
            return False

        try:
            doc = tantivy.Document()
            doc.add_text("id", doc_id)
            doc.add_text("title", title)
            doc.add_text("content", content)
            doc.add_text("content_raw", content_raw)
            doc.add_text("department", department)
            doc.add_text("tags", " ".join(tags))

            self.writer.add_document(doc)
            return True

        except Exception as e:
            print(f"[TantivyIndexError] add_document failed: {e}")
            return False

    def commit(self) -> bool:
        """提交索引变更"""
        if not self.writer:
            return False

        try:
            self.writer.commit()
            # 必须reload才能看到新数据
            self.index.reload()
            return True
        except Exception as e:
            print(f"[TantivyIndexError] commit failed: {e}")
            return False

    def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
    ) -> List[SearchResult]:
        """搜索文档"""
        if not self.index:
            return []

        try:
            # 每次搜索获取新的searcher
            searcher = self.index.searcher()

            # 解析查询：title + content（jieba 分词）+ content_raw（标点字符兜底）
            parsed_query = self.index.parse_query(query, default_field_names=["title", "content", "content_raw"])

            # 执行搜索
            top_docs = searcher.search(parsed_query, limit + offset)

            results = []
            # hits 是 [(score, doc_address)] 列表
            hits = top_docs.hits[offset : limit + offset] if offset == 0 else top_docs.hits[offset : limit + offset]
            for score, doc_address in hits:
                doc = searcher.doc(doc_address)

                doc_id = doc.get_first("id") or ""
                title = doc.get_first("title") or ""
                content_raw = doc.get_first("content_raw") or ""

                snippet = self._generate_snippet(content_raw, query)

                results.append(
                    SearchResult(
                        doc_id=doc_id,
                        title=title,
                        snippet=snippet,
                        score=float(score),
                    )
                )

            return results

        except Exception as e:
            print(f"[TantivySearchError] search failed: {e}")
            return []

    def _generate_snippet(self, content: str, query: str, max_length: int = 200) -> str:
        """生成snippet"""
        if not content:
            return ""

        # 清理HTML标签
        text = re.sub(r"<[^>]+>", "", content)
        text = text.replace("\n", " ").strip()

        if len(text) <= max_length:
            return text

        # 尝试在查询词周围截取
        query_lower = query.lower()
        text_lower = text.lower()
        idx = text_lower.find(query_lower)

        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(text), start + max_length)
            snippet = text[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            return snippet

        # 未找到，返回开头
        return text[:max_length] + "..."

    def get_document(self, doc_id: str) -> Optional[dict]:
        """根据ID获取文档"""
        if not self.index:
            return None

        try:
            searcher = self.index.searcher()
            parsed_query = self.index.parse_query(f'id:"{doc_id}"', default_field_names=["id"])

            top_docs = searcher.search(parsed_query, 1)

            for _, doc_address in top_docs:
                doc = searcher.doc(doc_address)
                return {
                    "id": doc.get_first("id") or "",
                    "title": doc.get_first("title") or "",
                    "content_raw": doc.get_first("content_raw") or "",
                    "department": doc.get_first("department") or "",
                    "tags": doc.get_first("tags") or "",
                }

            return None

        except Exception as e:
            print(f"[TantivySearchError] get_document failed: {e}")
            return None


# 模块级单例
_indexer: Optional[TantivyIndexer] = None


def get_indexer() -> TantivyIndexer:
    """获取索引器单例"""
    global _indexer
    if _indexer is None:
        _indexer = TantivyIndexer()
    return _indexer


def close_indexer():
    """关闭索引器"""
    global _indexer
    if _indexer and _indexer.writer:
        _indexer.writer.commit()
        _indexer.writer = None
        _indexer = None

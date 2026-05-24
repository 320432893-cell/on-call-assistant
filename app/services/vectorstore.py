# Qdrant向量数据库服务

import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import get_settings

settings = get_settings()


def _stable_point_id(doc_id: str) -> int:
    """跨进程稳定的 point_id：md5(doc_id) 取前 16 字节作为 64-bit 无符号整数。

    Qdrant point id 接受 uint64；md5 截 16 hex 字符 → 64 bit。
    """
    return int(hashlib.md5(doc_id.encode("utf-8")).hexdigest()[:16], 16)  # noqa: S324 — md5 用作 Qdrant 64-bit 哈希 id,非密码学用途


class VectorSearchResult:
    """向量检索结果"""

    def __init__(self, doc_id: str, score: float, payload: dict):
        self.id = doc_id
        self.score = score
        self.payload = payload


class QdrantService:
    """Qdrant向量服务"""

    _instance: Optional["QdrantService"] = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if QdrantService._initialized:
            return

        self.collection_name = settings.QDRANT_COLLECTION
        self._client: QdrantClient | None = None
        self._dimension: int = 1024  # bge-m3 维度

        self._init_client()
        QdrantService._initialized = True

    def _init_client(self):
        """初始化Qdrant客户端"""
        qdrant_path = Path(settings.QDRANT_PATH)
        qdrant_path.mkdir(parents=True, exist_ok=True)

        try:
            # 嵌入式模式
            self._client = QdrantClient(path=str(qdrant_path))
            print(f"[Qdrant] Initialized at {qdrant_path}")

            # 确保collection存在
            self._ensure_collection()

        except Exception as e:
            print(f"[QdrantError] Failed to initialize: {e}")
            self._client = None

    def _ensure_collection(self):
        """确保collection存在"""
        if not self._client:
            return

        try:
            collections = self._client.get_collections().collections
            names = [c.name for c in collections]

            if self.collection_name not in names:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self._dimension,
                        distance=Distance.COSINE,
                    ),
                )
                print(f"[Qdrant] Created collection: {self.collection_name}")

        except Exception as e:
            print(f"[QdrantError] Failed to ensure collection: {e}")

    def ensure_collection(self, collection: str) -> bool:
        """对外暴露的按需建集合方法（多 collection 场景）"""
        if not self._client:
            return False
        try:
            collections = self._client.get_collections().collections
            names = [c.name for c in collections]
            if collection not in names:
                self._client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(
                        size=self._dimension,
                        distance=Distance.COSINE,
                    ),
                )
                print(f"[Qdrant] Created collection: {collection}")
            return True
        except Exception as e:
            print(f"[QdrantError] ensure_collection({collection}) failed: {e}")
            return False

    def upsert(
        self,
        doc_id: str,
        vector: np.ndarray,
        payload: dict,
    ) -> bool:
        """
        插入/更新向量（自动去重）

        Args:
            doc_id: 文档ID
            vector: 向量 (dim,)
            payload: 元数据 {title, department, tags, content_raw}

        Returns:
            bool: 成功/失败
        """
        if not self._client:
            return False

        try:
            # 先删除旧文档（如果存在）
            self.delete(doc_id)

            # 使用字符串ID转为数字point_id（取hash）
            point_id = abs(hash(doc_id)) % (2**63)

            point = PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={"doc_id": doc_id, **payload},
            )

            self._client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )
            return True

        except Exception as e:
            print(f"[QdrantError] upsert failed: {e}")
            return False

    def upsert_batch(
        self,
        items: list[dict],
    ) -> int:
        """
        批量插入

        Args:
            items: [{"id": str, "vector": np.ndarray, "payload": dict}, ...]

        Returns:
            int: 成功插入数量
        """
        if not self._client or not items:
            return 0

        points = []
        for item in items:
            point_id = abs(hash(item["id"])) % (2**63)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=item["vector"].tolist(),
                    payload={"doc_id": item["id"], **item.get("payload", {})},
                )
            )

        try:
            self._client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            return len(points)

        except Exception as e:
            print(f"[QdrantError] upsert_batch failed: {e}")
            return 0

    def search(
        self,
        query_vector: np.ndarray,
        limit: int = 10,
        score_threshold: float = 0.0,
        department_filter: str | None = None,
    ) -> list[VectorSearchResult]:
        """
        向量相似检索

        Args:
            query_vector: 查询向量
            limit: 返回数量
            score_threshold: 最低相似度阈值
            department_filter: 部门过滤

        Returns:
            List[VectorSearchResult]: 检索结果
        """
        if not self._client:
            return []

        try:
            query_filter = None
            if department_filter:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="department",
                            match=MatchValue(value=department_filter),
                        )
                    ]
                )

            results = self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector.tolist(),
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            ).points

            return [
                VectorSearchResult(
                    doc_id=r.payload.get("doc_id", ""),
                    score=r.score,
                    payload=r.payload,
                )
                for r in results
            ]

        except Exception as e:
            print(f"[QdrantError] search failed: {e}")
            return []

    def get(self, doc_id: str) -> dict | None:
        """根据ID获取文档"""
        if not self._client:
            return None

        try:
            point_id = abs(hash(doc_id)) % (2**63)
            result = self._client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )

            if result:
                return result[0].payload

            return None

        except Exception as e:
            print(f"[QdrantError] get failed: {e}")
            return None

    def delete(self, doc_id: str) -> bool:
        """删除文档"""
        if not self._client:
            return False

        try:
            point_id = abs(hash(doc_id)) % (2**63)
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=[point_id],
            )
            return True

        except Exception as e:
            print(f"[QdrantError] delete failed: {e}")
            return False

    def count(self) -> int:
        """统计文档数量"""
        if not self._client:
            return 0

        try:
            result = self._client.count(collection_name=self.collection_name)
            return result.count

        except Exception as e:
            print(f"[QdrantError] count failed: {e}")
            return 0

    # ---------- 多 collection 接口（v4 年报场景） ----------
    # 默认 collection 行为不变；新方法显式传 collection 名。
    # point_id 用 md5 稳定 hash，跨进程一致（v4 必须）。

    def upsert_batch_to(
        self,
        collection: str,
        items: list[dict],
    ) -> int:
        """批量插入到指定 collection（md5 稳定 point_id）

        Args:
            collection: 目标 collection 名
            items: [{"id": str, "vector": np.ndarray, "payload": dict}, ...]
        """
        if not self._client or not items:
            return 0

        points = []
        for item in items:
            point_id = _stable_point_id(item["id"])
            points.append(
                PointStruct(
                    id=point_id,
                    vector=item["vector"].tolist(),
                    payload={"doc_id": item["id"], **item.get("payload", {})},
                )
            )

        try:
            self._client.upsert(collection_name=collection, points=points)
            return len(points)
        except Exception as e:
            print(f"[QdrantError] upsert_batch_to({collection}) failed: {e}")
            return 0

    def search_in(
        self,
        collection: str,
        query_vector: np.ndarray,
        limit: int = 10,
        score_threshold: float = 0.0,
        filters: dict | None = None,
    ) -> list[VectorSearchResult]:
        """在指定 collection 检索，支持 payload 等值过滤

        Args:
            filters: {field: value} 等值过滤（多字段为 AND）
        """
        if not self._client:
            return []
        try:
            query_filter = None
            if filters:
                must = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items() if v is not None]
                if must:
                    query_filter = Filter(must=must)

            results = self._client.query_points(
                collection_name=collection,
                query=query_vector.tolist(),
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            ).points

            return [
                VectorSearchResult(
                    doc_id=r.payload.get("doc_id", ""),
                    score=r.score,
                    payload=r.payload,
                )
                for r in results
            ]
        except Exception as e:
            print(f"[QdrantError] search_in({collection}) failed: {e}")
            return []

    def count_in(self, collection: str) -> int:
        """统计指定 collection 文档数"""
        if not self._client:
            return 0
        try:
            return self._client.count(collection_name=collection).count
        except Exception as e:
            print(f"[QdrantError] count_in({collection}) failed: {e}")
            return 0

    def scroll_distinct(
        self,
        collection: str,
        fields: list[str],
        limit: int = 10000,
    ) -> list[dict]:
        """扫描 collection 所有 payload，返回指定 fields 的去重组合

        用于 /v4/companies 这种"已灌库公司列表"接口。
        """
        if not self._client:
            return []
        try:
            seen = set()
            out: list[dict] = []
            next_offset = None
            while True:
                points, next_offset = self._client.scroll(
                    collection_name=collection,
                    limit=min(256, limit),
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for p in points:
                    key = tuple(p.payload.get(f) for f in fields)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({f: p.payload.get(f) for f in fields})
                    if len(out) >= limit:
                        return out
                if next_offset is None:
                    break
            return out
        except Exception as e:
            print(f"[QdrantError] scroll_distinct({collection}) failed: {e}")
            return []

    def health_check(self) -> bool:
        """健康检查"""
        return self._client is not None


# 模块级单例
_vectorstore: QdrantService | None = None


def get_vectorstore() -> QdrantService:
    """获取向量服务单例"""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = QdrantService()
    return _vectorstore

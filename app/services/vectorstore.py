# Qdrant向量数据库服务

from typing import Optional, List
from pathlib import Path
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import get_settings

settings = get_settings()


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
        self._client: Optional[QdrantClient] = None
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
        items: List[dict],
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
        department_filter: Optional[str] = None,
    ) -> List[VectorSearchResult]:
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

            from qdrant_client.models import SearchRequest

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

    def get(self, doc_id: str) -> Optional[dict]:
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

    def health_check(self) -> bool:
        """健康检查"""
        return self._client is not None


# 模块级单例
_vectorstore: Optional[QdrantService] = None


def get_vectorstore() -> QdrantService:
    """获取向量服务单例"""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = QdrantService()
    return _vectorstore

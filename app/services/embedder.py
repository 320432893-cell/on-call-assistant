# 职责：封装文本向量模型加载、单条/批量编码和嵌入服务单例。
# 不做什么：不处理 HTTP 请求、向量数据库持久化或业务检索排序。
# 允许依赖层：app.config、外部 embedding/model 库。
# 谁不应该 import：app.models、app.config、路由以外的低层配置模块不应反向依赖本服务。
# Embedding服务：本地sentence-transformers + bge-m3

import os

# 使用国内镜像加速 HuggingFace 模型下载（首次拉取约 2GB）
# 注意：必须在 import sentence_transformers / transformers / huggingface_hub 之前设置
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import logging
from typing import Optional

import numpy as np

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class EmbeddingService:
    """文本向量嵌入服务"""

    _instance: Optional["EmbeddingService"] = None
    _initialized = False

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if EmbeddingService._initialized:
            return

        self.model_name = settings.EMBEDDING_MODEL or "BAAI/bge-m3"
        self._model = None
        self._tokenizer = None
        self._dimension: int = 1024  # bge-m3 默认维度

        self._load_model()
        EmbeddingService._initialized = True

    def _load_model(self) -> None:
        """懒加载模型"""
        if self._model is not None:
            return

        try:
            # 动态导入，避免启动时加载
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            logger.info("embedding_model_loading model=%s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
            logger.info("embedding_model_loaded model=%s dimension=%s", self.model_name, self._dimension)

        except Exception:
            logger.exception("embedding_model_load_failed model=%s", self.model_name)
            self._model = None

    def encode(
        self,
        texts: str | list[str],
        *,
        is_query: bool = False,
    ) -> np.ndarray | None:
        """
        编码文本为向量

        Args:
            texts: 单条文本或多条文本列表
            is_query: True=查询侧（加 bge 官方 query 前缀）；False=文档侧（不加前缀）
                bge-m3 推荐做法：建索引时 passage 不加前缀，查询时 query 加前缀
                让 query 和 passage 在向量空间形成不对称匹配，命中率显著高于双侧都加。

        Returns:
            numpy.ndarray: 向量数组 [dim] 或 [batch, dim]
        """
        if self._model is None:
            self._load_model()

        if self._model is None:
            return None

        try:
            if is_query:
                prefix = "为这个句子生成表示以用于检索相关文章："
                if isinstance(texts, str):
                    texts = f"{prefix}{texts}"
                else:
                    texts = [f"{prefix}{t}" for t in texts]

            return self._model.encode(
                texts,
                normalize_embeddings=True,  # L2归一化
                convert_to_numpy=True,
            )

        except Exception:
            text_count = 1 if isinstance(texts, str) else len(texts)
            logger.exception(
                "embedding_encode_failed model=%s text_count=%s is_query=%s", self.model_name, text_count, is_query
            )
            return None

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[np.ndarray] | None:
        """
        批量编码（分batch处理）

        Args:
            texts: 文本列表
            batch_size: 批次大小

        Returns:
            List[np.ndarray]: 向量列表
        """
        if not texts:
            return []

        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self.encode(batch)
            if embeddings is not None:
                results.extend(embeddings)

        return results

    @property
    def dimension(self) -> int:
        """返回向量维度"""
        return self._dimension

    def health_check(self) -> bool:
        """服务健康检查"""
        if self._model is None:
            self._load_model()
        return self._model is not None


# 模块级单例
_embedder: EmbeddingService | None = None


def get_embedder() -> EmbeddingService:
    """获取Embedding服务单例"""
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder

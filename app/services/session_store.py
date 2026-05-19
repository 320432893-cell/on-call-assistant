# Redis 会话存储：保存对话历史，TTL 自动过期

import json
import time
import uuid
from typing import Optional, List

import redis

from app.config import get_settings

settings = get_settings()


class SessionStore:
    """会话存储：以 session_id 为键，存对话消息列表"""

    _instance: Optional["SessionStore"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        self._client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._ttl = settings.REDIS_SESSION_TTL

    def _key(self, session_id: str) -> str:
        return f"oncall:session:{session_id}"

    def health_check(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def create_session(self) -> str:
        """生成新 session_id"""
        return uuid.uuid4().hex

    def get_history(self, session_id: str) -> List[dict]:
        """获取会话历史；不存在或损坏返回空列表"""
        raw = self._client.get(self._key(session_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data.get("history", [])
        except json.JSONDecodeError:
            return []

    def append_message(self, session_id: str, role: str, content: str):
        """追加一条消息并刷新 TTL"""
        history = self.get_history(session_id)
        history.append(
            {
                "role": role,
                "content": content,
                "ts": int(time.time()),
            }
        )
        self._client.setex(
            self._key(session_id),
            self._ttl,
            json.dumps({"history": history}, ensure_ascii=False),
        )

    def clear_session(self, session_id: str):
        """删除会话"""
        self._client.delete(self._key(session_id))


_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store

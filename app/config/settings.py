# On-Call Assistant 配置

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 应用配置
    APP_NAME: str = "On-Call Assistant"
    DEBUG: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SESSION_TTL: int = 1800

    # Tantivy
    TANTIVY_INDEX_PATH: str = "./indexes/tantivy"

    # Qdrant
    QDRANT_PATH: str = "./indexes/qdrant"
    QDRANT_COLLECTION: str = "sop_documents"

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DEVICE: str = "cpu"

    # LLM Provider 主开关
    LLM_PROVIDER: str = "openai_compat"  # anthropic | openai_compat | gemini

    # OpenAI 兼容（覆盖 OpenAI / DeepSeek / 通义 / Kimi 等）
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-chat"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Agent 状态机
    AGENT_MAX_STEPS: int = 6
    AGENT_STATE_TIMEOUT: int = 300
    AGENT_TOOL_TIMEOUT: int = 10
    AGENT_GENERATE_TIMEOUT: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()

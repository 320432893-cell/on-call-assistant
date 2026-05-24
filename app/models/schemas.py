from datetime import datetime

from pydantic import BaseModel, Field

# ==================== Phase1: 文档入库 ====================


class DocumentInput(BaseModel):
    """文档入库请求"""

    id: str = Field(..., description="文档ID，如 sop-001")
    html: str = Field(..., description="HTML原文")


class DocumentResponse(BaseModel):
    """文档入库响应"""

    id: str
    title: str


# ==================== 搜索结果 ====================


class SearchResult(BaseModel):
    """单条搜索结果"""

    id: str
    title: str
    snippet: str
    score: float = Field(..., description="相关性评分（BM25 或余弦相似度等，量纲不固定）")


class SearchResponse(BaseModel):
    """搜索响应"""

    query: str
    results: list[SearchResult]


# ==================== Phase3: Agent对话 ====================


class ChatRequest(BaseModel):
    """对话请求"""

    message: str = Field(..., min_length=1, description="用户消息")
    session_id: str | None = Field(None, description="会话ID，续接历史")
    provider: str | None = Field(None, description="LLM Provider，默认配置")


class ChatSession(BaseModel):
    """会话状态（Redis存储）"""

    session_id: str
    state: str = Field(default="S0_IDLE")
    history: list[dict] = Field(default_factory=list)
    context: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ToolCall(BaseModel):
    """工具调用记录"""

    tool: str
    args: dict
    result: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentResponse(BaseModel):
    """Agent响应（SSE事件）"""

    event: str = Field(..., description="事件类型: think/tool_call/clarify/answer/error")
    data: dict = Field(default_factory=dict)


# ==================== 表单补充 ====================


class ClarifyForm(BaseModel):
    """信息补充表单"""

    problem_type: str | None = Field(None, description="问题类型")
    system_scope: list[str] | None = Field(None, description="涉及系统")
    severity: str | None = Field(None, description="严重等级 P0-P3")
    has_tried: str | None = Field(None, description="已尝试步骤")

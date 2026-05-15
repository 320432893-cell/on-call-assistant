# Phase3: On-Call Agent SSE 接口

import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from app.services.session_store import get_session_store
from app.services.agent import AgentStateMachine, get_llm_provider

router = APIRouter(prefix="/v3", tags=["Phase3-Agent"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


def _sse_format(event: str, data: dict) -> str:
    """SSE 帧格式"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """SSE 流式对话；客户端断开（AbortController.abort()）时尽快停止"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    store = get_session_store()
    if not store.health_check():
        raise HTTPException(status_code=503, detail="Redis 不可用，请检查 REDIS_URL")

    session_id = req.session_id or store.create_session()

    try:
        provider = get_llm_provider()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM Provider 初始化失败: {e}")

    history_raw = store.get_history(session_id)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in history_raw
        if m["role"] in ("user", "assistant") and m.get("content")
    ]

    async def event_stream():
        yield _sse_format("session", {"session_id": session_id})

        machine = AgentStateMachine(provider=provider)
        final_answer = ""
        aborted = False
        try:
            async for ev in machine.run(user_message=req.message, history=history):
                # 客户端按了暂停（AbortController）→ 提前结束
                if await request.is_disconnected():
                    aborted = True
                    break
                if ev.event == "answer":
                    final_answer = ev.data.get("text", "")
                yield _sse_format(ev.event, ev.data)
        except Exception as e:
            yield _sse_format("error", {"message": f"Agent 异常: {e}"})
            yield _sse_format("done", {})
            return

        # 暂停时仍写入：用户消息 + 已生成的部分回答（标记 [已暂停]）
        # 这样下一轮对话能保留上下文
        store.append_message(session_id, "user", req.message)
        if final_answer:
            suffix = "\n\n[已暂停]" if aborted else ""
            store.append_message(session_id, "assistant", final_answer + suffix)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """查询会话历史"""
    store = get_session_store()
    if not store.health_check():
        raise HTTPException(status_code=503, detail="Redis 不可用")
    return {"session_id": session_id, "history": store.get_history(session_id)}


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    store = get_session_store()
    store.clear_session(session_id)
    return {"ok": True}


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    template = request.app.templates
    return template.TemplateResponse(request, "v3_chat.html")

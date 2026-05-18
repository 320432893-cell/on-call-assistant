# Agent 状态机
# 4 状态：S0_IDLE → S1_PLAN → S2_TOOL → S3_GENERATE → S4_DONE
#   S1_PLAN     LLM 决策（直接答 / 调 readFile）
#   S2_TOOL     执行 readFile（多次工具时循环回 S1）
#   S3_GENERATE 综合工具结果生成最终回答
#   S4_DONE     输出完成

from __future__ import annotations
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, List

from app.config import get_settings
from .llm_provider import BaseLLMProvider, LLMEvent
from .tools import (
    READ_FILE_TOOL_SCHEMA,
    WRITE_FILE_TOOL_SCHEMA,
    read_file_tool,
    write_file_tool,
)
from .prompts import get_system_prompt

settings = get_settings()


@dataclass
class AgentEvent:
    """对外发射的 SSE 事件"""
    event: str  # state | think | tool_call | tool_result | answer | error | done
    data: dict = field(default_factory=dict)


class AgentStateMachine:
    """单轮对话状态机"""

    def __init__(self, provider: BaseLLMProvider, max_steps: Optional[int] = None):
        self._provider = provider
        self._max_steps = max_steps or settings.AGENT_MAX_STEPS

    async def run(
        self,
        user_message: str,
        history: List[dict],
    ) -> AsyncIterator[AgentEvent]:
        """运行一轮对话

        Args:
            user_message: 本轮用户消息
            history: 之前的对话历史（统一格式：role + content / tool_calls / tool_call_id）

        Yields:
            AgentEvent
        """
        # 初始化消息：历史 + 本轮
        messages: List[dict] = list(history) + [{"role": "user", "content": user_message}]
        tools = [READ_FILE_TOOL_SCHEMA, WRITE_FILE_TOOL_SCHEMA]
        system = get_system_prompt()

        # S0 → S1
        yield AgentEvent(event="state", data={"state": "S1_PLAN"})

        step = 0
        final_answer_emitted = False

        while step < self._max_steps:
            step += 1

            # ===== S1_PLAN：LLM 决策 =====
            assistant_text = ""
            tool_calls: List[dict] = []
            stop_reason: Optional[str] = None

            try:
                async for ev in self._provider.stream_chat(
                    messages=messages,
                    tools=tools,
                    system=system,
                ):
                    if ev.type == "text" and ev.text:
                        assistant_text += ev.text
                        yield AgentEvent(event="think", data={"text": ev.text})
                    elif ev.type == "tool_use":
                        tool_calls.append({
                            "id": ev.tool_call_id,
                            "name": ev.tool_name,
                            "args": ev.tool_args or {},
                        })
                    elif ev.type == "end":
                        stop_reason = ev.stop_reason
            except Exception as e:
                yield AgentEvent(event="error", data={"message": f"LLM 调用失败: {e}"})
                yield AgentEvent(event="done", data={})
                return

            # 没有工具调用 → 进入 S3_GENERATE（其实文本已边流边发了）
            if not tool_calls:
                yield AgentEvent(event="state", data={"state": "S3_GENERATE"})
                yield AgentEvent(event="answer", data={"text": assistant_text})
                final_answer_emitted = True
                break

            # ===== S2_TOOL：执行工具 =====
            yield AgentEvent(event="state", data={"state": "S2_TOOL"})

            # 把 assistant 的 tool_calls 加入 messages
            messages.append({
                "role": "assistant",
                "content": assistant_text,
                "tool_calls": tool_calls,
            })

            # 执行每个工具
            for tc in tool_calls:
                yield AgentEvent(event="tool_call", data={
                    "tool": tc["name"],
                    "args": tc["args"],
                    "id": tc["id"],
                })

                if tc["name"] == "readFile":
                    fname = tc["args"].get("fname", "")
                    result = read_file_tool(fname)
                elif tc["name"] == "writeFile":
                    fname = tc["args"].get("fname", "")
                    content = tc["args"].get("content", "")
                    result = write_file_tool(fname, content)
                else:
                    result = f"[Error] 未知工具: {tc['name']}"

                # 截断 SSE 推送的 result（避免一次推太大）
                preview_len = 500
                preview = result[:preview_len] + ("..." if len(result) > preview_len else "")
                yield AgentEvent(event="tool_result", data={
                    "tool": tc["name"],
                    "id": tc["id"],
                    "ok": not result.startswith("[Error]"),
                    "preview": preview,
                    "length": len(result),
                })

                # 回填消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "tool_name": tc["name"],
                    "content": result,
                })

            # 循环回 S1_PLAN
            yield AgentEvent(event="state", data={"state": "S1_PLAN"})

        if not final_answer_emitted:
            yield AgentEvent(event="error", data={
                "message": f"已达最大步数 {self._max_steps}，未生成最终回答",
            })

        # S4_DONE
        yield AgentEvent(event="state", data={"state": "S4_DONE"})
        yield AgentEvent(event="done", data={})

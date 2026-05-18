# LLM Provider 抽象层
# 3 个 Provider 覆盖所有主流模型：
#   - AnthropicProvider     → Claude
#   - OpenAICompatProvider  → OpenAI / DeepSeek / 通义 / Kimi / 豆包 / 智谱 等
#   - GeminiProvider        → Google Gemini

from __future__ import annotations
from typing import AsyncIterator, Optional
from dataclasses import dataclass

from app.config import get_settings

settings = get_settings()


# ==================== 统一事件模型 ====================

@dataclass
class LLMEvent:
    """Provider 流式输出标准化事件

    type:
      - text          模型文本增量（delta）
      - tool_use      模型决定调用工具（一次性）
      - end           本轮 LLM 响应结束
    """
    type: str
    text: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_call_id: Optional[str] = None
    stop_reason: Optional[str] = None  # end_turn | tool_use | stop


# ==================== 基类 ====================

class BaseLLMProvider:
    """LLM Provider 抽象基类"""

    name: str = "base"

    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        """流式对话

        Args:
            messages: 标准化消息列表 [{role, content}] 或带 tool_use/tool_result 的混合消息
            tools: 标准化工具描述 [{name, description, parameters(JSON Schema)}]
            system: system prompt

        Yields:
            LLMEvent
        """
        raise NotImplementedError


# ==================== Anthropic ====================

class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self):
        from anthropic import AsyncAnthropic
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY 未配置")
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL

    def _to_anthropic_messages(self, messages: list[dict]) -> list[dict]:
        """统一消息 → Anthropic 消息

        统一格式：
          {role: user/assistant, content: str}
          {role: assistant, tool_calls: [{id, name, args}]}
          {role: tool, tool_call_id, content}
        """
        out = []
        for m in messages:
            role = m["role"]
            if role == "tool":
                out.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m["content"],
                    }],
                })
            elif role == "assistant" and m.get("tool_calls"):
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["args"],
                    })
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": role, "content": m["content"]})
        return out

    def _to_anthropic_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]

    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        kwargs = {
            "model": self._model,
            "max_tokens": 2048,
            "messages": self._to_anthropic_messages(messages),
        }
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)
        if system:
            kwargs["system"] = system

        current_tool = None
        current_tool_input = ""

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                etype = getattr(event, "type", None)

                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool = {
                            "id": block.id,
                            "name": block.name,
                            "args": {},
                        }
                        current_tool_input = ""

                elif etype == "content_block_delta":
                    delta = event.delta
                    dtype = getattr(delta, "type", None)
                    if dtype == "text_delta":
                        yield LLMEvent(type="text", text=delta.text)
                    elif dtype == "input_json_delta":
                        current_tool_input += delta.partial_json

                elif etype == "content_block_stop":
                    if current_tool is not None:
                        import json as _json
                        try:
                            current_tool["args"] = _json.loads(current_tool_input or "{}")
                        except _json.JSONDecodeError:
                            current_tool["args"] = {}
                        yield LLMEvent(
                            type="tool_use",
                            tool_name=current_tool["name"],
                            tool_args=current_tool["args"],
                            tool_call_id=current_tool["id"],
                        )
                        current_tool = None
                        current_tool_input = ""

            final = await stream.get_final_message()
            yield LLMEvent(type="end", stop_reason=final.stop_reason)


# ==================== OpenAI 兼容 ====================

class OpenAICompatProvider(BaseLLMProvider):
    """OpenAI 兼容：通过 base_url + api_key + model 适配 OpenAI / DeepSeek / 通义 / Kimi 等"""

    name = "openai_compat"

    def __init__(self):
        from openai import AsyncOpenAI
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY 未配置")
        self._client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL or None,
        )
        self._model = settings.LLM_MODEL

    def _to_openai_messages(self, messages: list[dict]) -> list[dict]:
        """统一消息 → OpenAI 消息"""
        out = []
        for m in messages:
            role = m["role"]
            if role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": m["tool_call_id"],
                    "content": m["content"],
                })
            elif role == "assistant" and m.get("tool_calls"):
                import json as _json
                out.append({
                    "role": "assistant",
                    "content": m.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": _json.dumps(tc["args"], ensure_ascii=False),
                            },
                        }
                        for tc in m["tool_calls"]
                    ],
                })
            else:
                out.append({"role": role, "content": m["content"]})
        return out

    def _to_openai_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        msgs = self._to_openai_messages(messages)
        if system:
            msgs = [{"role": "system", "content": system}] + msgs

        kwargs = {
            "model": self._model,
            "messages": msgs,
            "stream": True,
            "max_tokens": 2048,
        }
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)

        # 累积 tool_call deltas（OpenAI 流式按 index 分片）
        tool_calls_buf: dict[int, dict] = {}
        stop_reason: Optional[str] = None

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                yield LLMEvent(type="text", text=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    buf = tool_calls_buf.setdefault(idx, {"id": "", "name": "", "args_str": ""})
                    if tc.id:
                        buf["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            buf["name"] = tc.function.name
                        if tc.function.arguments:
                            buf["args_str"] += tc.function.arguments

            if choice.finish_reason:
                stop_reason = choice.finish_reason

        # 流结束后发射所有 tool_use
        if tool_calls_buf:
            import json as _json
            for idx in sorted(tool_calls_buf.keys()):
                buf = tool_calls_buf[idx]
                try:
                    args = _json.loads(buf["args_str"] or "{}")
                except _json.JSONDecodeError:
                    args = {}
                yield LLMEvent(
                    type="tool_use",
                    tool_name=buf["name"],
                    tool_args=args,
                    tool_call_id=buf["id"] or f"call_{idx}",
                )

        yield LLMEvent(type="end", stop_reason=stop_reason or "stop")


# ==================== Gemini ====================

class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(self):
        from google import genai
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY 未配置")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL

    def _to_gemini_contents(self, messages: list[dict]) -> list[dict]:
        """统一消息 → Gemini contents"""
        out = []
        for m in messages:
            role = m["role"]
            if role == "tool":
                out.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": m.get("tool_name", "readFile"),
                            "response": {"content": m["content"]},
                        }
                    }],
                })
            elif role == "assistant" and m.get("tool_calls"):
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                for tc in m["tool_calls"]:
                    parts.append({
                        "function_call": {"name": tc["name"], "args": tc["args"]}
                    })
                out.append({"role": "model", "parts": parts})
            else:
                gemini_role = "model" if role == "assistant" else "user"
                out.append({"role": gemini_role, "parts": [{"text": m["content"]}]})
        return out

    def _to_gemini_tools(self, tools: list[dict]) -> list[dict]:
        return [{
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                }
                for t in tools
            ]
        }]

    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        from google.genai import types as gtypes

        contents = self._to_gemini_contents(messages)
        config = gtypes.GenerateContentConfig(
            system_instruction=system,
            tools=self._to_gemini_tools(tools) if tools else None,
            max_output_tokens=2048,
        )

        stop_reason = "stop"
        # google-genai 异步流式 API
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if not chunk.candidates:
                continue
            cand = chunk.candidates[0]
            if not cand.content or not cand.content.parts:
                continue
            for part in cand.content.parts:
                if getattr(part, "text", None):
                    yield LLMEvent(type="text", text=part.text)
                fc = getattr(part, "function_call", None)
                if fc:
                    yield LLMEvent(
                        type="tool_use",
                        tool_name=fc.name,
                        tool_args=dict(fc.args) if fc.args else {},
                        tool_call_id=f"gemini_{fc.name}",
                    )
                    stop_reason = "tool_use"
            if cand.finish_reason:
                stop_reason = str(cand.finish_reason).lower()

        yield LLMEvent(type="end", stop_reason=stop_reason)


# ==================== 工厂 ====================

_provider: Optional[BaseLLMProvider] = None


def get_llm_provider() -> BaseLLMProvider:
    """按 settings.LLM_PROVIDER 返回单例 Provider"""
    global _provider
    if _provider is not None:
        return _provider

    p = (settings.LLM_PROVIDER or "openai_compat").lower()
    if p == "anthropic":
        _provider = AnthropicProvider()
    elif p == "gemini":
        _provider = GeminiProvider()
    else:
        _provider = OpenAICompatProvider()
    return _provider


def reset_llm_provider():
    """重置（用于测试或配置切换）"""
    global _provider
    _provider = None

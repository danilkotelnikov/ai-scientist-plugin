"""OpenAI provider adapter.

Also serves as a base class for OpenAI-compatible providers (OpenRouter,
Together, DeepSeek, Moonshot, Zhipu, self-hosted) — subclasses only need to
override ``__init__`` to pass a ``base_url`` and ``capabilities`` to
report their per-provider metadata.
"""
from __future__ import annotations
from typing import AsyncIterator, Iterable

from openai import APIStatusError, AsyncOpenAI, RateLimitError

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from ..exceptions import AuthError, ContextOverflow, ProviderUnavailable, RateLimited


class OpenAIAdapter:
    name = "openai"

    def __init__(self, api_key: str, base_url: str | None = None):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="openai",
            region="global",
            max_context=128_000,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=True,
            supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        try:
            r = await self._client.chat.completions.create(
                model=req.model,
                messages=msgs,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stop=req.stop_sequences or None,
                tools=req.tools,
            )
        except RateLimitError as e:
            raise RateLimited(self.name) from e
        except APIStatusError as e:
            if e.status_code in (500, 502, 503, 504):
                raise ProviderUnavailable(self.name, str(e)) from e
            if e.status_code == 401:
                raise AuthError(self.name) from e
            if e.status_code == 400 and "context_length" in str(e):
                raise ContextOverflow(self.name, self.capabilities().max_context, -1) from e
            raise
        choice = r.choices[0]
        return ChatResponse(
            content=choice.message.content or "",
            model=r.model,
            finish_reason=choice.finish_reason or "stop",
            input_tokens=r.usage.prompt_tokens,
            output_tokens=r.usage.completion_tokens,
            tool_calls=[tc.model_dump() for tc in (choice.message.tool_calls or [])] or None,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        stream = await self._client.chat.completions.create(
            model=req.model,
            messages=msgs,
            max_tokens=req.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)

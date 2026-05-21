"""Qwen (Alibaba DashScope) provider adapter.

DashScope returns a status_code on the response object rather than raising
exceptions, so we map those codes onto the BYOK exception hierarchy.
"""
from __future__ import annotations
from typing import AsyncIterator, Iterable

import dashscope

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from ..exceptions import AuthError, ContextOverflow, ProviderUnavailable, RateLimited


class QwenAdapter:
    name = "qwen"

    def __init__(self, api_key: str):
        dashscope.api_key = api_key

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="qwen",
            region="cn",
            max_context=128_000,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=False,
            supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        r = await dashscope.Generation.acall(
            model=req.model,
            messages=msgs,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        if r.status_code == 429:
            raise RateLimited("qwen")
        if r.status_code == 401:
            raise AuthError("qwen")
        if r.status_code in (500, 502, 503, 504):
            raise ProviderUnavailable("qwen", f"status {r.status_code}")
        if r.status_code == 400 and "context" in (getattr(r, "message", "") or "").lower():
            raise ContextOverflow("qwen", 128_000, -1)
        return ChatResponse(
            content=r.output.text or "",
            model=req.model,
            finish_reason=r.output.finish_reason or "stop",
            input_tokens=r.usage.input_tokens,
            output_tokens=r.usage.output_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        async for chunk in await dashscope.Generation.acall(
            model=req.model,
            messages=msgs,
            max_tokens=req.max_tokens,
            stream=True,
        ):
            if chunk.output.text:
                yield chunk.output.text

    def count_tokens(self, messages: Iterable[Message]) -> int:
        # Chinese characters ~3 bytes/token under most BPE schemes; this
        # heuristic over-budgets a bit for mixed Chinese/English text.
        return sum(max(1, len(m.content) // 3) for m in messages)

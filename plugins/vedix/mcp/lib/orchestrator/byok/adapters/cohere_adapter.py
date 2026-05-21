"""Cohere provider adapter — uses the Cohere v2 async client."""
from __future__ import annotations
from typing import AsyncIterator, Iterable

import cohere

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities


class CohereAdapter:
    name = "cohere"

    def __init__(self, api_key: str):
        self._client = cohere.AsyncClientV2(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="cohere",
            region="global",
            max_context=128_000,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=False,
            supports_vision=False,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        r = await self._client.chat(
            model=req.model,
            messages=msgs,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        return ChatResponse(
            content=r.message.content[0].text if r.message.content else "",
            model=req.model,
            finish_reason=r.finish_reason or "stop",
            input_tokens=r.usage.tokens.input_tokens,
            output_tokens=r.usage.tokens.output_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        async for chunk in self._client.chat_stream(model=req.model, messages=msgs):
            if chunk.type == "content-delta":
                yield chunk.delta.message.content.text

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)

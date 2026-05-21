"""Mistral AI (EU) provider adapter."""
from __future__ import annotations
from typing import AsyncIterator, Iterable

from mistralai import Mistral

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from ..exceptions import RateLimited


class MistralAdapter:
    name = "mistral"

    def __init__(self, api_key: str):
        self._client = Mistral(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="mistral",
            region="eu",
            max_context=128_000,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=True,
            supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        try:
            r = await self._client.chat.complete_async(
                model=req.model,
                messages=msgs,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        except Exception as e:
            if "429" in str(e):
                raise RateLimited("mistral") from e
            raise
        c = r.choices[0]
        return ChatResponse(
            content=c.message.content,
            model=r.model,
            finish_reason=c.finish_reason or "stop",
            input_tokens=r.usage.prompt_tokens,
            output_tokens=r.usage.completion_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        async for chunk in self._client.chat.stream_async(model=req.model, messages=msgs):
            if chunk.data.choices and chunk.data.choices[0].delta.content:
                yield chunk.data.choices[0].delta.content

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)

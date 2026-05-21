"""Google Gemini provider adapter."""
from __future__ import annotations
from typing import AsyncIterator, Iterable

import google.generativeai as genai

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from ..exceptions import ContextOverflow, ProviderUnavailable, RateLimited


class GoogleAdapter:
    name = "google"

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="google",
            region="global",
            max_context=2_000_000,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=True,
            supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        model = genai.GenerativeModel(req.model)
        history = "\n".join(f"{m.role}: {m.content}" for m in req.messages)
        try:
            r = await model.generate_content_async(
                history,
                generation_config={
                    "max_output_tokens": req.max_tokens,
                    "temperature": req.temperature,
                },
            )
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "rate" in msg:
                raise RateLimited("google") from e
            if "context" in msg or "token" in msg:
                raise ContextOverflow("google", 2_000_000, -1) from e
            if any(c in msg for c in ("500", "502", "503", "504")):
                raise ProviderUnavailable("google", str(e)) from e
            raise
        return ChatResponse(
            content=r.text or "",
            model=req.model,
            finish_reason=str(r.candidates[0].finish_reason) if r.candidates else "stop",
            input_tokens=r.usage_metadata.prompt_token_count if r.usage_metadata else 0,
            output_tokens=r.usage_metadata.candidates_token_count if r.usage_metadata else 0,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        model = genai.GenerativeModel(req.model)
        history = "\n".join(f"{m.role}: {m.content}" for m in req.messages)
        stream = await model.generate_content_async(history, stream=True)
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)

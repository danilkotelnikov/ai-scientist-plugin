"""Anthropic provider adapter — gold-standard pattern.

Wraps ``anthropic.AsyncAnthropic`` and maps Anthropic-specific errors onto
the BYOK exception hierarchy (RateLimited / ContextOverflow / AuthError /
ProviderUnavailable). The Anthropic message schema separates ``system`` from
``messages``; we strip system messages on the way in and merge them into the
top-level ``system`` parameter.
"""
from __future__ import annotations
from typing import AsyncIterator, Iterable

import anthropic

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from ..exceptions import AuthError, ContextOverflow, ProviderUnavailable, RateLimited


class AnthropicAdapter:
    name = "anthropic"

    def __init__(self, api_key: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="anthropic",
            region="global",
            max_context=200_000,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=True,
            supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        anth_messages = [
            {"role": m.role if m.role != "system" else "user", "content": m.content}
            for m in req.messages
            if m.role != "system"
        ]
        system = next((m.content for m in req.messages if m.role == "system"), None)
        try:
            r = await self._client.messages.create(
                model=req.model,
                messages=anth_messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stop_sequences=req.stop_sequences or None,
                system=system,
                tools=req.tools,
            )
        except anthropic.RateLimitError as e:
            retry_after = None
            try:
                retry_after = float(e.response.headers.get("retry-after", 0))  # type: ignore[union-attr]
            except (AttributeError, ValueError, TypeError):
                retry_after = None
            raise RateLimited("anthropic", retry_after) from e
        except anthropic.APIStatusError as e:
            if e.status_code in (500, 502, 503, 504):
                raise ProviderUnavailable("anthropic", str(e)) from e
            if e.status_code == 401:
                raise AuthError("anthropic") from e
            if e.status_code == 400 and "context" in str(e).lower():
                raise ContextOverflow("anthropic", 200_000, -1) from e
            raise

        content_text = "".join(b.text for b in r.content if hasattr(b, "text"))
        tool_calls = [
            {"name": b.name, "input": b.input, "id": b.id}
            for b in r.content
            if getattr(b, "type", None) == "tool_use"
        ] or None
        return ChatResponse(
            content=content_text,
            model=r.model,
            finish_reason=r.stop_reason or "stop",
            input_tokens=r.usage.input_tokens,
            output_tokens=r.usage.output_tokens,
            tool_calls=tool_calls,
            raw=r.model_dump() if hasattr(r, "model_dump") else None,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        anth_messages = [
            {"role": m.role if m.role != "system" else "user", "content": m.content}
            for m in req.messages
            if m.role != "system"
        ]
        async with self._client.messages.stream(
            model=req.model,
            messages=anth_messages,
            max_tokens=req.max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def count_tokens(self, messages: Iterable[Message]) -> int:
        # Rough estimate; the real anthropic SDK has a count_tokens API but
        # the public wrapper varies by version. ~4 chars/token works for
        # English text and overestimates for code (which is fine for budgeting).
        return sum(max(1, len(m.content) // 4) for m in messages)

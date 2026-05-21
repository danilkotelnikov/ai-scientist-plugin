"""GigaChat (Sber) adapter — mTLS + OAuth2 client-credentials flow.

The official ``gigachat`` Python SDK is synchronous, so we wrap each call in
``asyncio.to_thread``. The mTLS verification requires the Russian Trusted
Root CA bundle (Sber distributes this); pass its filesystem path via
``verify_cert``.
"""
from __future__ import annotations
import asyncio
from typing import AsyncIterator, Iterable

from gigachat import GigaChat
from gigachat.models import Chat as GigaChatChat
from gigachat.models import Messages as GigaMessages
from gigachat.models import MessagesRole

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from ..exceptions import AuthError, ProviderUnavailable, RateLimited


class GigaChatAdapter:
    name = "gigachat"

    def __init__(
        self,
        credentials: str,
        scope: str = "GIGACHAT_API_PERS",
        verify_cert: str | None = None,
    ):
        # credentials = base64("client_id:client_secret")
        # scope = GIGACHAT_API_PERS (personal) or GIGACHAT_API_CORP (corporate)
        # verify_cert = path to Russian Trusted Root CA bundle
        self._client = GigaChat(
            credentials=credentials,
            scope=scope,
            verify_ssl_certs=bool(verify_cert),
            ca_bundle_file=verify_cert,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="gigachat",
            region="ru",
            max_context=32_768,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=False,
            supports_vision=False,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        role_map = {
            "user": MessagesRole.USER,
            "system": MessagesRole.SYSTEM,
            "assistant": MessagesRole.ASSISTANT,
        }
        chat_req = GigaChatChat(
            messages=[
                GigaMessages(role=role_map.get(m.role, MessagesRole.USER), content=m.content)
                for m in req.messages
            ],
            model=req.model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        try:
            r = await asyncio.to_thread(self._client.chat, chat_req)
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "unauthor" in msg:
                raise AuthError("gigachat") from e
            if "429" in msg:
                raise RateLimited("gigachat") from e
            if any(c in msg for c in ("500", "502", "503", "504", "connection")):
                raise ProviderUnavailable("gigachat", str(e)) from e
            raise
        choice = r.choices[0]
        return ChatResponse(
            content=choice.message.content or "",
            model=r.model,
            finish_reason=choice.finish_reason or "stop",
            input_tokens=r.usage.prompt_tokens,
            output_tokens=r.usage.completion_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        # The SDK's stream iterator is synchronous; tee chunks into an asyncio
        # queue so the consumer can ``async for`` over them.
        role_map = {
            "user": MessagesRole.USER,
            "system": MessagesRole.SYSTEM,
            "assistant": MessagesRole.ASSISTANT,
        }
        chat_req = GigaChatChat(
            messages=[
                GigaMessages(role=role_map.get(m.role, MessagesRole.USER), content=m.content)
                for m in req.messages
            ],
            model=req.model,
            stream=True,
        )
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _runner():
            try:
                for chunk in self._client.stream(chat_req):
                    delta = chunk.choices[0].delta.content
                    if delta:
                        asyncio.run_coroutine_threadsafe(queue.put(delta), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        asyncio.create_task(asyncio.to_thread(_runner))
        while True:
            item = await queue.get()
            if item is None:
                return
            yield item

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 3) for m in messages)

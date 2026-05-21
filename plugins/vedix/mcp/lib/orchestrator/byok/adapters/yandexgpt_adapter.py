"""YandexGPT adapter — Yandex Cloud REST API with API-key or IAM-token auth.

Uses ``httpx.AsyncClient`` directly because Yandex Cloud does not have a
unified Python SDK for foundation models. The IAM-token flow is implemented
elsewhere (the CLI ``vedix provider add yandexgpt`` stores either an Api-Key
or an IAM token that the user refreshes manually).
"""
from __future__ import annotations
from typing import AsyncIterator, Iterable

import httpx

from ..base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from ..exceptions import AuthError, ContextOverflow, ProviderUnavailable, RateLimited


class YandexGPTAdapter:
    name = "yandexgpt"

    def __init__(self, api_key: str, folder_id: str):
        # api_key — passed with "Api-Key" prefix; folder_id is the Yandex
        # Cloud folder whose quota this call counts against.
        self._api_key = api_key
        self._folder_id = folder_id
        self._endpoint = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="yandexgpt",
            region="ru",
            max_context=32_000,
            supports_tools=False,
            supports_streaming=True,
            supports_structured_output=False,
            supports_vision=False,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        # YandexGPT model URI format: gpt://<folder_id>/<model_name>/<version>
        model_uri = (
            req.model
            if req.model.startswith("gpt://")
            else f"gpt://{self._folder_id}/{req.model}/latest"
        )
        body = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": req.temperature,
                "maxTokens": str(req.max_tokens),
            },
            "messages": [{"role": m.role, "text": m.content} for m in req.messages],
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Api-Key {self._api_key}",
                    "x-folder-id": self._folder_id,
                },
                json=body,
                timeout=60,
            )
        if r.status_code == 429:
            raise RateLimited("yandexgpt")
        if r.status_code == 401:
            raise AuthError("yandexgpt")
        if r.status_code in (500, 502, 503, 504):
            raise ProviderUnavailable("yandexgpt", f"status {r.status_code}")
        if r.status_code == 400 and "token" in r.text.lower():
            raise ContextOverflow("yandexgpt", 32_000, -1)
        data = r.json()
        alt = data["result"]["alternatives"][0]
        usage = data["result"]["usage"]
        return ChatResponse(
            content=alt["message"]["text"],
            model=data["result"].get("modelVersion", req.model),
            finish_reason=alt.get("status", "stop"),
            input_tokens=int(usage.get("inputTextTokens", "0")),
            output_tokens=int(usage.get("completionTokens", "0")),
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        # YandexGPT streams as JSON objects per line; each chunk carries the
        # full cumulative text, so we yield the delta against the previous.
        model_uri = (
            req.model
            if req.model.startswith("gpt://")
            else f"gpt://{self._folder_id}/{req.model}/latest"
        )
        body = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": True,
                "temperature": req.temperature,
                "maxTokens": str(req.max_tokens),
            },
            "messages": [{"role": m.role, "text": m.content} for m in req.messages],
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self._endpoint,
                headers={
                    "Authorization": f"Api-Key {self._api_key}",
                    "x-folder-id": self._folder_id,
                },
                json=body,
            ) as r:
                import json as _j

                last_text = ""
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = _j.loads(line)
                    cur = chunk["result"]["alternatives"][0]["message"]["text"]
                    delta = cur[len(last_text):]
                    last_text = cur
                    if delta:
                        yield delta

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)

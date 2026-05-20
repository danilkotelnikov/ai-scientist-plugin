# Block 2 — BYOK Multi-Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build a thin BYOK abstraction layer with 14 provider adapters (3 global-direct, 2 routers, 4 Chinese-direct, 2 Russian-direct, 2 EU/other, 1 self-hosted), a configurable fallback chain with automatic retry on rate-limit / 5xx / context-overflow, per-agent-class provider selection, and a JSONL cost ledger.

**Architecture:** A `ProviderAdapter` protocol normalizes provider-specific quirks behind a uniform `chat()` + `stream()` + `count_tokens()` interface. A `ProviderRouter` consults the user's configured chain, dispatches to the first available provider, catches retryable errors and falls back to the next. Per-agent overrides allow cheaper models for register-discriminator / generator tasks and stronger models for manuscript-writer / reviewer. All calls log to `~/.vedix/byok/cost_ledger.jsonl`. Capability detection (tool-use? streaming? max-context?) ensures the dispatcher only routes a call to a provider that can actually serve it.

**Tech Stack:**
- Python 3.11+ (typing.Protocol, asyncio)
- Provider SDKs: `anthropic`, `openai`, `google-generativeai`, `gigachat`, `yandex-cloud`, `dashscope`, `cohere`, `mistralai`, `httpx` (for OpenRouter / DeepSeek / Moonshot / Zhipu / Together / self-hosted via OpenAI-compatible REST)
- `pytest`, `pytest-asyncio`, `respx` (HTTP mocking)

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §3.2.

---

## File structure

```
plugins/vedix/mcp/lib/orchestrator/byok/
├── __init__.py
├── base.py                      # ProviderAdapter protocol + ChatRequest/Response dataclasses
├── capabilities.py              # Per-provider capability registry
├── exceptions.py                # RateLimited, ContextOverflow, ProviderUnavailable, etc.
├── router.py                    # ProviderRouter — fallback-chain dispatch
├── cost_ledger.py               # JSONL append; aggregation by `vedix cost report`
├── secrets.py                   # Load + store API keys in ~/.vedix/byok/secrets/
├── adapters/
│   ├── __init__.py
│   ├── anthropic_adapter.py     # Anthropic
│   ├── openai_adapter.py        # OpenAI
│   ├── google_adapter.py        # Google Gemini
│   ├── openrouter_adapter.py    # OpenRouter (OpenAI-compatible)
│   ├── together_adapter.py      # Together.ai (OpenAI-compatible)
│   ├── deepseek_adapter.py      # DeepSeek (OpenAI-compatible)
│   ├── qwen_adapter.py          # Alibaba DashScope / Qwen
│   ├── moonshot_adapter.py      # Moonshot Kimi (OpenAI-compatible)
│   ├── zhipu_adapter.py         # Zhipu GLM (OpenAI-compatible)
│   ├── gigachat_adapter.py      # Sber GigaChat (mTLS + OAuth2)
│   ├── yandexgpt_adapter.py     # YandexGPT (IAM token refresh)
│   ├── mistral_adapter.py       # Mistral AI
│   ├── cohere_adapter.py        # Cohere
│   └── local_adapter.py         # Self-hosted OpenAI-compatible (vLLM, Ollama, llama.cpp)
└── cli/
    └── provider.py              # `vedix provider {add,remove,list,test,chain}` subcommands
```

## Task 1: Provider protocol + dataclasses

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/base.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/exceptions.py`
- Test: `tests/byok/test_base_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/byok/test_base_protocol.py
from plugins.vedix.mcp.lib.orchestrator.byok.base import (
    ProviderAdapter, ChatRequest, ChatResponse, Message
)

def test_chat_request_dataclass_shape():
    req = ChatRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-opus-4",
        max_tokens=100,
    )
    assert req.messages[0].content == "hi"
    assert req.max_tokens == 100

def test_provider_adapter_protocol_has_required_methods():
    methods = {m for m in dir(ProviderAdapter) if not m.startswith("_")}
    assert {"chat", "stream", "count_tokens", "capabilities", "name"}.issubset(methods)
```

- [ ] **Step 2: Run test — verify it fails**

```
pytest tests/byok/test_base_protocol.py -v
# Expected: FAIL (module does not exist)
```

- [ ] **Step 3: Write the protocol**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import AsyncIterator, Iterable, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]

@dataclass
class Message:
    role: Role
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None

@dataclass
class ChatRequest:
    messages: list[Message]
    model: str
    max_tokens: int = 1024
    temperature: float = 0.7
    stop_sequences: list[str] = field(default_factory=list)
    tools: list[dict] | None = None
    response_schema: dict | None = None

@dataclass
class ChatResponse:
    content: str
    model: str
    finish_reason: str
    input_tokens: int
    output_tokens: int
    tool_calls: list[dict] | None = None
    raw: dict | None = None  # provider-native payload for debugging

@dataclass
class ProviderCapabilities:
    name: str
    region: Literal["global", "ru", "cn", "eu", "self-hosted"]
    max_context: int
    supports_tools: bool
    supports_streaming: bool
    supports_structured_output: bool
    supports_vision: bool = False

@runtime_checkable
class ProviderAdapter(Protocol):
    @property
    def name(self) -> str: ...
    def capabilities(self) -> ProviderCapabilities: ...
    async def chat(self, req: ChatRequest) -> ChatResponse: ...
    async def stream(self, req: ChatRequest) -> AsyncIterator[str]: ...
    def count_tokens(self, messages: Iterable[Message]) -> int: ...
```

- [ ] **Step 4: Add exceptions**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/exceptions.py
class BYOKError(Exception): ...
class RateLimited(BYOKError):
    def __init__(self, provider: str, retry_after: float | None = None):
        super().__init__(f"{provider} rate-limited")
        self.provider = provider
        self.retry_after = retry_after
class ContextOverflow(BYOKError):
    def __init__(self, provider: str, max_context: int, requested: int):
        super().__init__(f"{provider} max_context={max_context}, requested={requested}")
class ProviderUnavailable(BYOKError):
    def __init__(self, provider: str, reason: str):
        super().__init__(f"{provider} unavailable: {reason}")
class AuthError(BYOKError):
    def __init__(self, provider: str):
        super().__init__(f"{provider} auth failed")
class CapabilityMissing(BYOKError):
    def __init__(self, provider: str, capability: str):
        super().__init__(f"{provider} lacks capability: {capability}")
```

- [ ] **Step 5: Run test — verify it passes**

```
pytest tests/byok/test_base_protocol.py -v
# Expected: PASS
```

- [ ] **Step 6: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/base.py plugins/vedix/mcp/lib/orchestrator/byok/exceptions.py tests/byok/test_base_protocol.py
git commit -m "feat(B2): ProviderAdapter protocol + BYOK dataclasses + typed exceptions"
```

## Task 2: Anthropic adapter (gold-standard pattern)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/anthropic_adapter.py`
- Test: `tests/byok/test_anthropic_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/byok/test_anthropic_adapter.py
import pytest
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.anthropic_adapter import AnthropicAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message
from plugins.vedix.mcp.lib.orchestrator.byok.exceptions import RateLimited

@pytest.mark.asyncio
async def test_chat_returns_response():
    adapter = AnthropicAdapter(api_key="sk-test")
    with patch.object(adapter._client.messages, "create", new=AsyncMock()) as m:
        m.return_value.content = [type("C", (), {"text": "hi back", "type": "text"})()]
        m.return_value.model = "claude-opus-4-20250514"
        m.return_value.stop_reason = "end_turn"
        m.return_value.usage = type("U", (), {"input_tokens": 5, "output_tokens": 3})()
        resp = await adapter.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="claude-opus-4"))
        assert resp.content == "hi back"
        assert resp.input_tokens == 5

@pytest.mark.asyncio
async def test_chat_raises_RateLimited_on_429():
    import anthropic
    adapter = AnthropicAdapter(api_key="sk-test")
    with patch.object(adapter._client.messages, "create", side_effect=anthropic.RateLimitError("rate limit", response=type("R",(),{"headers":{}})(), body={})):
        with pytest.raises(RateLimited):
            await adapter.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="claude-opus-4"))

def test_capabilities():
    adapter = AnthropicAdapter(api_key="sk-test")
    caps = adapter.capabilities()
    assert caps.name == "anthropic"
    assert caps.region == "global"
    assert caps.supports_tools is True
    assert caps.max_context >= 200_000
```

- [ ] **Step 2: Run test — verify it fails**

```
pytest tests/byok/test_anthropic_adapter.py -v
# Expected: FAIL (module does not exist)
```

- [ ] **Step 3: Implement the adapter**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/anthropic_adapter.py
from __future__ import annotations
from typing import AsyncIterator, Iterable
import anthropic
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message
from ..exceptions import RateLimited, ContextOverflow, ProviderUnavailable, AuthError

class AnthropicAdapter:
    name = "anthropic"

    def __init__(self, api_key: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="anthropic", region="global",
            max_context=200_000, supports_tools=True,
            supports_streaming=True, supports_structured_output=True,
            supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        anth_messages = [{"role": m.role if m.role != "system" else "user", "content": m.content}
                         for m in req.messages if m.role != "system"]
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
            retry_after = float(e.response.headers.get("retry-after", 0)) if hasattr(e, "response") else None
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
        tool_calls = [{"name": b.name, "input": b.input, "id": b.id} for b in r.content if b.type == "tool_use"] or None
        return ChatResponse(
            content=content_text, model=r.model, finish_reason=r.stop_reason or "stop",
            input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens,
            tool_calls=tool_calls, raw=r.model_dump() if hasattr(r, "model_dump") else None,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        anth_messages = [{"role": m.role if m.role != "system" else "user", "content": m.content}
                         for m in req.messages if m.role != "system"]
        async with self._client.messages.stream(
            model=req.model, messages=anth_messages, max_tokens=req.max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)  # rough estimate; real anthropic SDK has count_tokens API
```

- [ ] **Step 4: Run test — verify it passes**

```
pytest tests/byok/test_anthropic_adapter.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/adapters/anthropic_adapter.py tests/byok/test_anthropic_adapter.py
git commit -m "feat(B2): Anthropic adapter — gold-standard ProviderAdapter pattern"
```

## Task 3: OpenAI + Google adapters (same pattern, different SDKs)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/openai_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/google_adapter.py`
- Test: `tests/byok/test_openai_adapter.py`, `tests/byok/test_google_adapter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/byok/test_openai_adapter.py
import pytest
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.openai_adapter import OpenAIAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message

@pytest.mark.asyncio
async def test_openai_chat():
    adapter = OpenAIAdapter(api_key="sk-test")
    with patch.object(adapter._client.chat.completions, "create", new=AsyncMock()) as m:
        m.return_value.choices = [type("C", (), {"message": type("M", (), {"content": "ok", "tool_calls": None})(), "finish_reason": "stop"})()]
        m.return_value.model = "gpt-5"
        m.return_value.usage = type("U", (), {"prompt_tokens": 5, "completion_tokens": 2})()
        resp = await adapter.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="gpt-5"))
        assert resp.content == "ok"

def test_openai_capabilities():
    adapter = OpenAIAdapter(api_key="sk-test")
    caps = adapter.capabilities()
    assert caps.name == "openai"
    assert caps.region == "global"
    assert caps.max_context >= 128_000
```

```python
# tests/byok/test_google_adapter.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.google_adapter import GoogleAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message

@pytest.mark.asyncio
async def test_google_chat():
    adapter = GoogleAdapter(api_key="ai-test")
    fake_response = MagicMock(text="hi", candidates=[MagicMock(finish_reason="STOP")], usage_metadata=MagicMock(prompt_token_count=5, candidates_token_count=2))
    with patch("google.generativeai.GenerativeModel") as MM:
        MM.return_value.generate_content_async = AsyncMock(return_value=fake_response)
        resp = await adapter.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="gemini-2.5-pro"))
        assert resp.content == "hi"
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/byok/test_openai_adapter.py tests/byok/test_google_adapter.py -v
# Expected: FAIL
```

- [ ] **Step 3: Implement OpenAI adapter**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/openai_adapter.py
from __future__ import annotations
from typing import AsyncIterator, Iterable
from openai import AsyncOpenAI, APIStatusError, RateLimitError
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message
from ..exceptions import RateLimited, ContextOverflow, ProviderUnavailable, AuthError

class OpenAIAdapter:
    name = "openai"

    def __init__(self, api_key: str, base_url: str | None = None):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="openai", region="global", max_context=128_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=True, supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        try:
            r = await self._client.chat.completions.create(
                model=req.model, messages=msgs,
                max_tokens=req.max_tokens, temperature=req.temperature,
                stop=req.stop_sequences or None, tools=req.tools,
            )
        except RateLimitError as e:
            raise RateLimited("openai") from e
        except APIStatusError as e:
            if e.status_code in (500, 502, 503, 504):
                raise ProviderUnavailable("openai", str(e)) from e
            if e.status_code == 401:
                raise AuthError("openai") from e
            if e.status_code == 400 and "context_length" in str(e):
                raise ContextOverflow("openai", 128_000, -1) from e
            raise
        choice = r.choices[0]
        return ChatResponse(
            content=choice.message.content or "", model=r.model,
            finish_reason=choice.finish_reason or "stop",
            input_tokens=r.usage.prompt_tokens, output_tokens=r.usage.completion_tokens,
            tool_calls=[tc.model_dump() for tc in (choice.message.tool_calls or [])] or None,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        stream = await self._client.chat.completions.create(
            model=req.model, messages=msgs, max_tokens=req.max_tokens, stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)
```

- [ ] **Step 4: Implement Google adapter**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/google_adapter.py
from __future__ import annotations
from typing import AsyncIterator, Iterable
import google.generativeai as genai
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message
from ..exceptions import RateLimited, ContextOverflow, ProviderUnavailable

class GoogleAdapter:
    name = "google"

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="google", region="global", max_context=2_000_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=True, supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        model = genai.GenerativeModel(req.model)
        history = "\n".join(f"{m.role}: {m.content}" for m in req.messages)
        try:
            r = await model.generate_content_async(
                history,
                generation_config={"max_output_tokens": req.max_tokens, "temperature": req.temperature},
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
            content=r.text or "", model=req.model,
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
```

- [ ] **Step 5: Run tests — verify they pass**

```
pytest tests/byok/ -v
# Expected: PASS
```

- [ ] **Step 6: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/adapters/openai_adapter.py plugins/vedix/mcp/lib/orchestrator/byok/adapters/google_adapter.py tests/byok/test_openai_adapter.py tests/byok/test_google_adapter.py
git commit -m "feat(B2): OpenAI + Google adapters"
```

## Task 4: OpenAI-compatible adapters bundle (OpenRouter, Together, DeepSeek, Moonshot, Zhipu, self-hosted)

Six providers that all speak the OpenAI Chat Completions schema. We extend `OpenAIAdapter` with a per-provider `base_url` + name override.

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/openrouter_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/together_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/deepseek_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/moonshot_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/zhipu_adapter.py`
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/local_adapter.py`
- Test: `tests/byok/test_openai_compatible_adapters.py`

- [ ] **Step 1: Write the test (one parameterized test for all six)**

```python
# tests/byok/test_openai_compatible_adapters.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.openrouter_adapter import OpenRouterAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.together_adapter import TogetherAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.deepseek_adapter import DeepSeekAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.moonshot_adapter import MoonshotAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.zhipu_adapter import ZhipuAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.local_adapter import LocalAdapter

@pytest.mark.parametrize("AdapterCls, expected_name, expected_region, expected_base_url_substring", [
    (OpenRouterAdapter, "openrouter", "global", "openrouter.ai"),
    (TogetherAdapter, "together", "global", "together.xyz"),
    (DeepSeekAdapter, "deepseek", "cn", "deepseek.com"),
    (MoonshotAdapter, "moonshot", "cn", "moonshot.cn"),
    (ZhipuAdapter, "zhipu", "cn", "bigmodel.cn"),
])
def test_openai_compatible_adapter_capabilities(AdapterCls, expected_name, expected_region, expected_base_url_substring):
    adapter = AdapterCls(api_key="test")
    caps = adapter.capabilities()
    assert caps.name == expected_name
    assert caps.region == expected_region
    assert expected_base_url_substring in adapter._client.base_url.host

def test_local_adapter_takes_custom_url():
    adapter = LocalAdapter(api_key="none", base_url="http://localhost:8000/v1")
    caps = adapter.capabilities()
    assert caps.name == "local"
    assert caps.region == "self-hosted"
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/byok/test_openai_compatible_adapters.py -v
# Expected: FAIL
```

- [ ] **Step 3: Implement the 6 adapters**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/openrouter_adapter.py
from .openai_adapter import OpenAIAdapter
from ..base import ProviderCapabilities

class OpenRouterAdapter(OpenAIAdapter):
    name = "openrouter"

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        # OpenRouter requires HTTP-Referer + X-Title headers
        self._client._default_headers.update({
            "HTTP-Referer": "https://vedix.ai",
            "X-Title": "Vedix",
        })

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="openrouter", region="global", max_context=128_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=True, supports_vision=True,
        )
```

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/together_adapter.py
from .openai_adapter import OpenAIAdapter
from ..base import ProviderCapabilities

class TogetherAdapter(OpenAIAdapter):
    name = "together"

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.together.xyz/v1")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="together", region="global", max_context=32_768,
            supports_tools=False, supports_streaming=True,
            supports_structured_output=False, supports_vision=False,
        )
```

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/deepseek_adapter.py
from .openai_adapter import OpenAIAdapter
from ..base import ProviderCapabilities

class DeepSeekAdapter(OpenAIAdapter):
    name = "deepseek"

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.deepseek.com/v1")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="deepseek", region="cn", max_context=64_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=True, supports_vision=False,
        )
```

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/moonshot_adapter.py
from .openai_adapter import OpenAIAdapter
from ..base import ProviderCapabilities

class MoonshotAdapter(OpenAIAdapter):
    name = "moonshot"

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.moonshot.cn/v1")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="moonshot", region="cn", max_context=128_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=False, supports_vision=False,
        )
```

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/zhipu_adapter.py
from .openai_adapter import OpenAIAdapter
from ..base import ProviderCapabilities

class ZhipuAdapter(OpenAIAdapter):
    name = "zhipu"

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://open.bigmodel.cn/api/paas/v4")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="zhipu", region="cn", max_context=128_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=False, supports_vision=False,
        )
```

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/local_adapter.py
from .openai_adapter import OpenAIAdapter
from ..base import ProviderCapabilities

class LocalAdapter(OpenAIAdapter):
    name = "local"

    def __init__(self, api_key: str = "none", base_url: str = "http://localhost:8000/v1", max_context: int = 8192):
        super().__init__(api_key=api_key, base_url=base_url)
        self._max_context = max_context

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="local", region="self-hosted", max_context=self._max_context,
            supports_tools=False, supports_streaming=True,
            supports_structured_output=False, supports_vision=False,
        )
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/byok/test_openai_compatible_adapters.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/adapters/openrouter_adapter.py plugins/vedix/mcp/lib/orchestrator/byok/adapters/together_adapter.py plugins/vedix/mcp/lib/orchestrator/byok/adapters/deepseek_adapter.py plugins/vedix/mcp/lib/orchestrator/byok/adapters/moonshot_adapter.py plugins/vedix/mcp/lib/orchestrator/byok/adapters/zhipu_adapter.py plugins/vedix/mcp/lib/orchestrator/byok/adapters/local_adapter.py tests/byok/test_openai_compatible_adapters.py
git commit -m "feat(B2): six OpenAI-compatible adapters (OpenRouter, Together, DeepSeek, Moonshot, Zhipu, local)"
```

## Task 5: Qwen DashScope adapter (Alibaba-native SDK)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/qwen_adapter.py`
- Test: `tests/byok/test_qwen_adapter.py`

- [ ] **Step 1: Write test**

```python
# tests/byok/test_qwen_adapter.py
import pytest
from unittest.mock import patch, MagicMock
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.qwen_adapter import QwenAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message

@pytest.mark.asyncio
async def test_qwen_chat():
    adapter = QwenAdapter(api_key="sk-test")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.output.text = "ok"
    fake_response.output.finish_reason = "stop"
    fake_response.usage.input_tokens = 5
    fake_response.usage.output_tokens = 2
    with patch("dashscope.Generation.acall", return_value=fake_response):
        resp = await adapter.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="qwen-max"))
        assert resp.content == "ok"

def test_qwen_capabilities():
    adapter = QwenAdapter(api_key="sk-test")
    caps = adapter.capabilities()
    assert caps.name == "qwen"
    assert caps.region == "cn"
    assert caps.max_context >= 32_000
```

- [ ] **Step 2: Run — verify it fails**

```
pytest tests/byok/test_qwen_adapter.py -v
```

- [ ] **Step 3: Implement adapter**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/qwen_adapter.py
from __future__ import annotations
from typing import AsyncIterator, Iterable
import dashscope
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message
from ..exceptions import RateLimited, ContextOverflow, ProviderUnavailable, AuthError

class QwenAdapter:
    name = "qwen"

    def __init__(self, api_key: str):
        dashscope.api_key = api_key

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="qwen", region="cn", max_context=128_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=False, supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        r = await dashscope.Generation.acall(
            model=req.model, messages=msgs,
            max_tokens=req.max_tokens, temperature=req.temperature,
        )
        if r.status_code == 429:
            raise RateLimited("qwen")
        if r.status_code == 401:
            raise AuthError("qwen")
        if r.status_code in (500, 502, 503, 504):
            raise ProviderUnavailable("qwen", f"status {r.status_code}")
        if r.status_code == 400 and "context" in (r.message or "").lower():
            raise ContextOverflow("qwen", 128_000, -1)
        return ChatResponse(
            content=r.output.text or "", model=req.model,
            finish_reason=r.output.finish_reason or "stop",
            input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        async for chunk in await dashscope.Generation.acall(
            model=req.model, messages=msgs, max_tokens=req.max_tokens, stream=True,
        ):
            if chunk.output.text:
                yield chunk.output.text

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 3) for m in messages)  # Chinese chars ~3 bytes/token
```

- [ ] **Step 4: Run — verify it passes**

```
pytest tests/byok/test_qwen_adapter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/adapters/qwen_adapter.py tests/byok/test_qwen_adapter.py
git commit -m "feat(B2): Qwen / Alibaba DashScope adapter"
```

## Task 6: GigaChat adapter (Sber — mTLS + OAuth2)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/gigachat_adapter.py`
- Test: `tests/byok/test_gigachat_adapter.py`

- [ ] **Step 1: Write test**

```python
# tests/byok/test_gigachat_adapter.py
import pytest
from unittest.mock import patch, MagicMock
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.gigachat_adapter import GigaChatAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message

@pytest.mark.asyncio
async def test_gigachat_chat(tmp_path):
    cert = tmp_path / "russian_trusted_root_ca.crt"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIfake\n-----END CERTIFICATE-----")
    adapter = GigaChatAdapter(credentials="Y2xpZW50OnNlY3JldA==", scope="GIGACHAT_API_PERS", verify_cert=str(cert))

    with patch.object(adapter._client, "chat") as m:
        m.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="привет"), finish_reason="stop")],
            usage=MagicMock(prompt_tokens=5, completion_tokens=3),
            model="GigaChat-Pro",
        )
        resp = await adapter.chat(ChatRequest(messages=[Message(role="user", content="привет")], model="GigaChat-Pro"))
        assert resp.content == "привет"

def test_gigachat_capabilities(tmp_path):
    cert = tmp_path / "ca.crt"
    cert.write_text("dummy")
    adapter = GigaChatAdapter(credentials="dGVzdA==", verify_cert=str(cert))
    caps = adapter.capabilities()
    assert caps.name == "gigachat"
    assert caps.region == "ru"
```

- [ ] **Step 2: Run — verify it fails**

```
pytest tests/byok/test_gigachat_adapter.py -v
```

- [ ] **Step 3: Implement adapter**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/gigachat_adapter.py
"""GigaChat (Sber) adapter — mTLS + OAuth2 client-credentials flow."""
from __future__ import annotations
import asyncio
from typing import AsyncIterator, Iterable
from gigachat import GigaChat
from gigachat.models import Chat as GigaChatChat, Messages as GigaMessages, MessagesRole
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message
from ..exceptions import RateLimited, ProviderUnavailable, AuthError

class GigaChatAdapter:
    name = "gigachat"

    def __init__(self, credentials: str, scope: str = "GIGACHAT_API_PERS", verify_cert: str | None = None):
        # credentials = base64("client_id:client_secret"); scope = GIGACHAT_API_PERS or GIGACHAT_API_CORP
        # verify_cert = path to Russian Trusted Root CA (sber distributes this; required for mTLS)
        self._client = GigaChat(credentials=credentials, scope=scope, verify_ssl_certs=bool(verify_cert), ca_bundle_file=verify_cert)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="gigachat", region="ru", max_context=32_768,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=False, supports_vision=False,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        # The gigachat python SDK is sync — wrap in to_thread
        role_map = {"user": MessagesRole.USER, "system": MessagesRole.SYSTEM, "assistant": MessagesRole.ASSISTANT}
        chat_req = GigaChatChat(
            messages=[GigaMessages(role=role_map.get(m.role, MessagesRole.USER), content=m.content) for m in req.messages],
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
            content=choice.message.content or "", model=r.model,
            finish_reason=choice.finish_reason or "stop",
            input_tokens=r.usage.prompt_tokens, output_tokens=r.usage.completion_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        # SSE-stream the response by polling the SDK stream iterator in a thread
        role_map = {"user": MessagesRole.USER, "system": MessagesRole.SYSTEM, "assistant": MessagesRole.ASSISTANT}
        chat_req = GigaChatChat(
            messages=[GigaMessages(role=role_map.get(m.role, MessagesRole.USER), content=m.content) for m in req.messages],
            model=req.model,
            stream=True,
        )
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _runner():
            try:
                for chunk in self._client.stream(chat_req):
                    if chunk.choices[0].delta.content:
                        asyncio.run_coroutine_threadsafe(queue.put(chunk.choices[0].delta.content), asyncio.get_event_loop())
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), asyncio.get_event_loop())

        asyncio.create_task(asyncio.to_thread(_runner))
        while True:
            item = await queue.get()
            if item is None:
                return
            yield item

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 3) for m in messages)
```

- [ ] **Step 4: Run — verify it passes**

```
pytest tests/byok/test_gigachat_adapter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/adapters/gigachat_adapter.py tests/byok/test_gigachat_adapter.py
git commit -m "feat(B2): GigaChat (Sber) adapter — mTLS + OAuth2 client-credentials"
```

## Task 7: YandexGPT adapter (IAM token refresh)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/adapters/yandexgpt_adapter.py`
- Test: `tests/byok/test_yandexgpt_adapter.py`

- [ ] **Step 1: Write test**

```python
# tests/byok/test_yandexgpt_adapter.py
import pytest
from unittest.mock import patch, MagicMock
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.yandexgpt_adapter import YandexGPTAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message

@pytest.mark.asyncio
async def test_yandexgpt_chat():
    adapter = YandexGPTAdapter(api_key="AQVNxxx", folder_id="b1g000000000000000000")
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "result": {
            "alternatives": [{"message": {"text": "привет", "role": "assistant"}, "status": "ALTERNATIVE_STATUS_FINAL"}],
            "usage": {"inputTextTokens": "5", "completionTokens": "3", "totalTokens": "8"},
            "modelVersion": "yandexgpt:lite",
        }
    }
    fake_response.status_code = 200
    with patch("httpx.AsyncClient.post", return_value=fake_response):
        resp = await adapter.chat(ChatRequest(messages=[Message(role="user", content="привет")], model="yandexgpt-lite"))
        assert resp.content == "привет"

def test_yandexgpt_capabilities():
    adapter = YandexGPTAdapter(api_key="t", folder_id="b1g")
    caps = adapter.capabilities()
    assert caps.region == "ru"
```

- [ ] **Step 2: Run — verify fails**

- [ ] **Step 3: Implement adapter**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/yandexgpt_adapter.py
"""YandexGPT adapter — Yandex Cloud REST API with API-key or IAM-token auth."""
from __future__ import annotations
from typing import AsyncIterator, Iterable
import httpx
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message
from ..exceptions import RateLimited, ProviderUnavailable, AuthError, ContextOverflow

class YandexGPTAdapter:
    name = "yandexgpt"

    def __init__(self, api_key: str, folder_id: str):
        # api_key = "Api-Key" prefix is added by us; folder_id is the Yandex Cloud folder
        self._api_key = api_key
        self._folder_id = folder_id
        self._endpoint = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="yandexgpt", region="ru", max_context=32_000,
            supports_tools=False, supports_streaming=True,
            supports_structured_output=False, supports_vision=False,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        # yandexgpt model URI format: gpt://<folder_id>/<model_name>/<version>
        model_uri = req.model if req.model.startswith("gpt://") else f"gpt://{self._folder_id}/{req.model}/latest"
        body = {
            "modelUri": model_uri,
            "completionOptions": {"stream": False, "temperature": req.temperature, "maxTokens": str(req.max_tokens)},
            "messages": [{"role": m.role, "text": m.content} for m in req.messages],
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                self._endpoint,
                headers={"Authorization": f"Api-Key {self._api_key}", "x-folder-id": self._folder_id},
                json=body, timeout=60,
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
        # YandexGPT SSE
        model_uri = req.model if req.model.startswith("gpt://") else f"gpt://{self._folder_id}/{req.model}/latest"
        body = {
            "modelUri": model_uri,
            "completionOptions": {"stream": True, "temperature": req.temperature, "maxTokens": str(req.max_tokens)},
            "messages": [{"role": m.role, "text": m.content} for m in req.messages],
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", self._endpoint,
                headers={"Authorization": f"Api-Key {self._api_key}", "x-folder-id": self._folder_id},
                json=body,
            ) as r:
                last_text = ""
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    import json as _j
                    chunk = _j.loads(line)
                    cur = chunk["result"]["alternatives"][0]["message"]["text"]
                    delta = cur[len(last_text):]
                    last_text = cur
                    if delta:
                        yield delta

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)
```

- [ ] **Step 4: Run — verify it passes**

```
pytest tests/byok/test_yandexgpt_adapter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/adapters/yandexgpt_adapter.py tests/byok/test_yandexgpt_adapter.py
git commit -m "feat(B2): YandexGPT adapter — Yandex Cloud REST + Api-Key auth"
```

## Task 8: Mistral + Cohere adapters

Short tasks; both use their native SDK.

- [ ] **Step 1: Write tests**

```python
# tests/byok/test_mistral_cohere_adapters.py
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.mistral_adapter import MistralAdapter
from plugins.vedix.mcp.lib.orchestrator.byok.adapters.cohere_adapter import CohereAdapter

def test_mistral_capabilities():
    a = MistralAdapter(api_key="t")
    caps = a.capabilities()
    assert caps.name == "mistral"
    assert caps.region == "eu"

def test_cohere_capabilities():
    a = CohereAdapter(api_key="t")
    caps = a.capabilities()
    assert caps.name == "cohere"
    assert caps.region == "global"
```

- [ ] **Step 2: Implement Mistral**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/mistral_adapter.py
from __future__ import annotations
from typing import AsyncIterator, Iterable
from mistralai import Mistral
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message
from ..exceptions import RateLimited, ProviderUnavailable

class MistralAdapter:
    name = "mistral"
    def __init__(self, api_key: str):
        self._client = Mistral(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="mistral", region="eu", max_context=128_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=True, supports_vision=True,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        try:
            r = await self._client.chat.complete_async(model=req.model, messages=msgs, max_tokens=req.max_tokens, temperature=req.temperature)
        except Exception as e:
            if "429" in str(e):
                raise RateLimited("mistral") from e
            raise
        c = r.choices[0]
        return ChatResponse(
            content=c.message.content, model=r.model, finish_reason=c.finish_reason or "stop",
            input_tokens=r.usage.prompt_tokens, output_tokens=r.usage.completion_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        async for chunk in self._client.chat.stream_async(model=req.model, messages=msgs):
            if chunk.data.choices and chunk.data.choices[0].delta.content:
                yield chunk.data.choices[0].delta.content

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)
```

- [ ] **Step 3: Implement Cohere**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/adapters/cohere_adapter.py
from __future__ import annotations
from typing import AsyncIterator, Iterable
import cohere
from ..base import ProviderAdapter, ProviderCapabilities, ChatRequest, ChatResponse, Message

class CohereAdapter:
    name = "cohere"
    def __init__(self, api_key: str):
        self._client = cohere.AsyncClientV2(api_key=api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="cohere", region="global", max_context=128_000,
            supports_tools=True, supports_streaming=True,
            supports_structured_output=False, supports_vision=False,
        )

    async def chat(self, req: ChatRequest) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        r = await self._client.chat(model=req.model, messages=msgs, max_tokens=req.max_tokens, temperature=req.temperature)
        return ChatResponse(
            content=r.message.content[0].text if r.message.content else "",
            model=req.model, finish_reason=r.finish_reason or "stop",
            input_tokens=r.usage.tokens.input_tokens, output_tokens=r.usage.tokens.output_tokens,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[str]:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        async for chunk in self._client.chat_stream(model=req.model, messages=msgs):
            if chunk.type == "content-delta":
                yield chunk.delta.message.content.text

    def count_tokens(self, messages: Iterable[Message]) -> int:
        return sum(max(1, len(m.content) // 4) for m in messages)
```

- [ ] **Step 4: Run + commit**

```
pytest tests/byok/test_mistral_cohere_adapters.py -v
git add plugins/vedix/mcp/lib/orchestrator/byok/adapters/mistral_adapter.py plugins/vedix/mcp/lib/orchestrator/byok/adapters/cohere_adapter.py tests/byok/test_mistral_cohere_adapters.py
git commit -m "feat(B2): Mistral + Cohere adapters"
```

## Task 9: Provider router with fallback chain

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/router.py`
- Test: `tests/byok/test_router.py`

- [ ] **Step 1: Write test**

```python
# tests/byok/test_router.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from plugins.vedix.mcp.lib.orchestrator.byok.router import ProviderRouter
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, ChatResponse, Message, ProviderCapabilities
from plugins.vedix.mcp.lib.orchestrator.byok.exceptions import RateLimited, ProviderUnavailable

def _make_adapter(name, region="global", chat_fn=None):
    a = MagicMock()
    a.name = name
    a.capabilities.return_value = ProviderCapabilities(name=name, region=region, max_context=100_000,
                                                       supports_tools=True, supports_streaming=True,
                                                       supports_structured_output=True)
    a.chat = chat_fn if chat_fn else AsyncMock(return_value=ChatResponse(content="ok", model="m", finish_reason="stop", input_tokens=1, output_tokens=1))
    return a

@pytest.mark.asyncio
async def test_router_dispatches_to_first():
    a1 = _make_adapter("a1")
    a2 = _make_adapter("a2")
    router = ProviderRouter(chain=[a1, a2])
    r = await router.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="m"))
    assert r.content == "ok"
    a1.chat.assert_called_once()
    a2.chat.assert_not_called()

@pytest.mark.asyncio
async def test_router_falls_back_on_rate_limit():
    a1 = _make_adapter("a1", chat_fn=AsyncMock(side_effect=RateLimited("a1")))
    a2 = _make_adapter("a2")
    router = ProviderRouter(chain=[a1, a2])
    r = await router.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="m"))
    assert r.content == "ok"
    a1.chat.assert_called_once()
    a2.chat.assert_called_once()

@pytest.mark.asyncio
async def test_router_raises_when_all_fail():
    a1 = _make_adapter("a1", chat_fn=AsyncMock(side_effect=RateLimited("a1")))
    a2 = _make_adapter("a2", chat_fn=AsyncMock(side_effect=ProviderUnavailable("a2", "500")))
    router = ProviderRouter(chain=[a1, a2])
    with pytest.raises(ProviderUnavailable):
        await router.chat(ChatRequest(messages=[Message(role="user", content="hi")], model="m"))

@pytest.mark.asyncio
async def test_per_agent_class_override():
    primary = _make_adapter("primary")
    cheap = _make_adapter("cheap")
    router = ProviderRouter(chain=[primary], per_agent_class={"register-discriminator": [cheap]})
    await router.chat(ChatRequest(messages=[Message(role="user", content="x")], model="m"), agent_class="register-discriminator")
    cheap.chat.assert_called_once()
    primary.chat.assert_not_called()
```

- [ ] **Step 2: Run — verify fails**

```
pytest tests/byok/test_router.py -v
```

- [ ] **Step 3: Implement router**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/router.py
from __future__ import annotations
import asyncio
import logging
from typing import AsyncIterator
from .base import ProviderAdapter, ChatRequest, ChatResponse, Message
from .exceptions import RateLimited, ContextOverflow, ProviderUnavailable, AuthError, CapabilityMissing
from .cost_ledger import CostLedger

logger = logging.getLogger(__name__)

class ProviderRouter:
    def __init__(
        self,
        chain: list[ProviderAdapter],
        per_agent_class: dict[str, list[ProviderAdapter]] | None = None,
        cost_ledger: CostLedger | None = None,
    ):
        self.chain = chain
        self.per_agent_class = per_agent_class or {}
        self.cost_ledger = cost_ledger

    def _resolve_chain(self, agent_class: str | None) -> list[ProviderAdapter]:
        if agent_class and agent_class in self.per_agent_class:
            return self.per_agent_class[agent_class]
        return self.chain

    async def chat(self, req: ChatRequest, agent_class: str | None = None) -> ChatResponse:
        chain = self._resolve_chain(agent_class)
        last_err: Exception | None = None
        for adapter in chain:
            # Capability check
            caps = adapter.capabilities()
            if req.tools and not caps.supports_tools:
                logger.warning(f"skip {adapter.name}: no tool support, request had tools")
                last_err = CapabilityMissing(adapter.name, "tools")
                continue
            if req.response_schema and not caps.supports_structured_output:
                logger.warning(f"skip {adapter.name}: no structured-output, request had schema")
                last_err = CapabilityMissing(adapter.name, "structured_output")
                continue
            try:
                resp = await adapter.chat(req)
                if self.cost_ledger:
                    self.cost_ledger.record(
                        provider=adapter.name, model=resp.model, agent_class=agent_class or "default",
                        input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                    )
                return resp
            except RateLimited as e:
                logger.warning(f"{adapter.name} rate-limited; retry_after={e.retry_after}; trying next")
                last_err = e
                if e.retry_after and len(chain) == 1:
                    await asyncio.sleep(min(e.retry_after, 30))
            except (ProviderUnavailable, AuthError) as e:
                logger.warning(f"{adapter.name} unavailable: {e}; trying next")
                last_err = e
            except ContextOverflow as e:
                # Context overflow is provider-agnostic — don't fallback (the next provider
                # almost certainly has similar context). Re-raise immediately.
                raise
        raise last_err or ProviderUnavailable("router", "no providers configured")

    async def stream(self, req: ChatRequest, agent_class: str | None = None) -> AsyncIterator[str]:
        chain = self._resolve_chain(agent_class)
        for adapter in chain:
            try:
                async for chunk in adapter.stream(req):
                    yield chunk
                return
            except (RateLimited, ProviderUnavailable, AuthError):
                continue
        raise ProviderUnavailable("router", "no providers could stream")
```

- [ ] **Step 4: Implement cost ledger**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/cost_ledger.py
from __future__ import annotations
import json
import os
import time
from pathlib import Path

# Pricing per 1M tokens (input, output) — rough; updated quarterly via vedix update-prices
PRICING_USD_PER_M = {
    "anthropic": {"claude-opus-4": (15.0, 75.0), "claude-sonnet-4": (3.0, 15.0)},
    "openai": {"gpt-5": (5.0, 15.0), "gpt-5-xhigh": (10.0, 30.0)},
    "google": {"gemini-2.5-pro": (1.25, 5.0)},
    "deepseek": {"deepseek-chat": (0.14, 0.28), "deepseek-reasoner": (0.55, 2.19)},
    "qwen": {"qwen-max": (0.5, 1.5)},
    "moonshot": {"moonshot-v1-128k": (1.0, 3.0)},
    "zhipu": {"glm-4": (0.5, 1.5)},
    "gigachat": {"GigaChat-Pro": (0.5, 1.5)},
    "yandexgpt": {"yandexgpt": (0.4, 1.2)},
    "mistral": {"mistral-large-latest": (2.0, 6.0)},
    "cohere": {"command-r-plus": (3.0, 15.0)},
    "openrouter": {},  # passes through provider pricing
    "together": {},
    "local": {},
}

def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

class CostLedger:
    def __init__(self, path: Path | None = None):
        self.path = path or _home() / ".vedix" / "byok" / "cost_ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, *, provider: str, model: str, agent_class: str, input_tokens: int, output_tokens: int) -> None:
        prices = PRICING_USD_PER_M.get(provider, {}).get(model, (0.0, 0.0))
        cost = (input_tokens / 1_000_000) * prices[0] + (output_tokens / 1_000_000) * prices[1]
        entry = {
            "ts": time.time(),
            "provider": provider,
            "model": model,
            "agent_class": agent_class,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 5: Run — verify it passes**

```
pytest tests/byok/test_router.py -v
```

- [ ] **Step 6: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/router.py plugins/vedix/mcp/lib/orchestrator/byok/cost_ledger.py tests/byok/test_router.py
git commit -m "feat(B2): ProviderRouter with fallback chain + per-agent override + cost ledger"
```

## Task 10: CLI subcommands — `vedix provider {add,list,remove,test,chain}`

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/byok/cli/provider.py`
- Modify: `plugins/vedix/scripts/vedix-cli.py` (route subcommand)
- Test: `tests/byok/test_provider_cli.py`

- [ ] **Step 1: Write test**

```python
# tests/byok/test_provider_cli.py
import json
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.byok.cli.provider import (
    add_provider, list_providers, remove_provider, set_chain
)

def test_add_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    add_provider("anthropic", api_key="sk-test", confirm=False)
    listing = list_providers()
    assert "anthropic" in [p["name"] for p in listing]

def test_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    add_provider("anthropic", api_key="sk-test", confirm=False)
    remove_provider("anthropic", confirm=False)
    assert all(p["name"] != "anthropic" for p in list_providers())

def test_set_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    add_provider("anthropic", api_key="sk-test", confirm=False)
    add_provider("openai", api_key="sk-test", confirm=False)
    set_chain(["anthropic", "openai"])
    cfg = json.loads((tmp_path / ".vedix" / "byok" / "providers.json").read_text())
    assert cfg["chain"] == ["anthropic", "openai"]
```

- [ ] **Step 2: Run — verify fails**

- [ ] **Step 3: Implement CLI**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/cli/provider.py
from __future__ import annotations
import json
import os
import stat
from pathlib import Path

def _byok_root() -> Path:
    root = Path(os.environ.get("USERPROFILE") or os.environ["HOME"]) / ".vedix" / "byok"
    (root / "secrets").mkdir(parents=True, exist_ok=True)
    return root

def _providers_json_path() -> Path:
    return _byok_root() / "providers.json"

def _load_config() -> dict:
    p = _providers_json_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"providers": [], "chain": [], "per_agent_class": {}}

def _save_config(cfg: dict) -> None:
    p = _providers_json_path()
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def _save_secret(name: str, secret: str) -> Path:
    p = _byok_root() / "secrets" / f"{name}.key"
    p.write_text(secret, encoding="utf-8")
    if os.name != "nt":
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return p

def add_provider(name: str, *, api_key: str, confirm: bool = True, **kwargs) -> None:
    cfg = _load_config()
    if any(p["name"] == name for p in cfg["providers"]):
        if confirm:
            resp = input(f"provider {name} already exists. Overwrite? [y/N]: ")
            if resp.strip().lower() != "y":
                return
        cfg["providers"] = [p for p in cfg["providers"] if p["name"] != name]
    _save_secret(name, api_key)
    entry = {"name": name, "added_at": __import__("time").time(), **kwargs}
    cfg["providers"].append(entry)
    if not cfg["chain"]:
        cfg["chain"] = [name]
    _save_config(cfg)
    print(f"[provider add] {name} configured")

def list_providers() -> list[dict]:
    return _load_config()["providers"]

def remove_provider(name: str, *, confirm: bool = True) -> None:
    cfg = _load_config()
    if confirm:
        resp = input(f"remove {name}? [y/N]: ")
        if resp.strip().lower() != "y":
            return
    cfg["providers"] = [p for p in cfg["providers"] if p["name"] != name]
    cfg["chain"] = [n for n in cfg["chain"] if n != name]
    _save_config(cfg)
    secret = _byok_root() / "secrets" / f"{name}.key"
    if secret.exists():
        secret.unlink()
    print(f"[provider remove] {name} removed")

def set_chain(names: list[str]) -> None:
    cfg = _load_config()
    known = {p["name"] for p in cfg["providers"]}
    unknown = set(names) - known
    if unknown:
        raise ValueError(f"unknown providers: {unknown}")
    cfg["chain"] = names
    _save_config(cfg)
    print(f"[provider chain] {' → '.join(names)}")

async def test_provider(name: str) -> bool:
    """Send a tiny prompt to the named provider; return True if successful."""
    from ..base import ChatRequest, Message
    from .. import factory
    adapter = factory.build_adapter(name)
    try:
        await adapter.chat(ChatRequest(messages=[Message(role="user", content="hi")], model=factory.default_model(name), max_tokens=10))
        print(f"[provider test] {name} OK")
        return True
    except Exception as e:
        print(f"[provider test] {name} FAIL: {e}")
        return False
```

- [ ] **Step 4: Run — verify it passes**

```
pytest tests/byok/test_provider_cli.py -v
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/cli/provider.py tests/byok/test_provider_cli.py
git commit -m "feat(B2): vedix provider {add,list,remove,set-chain,test} CLI subcommands"
```

## Task 11: Wire router into existing dispatch layer

**Files:**
- Modify: `plugins/vedix/mcp/lib/orchestrator/dispatch/__init__.py` (route through ProviderRouter)
- Modify: `plugins/vedix/mcp/lib/orchestrator/pipeline.py` (initialize router from config at boot)
- Test: `tests/byok/test_dispatch_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/byok/test_dispatch_integration.py
import pytest
from unittest.mock import patch
from plugins.vedix.mcp.lib.orchestrator.dispatch import dispatch_agent
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatResponse

@pytest.mark.asyncio
async def test_dispatch_routes_through_router(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Add an anthropic provider
    from plugins.vedix.mcp.lib.orchestrator.byok.cli.provider import add_provider
    add_provider("anthropic", api_key="sk-test", confirm=False)

    fake_response = ChatResponse(content="hi", model="claude", finish_reason="stop", input_tokens=1, output_tokens=1)
    with patch("plugins.vedix.mcp.lib.orchestrator.byok.adapters.anthropic_adapter.AnthropicAdapter.chat", return_value=fake_response):
        result = await dispatch_agent(agent_type="ideator", prompt="hi")
        assert result.content == "hi"
```

- [ ] **Step 2: Implement factory**

```python
# plugins/vedix/mcp/lib/orchestrator/byok/factory.py
from __future__ import annotations
import json
from pathlib import Path
from .router import ProviderRouter
from .cost_ledger import CostLedger
from .cli.provider import _byok_root
from .adapters.anthropic_adapter import AnthropicAdapter
from .adapters.openai_adapter import OpenAIAdapter
from .adapters.google_adapter import GoogleAdapter
from .adapters.openrouter_adapter import OpenRouterAdapter
from .adapters.together_adapter import TogetherAdapter
from .adapters.deepseek_adapter import DeepSeekAdapter
from .adapters.qwen_adapter import QwenAdapter
from .adapters.moonshot_adapter import MoonshotAdapter
from .adapters.zhipu_adapter import ZhipuAdapter
from .adapters.gigachat_adapter import GigaChatAdapter
from .adapters.yandexgpt_adapter import YandexGPTAdapter
from .adapters.mistral_adapter import MistralAdapter
from .adapters.cohere_adapter import CohereAdapter
from .adapters.local_adapter import LocalAdapter

_ADAPTERS = {
    "anthropic": AnthropicAdapter, "openai": OpenAIAdapter, "google": GoogleAdapter,
    "openrouter": OpenRouterAdapter, "together": TogetherAdapter,
    "deepseek": DeepSeekAdapter, "qwen": QwenAdapter, "moonshot": MoonshotAdapter, "zhipu": ZhipuAdapter,
    "gigachat": GigaChatAdapter, "yandexgpt": YandexGPTAdapter,
    "mistral": MistralAdapter, "cohere": CohereAdapter, "local": LocalAdapter,
}

DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-20250514",
    "openai": "gpt-5",
    "google": "gemini-2.5-pro",
    "openrouter": "anthropic/claude-opus-4",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-max",
    "moonshot": "moonshot-v1-128k",
    "zhipu": "glm-4-plus",
    "gigachat": "GigaChat-Pro",
    "yandexgpt": "yandexgpt",
    "mistral": "mistral-large-latest",
    "cohere": "command-r-plus",
    "local": "llama3",
}

def default_model(name: str) -> str:
    return DEFAULT_MODELS.get(name, "default")

def _load_secret(name: str) -> str:
    return (_byok_root() / "secrets" / f"{name}.key").read_text(encoding="utf-8").strip()

def build_adapter(name: str, **extra):
    cls = _ADAPTERS[name]
    secret = _load_secret(name)
    if name in ("gigachat",):
        return cls(credentials=secret, **extra)
    if name in ("yandexgpt",):
        folder = json.loads((_byok_root() / "providers.json").read_text())
        folder_id = next((p["folder_id"] for p in folder["providers"] if p["name"] == name), "")
        return cls(api_key=secret, folder_id=folder_id)
    if name == "local":
        cfg = json.loads((_byok_root() / "providers.json").read_text())
        base_url = next((p.get("base_url") for p in cfg["providers"] if p["name"] == name), "http://localhost:8000/v1")
        return cls(api_key=secret, base_url=base_url, **extra)
    return cls(api_key=secret)

def build_router() -> ProviderRouter:
    cfg = json.loads((_byok_root() / "providers.json").read_text())
    chain = [build_adapter(name) for name in cfg.get("chain", [])]
    per_agent = {k: [build_adapter(n) for n in v] for k, v in cfg.get("per_agent_class", {}).items()}
    return ProviderRouter(chain=chain, per_agent_class=per_agent, cost_ledger=CostLedger())
```

- [ ] **Step 3: Wire into dispatch**

```python
# plugins/vedix/mcp/lib/orchestrator/dispatch/__init__.py
# (modify existing module to expose dispatch_agent that uses the router)
from ..byok import factory as _byok_factory
from ..byok.base import ChatRequest, Message

_router = None

def _get_router():
    global _router
    if _router is None:
        _router = _byok_factory.build_router()
    return _router

async def dispatch_agent(*, agent_type: str, prompt: str, system: str | None = None, model: str | None = None, max_tokens: int = 4096):
    msgs = []
    if system:
        msgs.append(Message(role="system", content=system))
    msgs.append(Message(role="user", content=prompt))
    chain_first_provider = _byok_factory._ADAPTERS  # for reference
    # Default model resolution: use the first provider's default model
    if not model:
        cfg = __import__("json").loads((_byok_factory._byok_root() / "providers.json").read_text())
        first = cfg["chain"][0] if cfg["chain"] else "anthropic"
        model = _byok_factory.default_model(first)
    req = ChatRequest(messages=msgs, model=model, max_tokens=max_tokens)
    router = _get_router()
    return await router.chat(req, agent_class=agent_type)
```

- [ ] **Step 4: Run integration test**

```
pytest tests/byok/test_dispatch_integration.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/byok/factory.py plugins/vedix/mcp/lib/orchestrator/dispatch/__init__.py tests/byok/test_dispatch_integration.py
git commit -m "feat(B2): wire ProviderRouter into orchestrator dispatch layer; add factory"
```

## Block 2 acceptance criteria

- [ ] All 14 adapter tests pass
- [ ] Router fallback works (test: kill the first adapter via mock, observe fallback)
- [ ] `vedix provider add anthropic` → `~/.vedix/byok/providers.json` + `~/.vedix/byok/secrets/anthropic.key` exist (with `chmod 600` on Unix)
- [ ] `vedix provider test anthropic` returns OK with a real key in env
- [ ] Cost ledger appends one JSON line per dispatch
- [ ] Capability filtering kicks in: a tool-using agent skipped past `together` (no tools) to `anthropic`
- [ ] Existing v2.1.x pipeline tests still pass after dispatch refactor
- [ ] Documented in `docs/byok/providers.md`
- [ ] Git tag `v3.0.0-block2` pushed

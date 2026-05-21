import pytest
from unittest.mock import AsyncMock, MagicMock

from plugins.vedix.mcp.lib.orchestrator.byok.base import (
    ChatRequest,
    ChatResponse,
    Message,
    ProviderCapabilities,
)
from plugins.vedix.mcp.lib.orchestrator.byok.exceptions import ProviderUnavailable, RateLimited
from plugins.vedix.mcp.lib.orchestrator.byok.router import ProviderRouter


def _make_adapter(name, region="global", chat_fn=None):
    a = MagicMock()
    a.name = name
    a.capabilities.return_value = ProviderCapabilities(
        name=name,
        region=region,
        max_context=100_000,
        supports_tools=True,
        supports_streaming=True,
        supports_structured_output=True,
    )
    a.chat = chat_fn if chat_fn else AsyncMock(
        return_value=ChatResponse(
            content="ok", model="m", finish_reason="stop", input_tokens=1, output_tokens=1
        )
    )
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
    router = ProviderRouter(
        chain=[primary], per_agent_class={"register-discriminator": [cheap]}
    )
    await router.chat(
        ChatRequest(messages=[Message(role="user", content="x")], model="m"),
        agent_class="register-discriminator",
    )
    cheap.chat.assert_called_once()
    primary.chat.assert_not_called()

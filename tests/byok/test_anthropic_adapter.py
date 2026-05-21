import pytest

anthropic = pytest.importorskip("anthropic")

from unittest.mock import AsyncMock, patch  # noqa: E402

from plugins.vedix.mcp.lib.orchestrator.byok.adapters.anthropic_adapter import (  # noqa: E402
    AnthropicAdapter,
)
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message  # noqa: E402
from plugins.vedix.mcp.lib.orchestrator.byok.exceptions import RateLimited  # noqa: E402


@pytest.mark.asyncio
async def test_chat_returns_response():
    adapter = AnthropicAdapter(api_key="sk-test")
    with patch.object(adapter._client.messages, "create", new=AsyncMock()) as m:
        m.return_value.content = [type("C", (), {"text": "hi back", "type": "text"})()]
        m.return_value.model = "claude-opus-4-20250514"
        m.return_value.stop_reason = "end_turn"
        m.return_value.usage = type("U", (), {"input_tokens": 5, "output_tokens": 3})()
        resp = await adapter.chat(
            ChatRequest(messages=[Message(role="user", content="hi")], model="claude-opus-4")
        )
        assert resp.content == "hi back"
        assert resp.input_tokens == 5


@pytest.mark.asyncio
async def test_chat_raises_RateLimited_on_429():
    adapter = AnthropicAdapter(api_key="sk-test")
    rl_exc = anthropic.RateLimitError(
        "rate limit",
        response=type("R", (), {"headers": {}})(),
        body={},
    )
    with patch.object(adapter._client.messages, "create", side_effect=rl_exc):
        with pytest.raises(RateLimited):
            await adapter.chat(
                ChatRequest(messages=[Message(role="user", content="hi")], model="claude-opus-4")
            )


def test_capabilities():
    adapter = AnthropicAdapter(api_key="sk-test")
    caps = adapter.capabilities()
    assert caps.name == "anthropic"
    assert caps.region == "global"
    assert caps.supports_tools is True
    assert caps.max_context >= 200_000

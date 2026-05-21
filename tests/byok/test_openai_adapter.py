import pytest

pytest.importorskip("openai")

from unittest.mock import AsyncMock, patch  # noqa: E402

from plugins.vedix.mcp.lib.orchestrator.byok.adapters.openai_adapter import (  # noqa: E402
    OpenAIAdapter,
)
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message  # noqa: E402


@pytest.mark.asyncio
async def test_openai_chat():
    adapter = OpenAIAdapter(api_key="sk-test")
    with patch.object(adapter._client.chat.completions, "create", new=AsyncMock()) as m:
        m.return_value.choices = [
            type(
                "C",
                (),
                {
                    "message": type("M", (), {"content": "ok", "tool_calls": None})(),
                    "finish_reason": "stop",
                },
            )()
        ]
        m.return_value.model = "gpt-5"
        m.return_value.usage = type("U", (), {"prompt_tokens": 5, "completion_tokens": 2})()
        resp = await adapter.chat(
            ChatRequest(messages=[Message(role="user", content="hi")], model="gpt-5")
        )
        assert resp.content == "ok"


def test_openai_capabilities():
    adapter = OpenAIAdapter(api_key="sk-test")
    caps = adapter.capabilities()
    assert caps.name == "openai"
    assert caps.region == "global"
    assert caps.max_context >= 128_000

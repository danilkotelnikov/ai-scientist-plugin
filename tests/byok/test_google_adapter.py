import pytest

pytest.importorskip("google.generativeai")

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from plugins.vedix.mcp.lib.orchestrator.byok.adapters.google_adapter import (  # noqa: E402
    GoogleAdapter,
)
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message  # noqa: E402


@pytest.mark.asyncio
async def test_google_chat():
    adapter = GoogleAdapter(api_key="ai-test")
    fake_response = MagicMock(
        text="hi",
        candidates=[MagicMock(finish_reason="STOP")],
        usage_metadata=MagicMock(prompt_token_count=5, candidates_token_count=2),
    )
    with patch("google.generativeai.GenerativeModel") as MM:
        MM.return_value.generate_content_async = AsyncMock(return_value=fake_response)
        resp = await adapter.chat(
            ChatRequest(messages=[Message(role="user", content="hi")], model="gemini-2.5-pro")
        )
        assert resp.content == "hi"


def test_google_capabilities():
    adapter = GoogleAdapter(api_key="ai-test")
    caps = adapter.capabilities()
    assert caps.name == "google"
    assert caps.region == "global"
    assert caps.max_context >= 1_000_000

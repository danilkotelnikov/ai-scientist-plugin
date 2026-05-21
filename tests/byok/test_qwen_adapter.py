import pytest

pytest.importorskip("dashscope")

from unittest.mock import MagicMock, patch  # noqa: E402

from plugins.vedix.mcp.lib.orchestrator.byok.adapters.qwen_adapter import QwenAdapter  # noqa: E402
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message  # noqa: E402


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
        resp = await adapter.chat(
            ChatRequest(messages=[Message(role="user", content="hi")], model="qwen-max")
        )
        assert resp.content == "ok"


def test_qwen_capabilities():
    adapter = QwenAdapter(api_key="sk-test")
    caps = adapter.capabilities()
    assert caps.name == "qwen"
    assert caps.region == "cn"
    assert caps.max_context >= 32_000

import pytest

pytest.importorskip("httpx")

from unittest.mock import MagicMock, patch  # noqa: E402

from plugins.vedix.mcp.lib.orchestrator.byok.adapters.yandexgpt_adapter import (  # noqa: E402
    YandexGPTAdapter,
)
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message  # noqa: E402


@pytest.mark.asyncio
async def test_yandexgpt_chat():
    adapter = YandexGPTAdapter(api_key="AQVNxxx", folder_id="b1g000000000000000000")
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "result": {
            "alternatives": [
                {
                    "message": {"text": "привет", "role": "assistant"},
                    "status": "ALTERNATIVE_STATUS_FINAL",
                }
            ],
            "usage": {
                "inputTextTokens": "5",
                "completionTokens": "3",
                "totalTokens": "8",
            },
            "modelVersion": "yandexgpt:lite",
        }
    }
    fake_response.status_code = 200

    async def fake_post(*args, **kwargs):
        return fake_response

    with patch("httpx.AsyncClient.post", new=fake_post):
        resp = await adapter.chat(
            ChatRequest(
                messages=[Message(role="user", content="привет")],
                model="yandexgpt-lite",
            )
        )
        assert resp.content == "привет"


def test_yandexgpt_capabilities():
    adapter = YandexGPTAdapter(api_key="t", folder_id="b1g")
    caps = adapter.capabilities()
    assert caps.region == "ru"
    assert caps.name == "yandexgpt"

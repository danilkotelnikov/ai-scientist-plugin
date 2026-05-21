import pytest

pytest.importorskip("gigachat")

from unittest.mock import MagicMock, patch  # noqa: E402

from plugins.vedix.mcp.lib.orchestrator.byok.adapters.gigachat_adapter import (  # noqa: E402
    GigaChatAdapter,
)
from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatRequest, Message  # noqa: E402


@pytest.mark.asyncio
async def test_gigachat_chat(tmp_path):
    cert = tmp_path / "russian_trusted_root_ca.crt"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIfake\n-----END CERTIFICATE-----")
    adapter = GigaChatAdapter(
        credentials="Y2xpZW50OnNlY3JldA==",
        scope="GIGACHAT_API_PERS",
        verify_cert=str(cert),
    )

    fake_chat_response = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(content="привет"),
                finish_reason="stop",
            )
        ],
        usage=MagicMock(prompt_tokens=5, completion_tokens=3),
        model="GigaChat-Pro",
    )
    with patch.object(adapter._client, "chat", return_value=fake_chat_response):
        resp = await adapter.chat(
            ChatRequest(
                messages=[Message(role="user", content="привет")],
                model="GigaChat-Pro",
            )
        )
        assert resp.content == "привет"


def test_gigachat_capabilities(tmp_path):
    cert = tmp_path / "ca.crt"
    cert.write_text("dummy")
    adapter = GigaChatAdapter(credentials="dGVzdA==", verify_cert=str(cert))
    caps = adapter.capabilities()
    assert caps.name == "gigachat"
    assert caps.region == "ru"

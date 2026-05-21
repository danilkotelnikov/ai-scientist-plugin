import pytest

# The factory builds adapters by name, importing each provider's SDK lazily
# inside the adapter module. For this integration test we only need anthropic
# (mocked at the .chat seam), so the test skips when anthropic isn't available.
pytest.importorskip("anthropic")

from unittest.mock import patch  # noqa: E402

from plugins.vedix.mcp.lib.orchestrator.byok.base import ChatResponse  # noqa: E402


@pytest.mark.asyncio
async def test_dispatch_routes_through_router(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    # Reset the cached router so it picks up our env-redirected secrets dir.
    import plugins.vedix.mcp.lib.orchestrator.dispatch as dispatch_pkg

    dispatch_pkg._router = None

    from plugins.vedix.mcp.lib.orchestrator.byok.cli.provider import add_provider

    add_provider("anthropic", api_key="sk-test", confirm=False)

    fake_response = ChatResponse(
        content="hi", model="claude", finish_reason="stop", input_tokens=1, output_tokens=1
    )

    async def _fake_chat(self, req):  # noqa: ARG001
        return fake_response

    with patch(
        "plugins.vedix.mcp.lib.orchestrator.byok.adapters.anthropic_adapter.AnthropicAdapter.chat",
        new=_fake_chat,
    ):
        result = await dispatch_pkg.dispatch_agent(agent_type="ideator", prompt="hi")
        assert result.content == "hi"

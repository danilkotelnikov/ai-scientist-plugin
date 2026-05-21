import pytest


def test_mistral_capabilities():
    pytest.importorskip("mistralai")
    from plugins.vedix.mcp.lib.orchestrator.byok.adapters.mistral_adapter import MistralAdapter

    a = MistralAdapter(api_key="t")
    caps = a.capabilities()
    assert caps.name == "mistral"
    assert caps.region == "eu"


def test_cohere_capabilities():
    pytest.importorskip("cohere")
    from plugins.vedix.mcp.lib.orchestrator.byok.adapters.cohere_adapter import CohereAdapter

    a = CohereAdapter(api_key="t")
    caps = a.capabilities()
    assert caps.name == "cohere"
    assert caps.region == "global"

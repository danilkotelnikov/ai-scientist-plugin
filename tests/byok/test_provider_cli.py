import json

from plugins.vedix.mcp.lib.orchestrator.byok.cli.provider import (
    add_provider,
    list_providers,
    remove_provider,
    set_chain,
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

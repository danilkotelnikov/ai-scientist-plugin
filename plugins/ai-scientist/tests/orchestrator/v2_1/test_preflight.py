# tests/orchestrator/v2_1/test_preflight.py
from unittest.mock import patch
from mcp.lib.orchestrator.preflight import (
    probe_toolchain, probe_codex_runtime, probe_memory_tools,
)


def test_toolchain_probe_returns_struct():
    with patch("mcp.lib.orchestrator.preflight._which",
               side_effect=lambda x: f"/usr/bin/{x}" if x == "tectonic" else None):
        out = probe_toolchain()
    assert out["latex"]["tectonic"] is True
    assert out["latex"]["pdflatex"] is False
    assert "word_export" in out
    assert "visual_validation" in out


def test_codex_runtime_probe_returns_capabilities():
    fake_caps = {"spawn_agent": True, "wait": True, "close_agent": True,
                 "max_threads": 6}
    out = probe_codex_runtime(host="codex", available_tools=fake_caps)
    assert out["host"] == "codex"
    assert out["spawn_agent_available"] is True
    assert out["max_threads"] == 6
    assert out["fallback"] is None


def test_codex_runtime_probe_falls_back_when_unavailable():
    out = probe_codex_runtime(host="codex", available_tools={})
    assert out["spawn_agent_available"] is False
    assert out["fallback"] == "inline_phase_templates"


def test_memory_probe_lists_expected_vs_available():
    out = probe_memory_tools(
        expected=["mempalace_add_drawer", "mempalace_diary_write"],
        available=["mempalace_add_drawer"],
    )
    assert out["mempalace_expected"] == ["mempalace_add_drawer", "mempalace_diary_write"]
    assert out["mempalace_available"] == ["mempalace_add_drawer"]
    assert "mempalace_diary_write" in out["missing"]

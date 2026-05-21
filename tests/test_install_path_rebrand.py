# tests/test_install_path_rebrand.py
"""Verify B1 Task 5: bootstrap + Codex config + Gemini config all point at vedix.

Allows legacy `ai-scientist` references only in the v2 migration-detection
block (where the old name is required to recognize a v2.x install on disk).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_uses_vedix_paths() -> None:
    for fname in ("scripts/bootstrap.ps1", "scripts/bootstrap.sh"):
        content = (ROOT / fname).read_text(encoding="utf-8")
        assert ".vedix" in content, f"{fname} must reference ~/.vedix/"
        # Any surviving `ai-scientist` mentions must be the v2-detection block,
        # which intentionally keeps the old name so the migration helper can
        # spot a pre-existing v2.x install.
        if "ai-scientist" in content:
            assert "migrate" in content, (
                f"{fname} mentions ai-scientist outside the migration context"
            )


def test_codex_config_uses_vedix_key() -> None:
    content = (
        ROOT / "plugins" / "vedix" / "codex-config.toml.example"
    ).read_text(encoding="utf-8")
    assert "[mcp_servers.vedix]" in content
    assert "[mcp_servers.ai-scientist]" not in content


def test_codex_config_uses_vedix_home_var() -> None:
    content = (
        ROOT / "plugins" / "vedix" / "codex-config.toml.example"
    ).read_text(encoding="utf-8")
    assert "VEDIX_HOME" in content
    assert "AI_SCIENTIST_HOME" not in content

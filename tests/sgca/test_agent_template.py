from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.dispatch import AGENT_CLASS_DEFAULTS


def test_paper_extractor_template_exists_and_has_frontmatter():
    p = Path("plugins/vedix/agents/paper-extractor.md")
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "name: paper-extractor" in content
    assert "agent_class: paper-extractor" in content


def test_agent_class_defaults_registers_sgca_classes():
    for cls in ("paper-extractor", "claim-verifier", "paragraph-planner", "lattice-merger"):
        assert cls in AGENT_CLASS_DEFAULTS
    pe = AGENT_CLASS_DEFAULTS["paper-extractor"]
    assert "deepseek" in pe["preferred_providers"]
    assert pe["max_tokens"] == 8192

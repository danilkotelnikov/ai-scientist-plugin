from mcp.lib.orchestrator.findings import FindingsScaffold, FINDINGS_SECTIONS


def test_default_scaffold_has_5_sections():
    s = FindingsScaffold()
    for section in FINDINGS_SECTIONS:
        assert section in s.to_dict()


def test_update_section():
    s = FindingsScaffold()
    s.update("lessons_and_constraints", "weight decay > 0.1 diverges at this scale")
    assert "weight decay" in s.to_dict()["lessons_and_constraints"]


def test_append_to_section():
    s = FindingsScaffold()
    s.append("patterns_and_insights", "first pattern")
    s.append("patterns_and_insights", "second pattern")
    text = s.to_dict()["patterns_and_insights"]
    assert "first pattern" in text and "second pattern" in text


def test_to_markdown_renders_all_sections():
    s = FindingsScaffold()
    s.update("current_understanding", "We know X.")
    md = s.to_markdown()
    assert "# Findings" in md
    assert "## Current Understanding" in md
    assert "We know X." in md


def test_unknown_section_raises():
    s = FindingsScaffold()
    import pytest
    with pytest.raises(KeyError):
        s.update("not_a_section", "x")

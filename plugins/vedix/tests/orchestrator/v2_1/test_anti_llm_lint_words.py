# tests/orchestrator/v2_1/test_anti_llm_lint_words.py
from mcp.lib.orchestrator.anti_llm_lint import (
    lint_text, TIER1_BLACKLIST, TIER2_BLACKLIST,
)


def test_tier1_includes_empirical_words():
    assert "delve" in TIER1_BLACKLIST
    assert "delves" in TIER1_BLACKLIST
    assert "underscores" in TIER1_BLACKLIST
    assert "showcasing" in TIER1_BLACKLIST
    assert "meticulous" in TIER1_BLACKLIST
    assert "intricate" in TIER1_BLACKLIST
    assert "commendable" in TIER1_BLACKLIST


def test_lint_flags_tier1_immediately():
    text = "We delve into the intricate details of attention."
    out = lint_text(text)
    assert any(h["tier"] == 1 and h["term"] == "delve" for h in out["hits"])
    assert any(h["tier"] == 1 and h["term"] == "intricate" for h in out["hits"])


def test_lint_warns_on_tier2_only_above_threshold():
    text_one = "The robust method is described."  # 1 occurrence
    text_three = "The robust method has a robust pipeline and robust output."
    out_one = lint_text(text_one)
    out_three = lint_text(text_three)
    # Tier 2 has a section-level threshold of 2
    assert sum(1 for h in out_one["hits"] if h["tier"] == 2) == 0  # under threshold → no flag
    assert sum(1 for h in out_three["hits"] if h["tier"] == 2) >= 1  # over threshold → flag


def test_disciplinary_exemption_for_robust_regression():
    text = "We use robust regression to handle outliers."
    out = lint_text(text)
    assert all(h["term"] != "robust" for h in out["hits"])  # exempted


def test_blocks_tier3_phrase_patterns():
    text = "It is important to note that the method works."
    out = lint_text(text)
    assert any(h["tier"] == 3 for h in out["hits"])


def test_paragraph_initial_transitions_flagged():
    text = "First paragraph here.\n\nFurthermore, the second paragraph adds context."
    out = lint_text(text)
    assert any(h["tier"] == 3 and "Furthermore" in h["match"] for h in out["hits"])

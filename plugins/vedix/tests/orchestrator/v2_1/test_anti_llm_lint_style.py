# tests/orchestrator/v2_1/test_anti_llm_lint_style.py
from mcp.lib.orchestrator.anti_llm_lint import lint_text


def test_em_dash_overuse_warned():
    text = " ".join(["word"] * 100) + " — em dash"
    # 1 em dash in 101 words ≈ 9.9 / 1000
    out = lint_text(text)
    assert any(h.get("metric") == "em_dash_density" and h["tier"] == 4
               for h in out["hits"])


def test_em_dash_below_threshold_no_flag():
    text = " ".join(["word"] * 1000) + " — only one"
    out = lint_text(text)
    assert all(h.get("metric") != "em_dash_density"
               for h in out["hits"])  # 1/1001 ≈ 1/1000, under 2 threshold


def test_tricolon_evaluative_adjectives_flagged():
    text = "Our method is robust, scalable, and efficient."
    out = lint_text(text)
    assert any(h.get("metric") == "evaluative_tricolon" for h in out["hits"])


def test_participial_commentary_flagged():
    text = "The accuracy improved by 15%, highlighting the importance of pretraining."
    out = lint_text(text)
    assert any(h.get("metric") == "participial_commentary" for h in out["hits"])

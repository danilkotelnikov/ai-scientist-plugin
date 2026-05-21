import pytest
from plugins.vedix.mcp.lib.orchestrator.sgca.importance import (
    compute_importance, top_headline_claims,
)


def test_compute_importance_uses_formula():
    score = compute_importance(
        mentions_in_manuscript=5,
        downstream_anchor_count=3,
        appears_in_abstract=True,
        appears_in_conclusion=True,
    )
    # 0.4*5 + 0.3*3 + 0.2*1 + 0.1*1 = 2.0 + 0.9 + 0.2 + 0.1 = 3.2
    assert score == pytest.approx(3.2)


def test_top_headline_claims_returns_n_by_score():
    candidates = {
        "c1": {"mentions": 1, "downstream": 0, "in_abstract": False, "in_conclusion": False},
        "c2": {"mentions": 5, "downstream": 4, "in_abstract": True,  "in_conclusion": True},
        "c3": {"mentions": 3, "downstream": 1, "in_abstract": True,  "in_conclusion": False},
        "c4": {"mentions": 2, "downstream": 2, "in_abstract": False, "in_conclusion": True},
    }
    top = top_headline_claims(candidates, n=2)
    assert top == ["c2", "c3"]

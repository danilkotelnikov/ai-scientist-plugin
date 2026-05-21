# tests/orchestrator/v2_1/test_cross_validator_stage3.py
from mcp.lib.orchestrator.cross_validator import stage3_claim_support


def test_skips_below_citation_threshold():
    paper = {"doi": "10.1/x", "citation_count_in_ms": 1}
    out = stage3_claim_support(paper, claim="anything", min_citations=3)
    assert out["checked"] is False
    assert out["reason"] == "below_threshold"


def test_uses_tldr_when_present():
    paper = {"doi": "10.1/x", "citation_count_in_ms": 5,
             "s2_tldr": "We propose a fast antibody design method."}
    out = stage3_claim_support(paper,
        claim="propose fast antibody design", min_citations=3)
    assert out["checked"] is True
    assert out["method"] == "s2_tldr"
    assert out["match_score"] >= 50
    assert out["flag"] is False


def test_flags_low_match():
    paper = {"doi": "10.1/x", "citation_count_in_ms": 5,
             "s2_tldr": "We propose a method for cell biology."}
    out = stage3_claim_support(paper,
        claim="quantum gravity in black holes", min_citations=3)
    assert out["flag"] is True


def test_falls_back_to_abstract_when_no_tldr():
    paper = {"doi": "10.1/x", "citation_count_in_ms": 5,
             "abstract": "We measure protein binding affinity using SPR."}
    out = stage3_claim_support(paper,
        claim="measure protein binding", min_citations=3)
    assert out["checked"] is True
    assert out["method"] == "abstract_snippet"

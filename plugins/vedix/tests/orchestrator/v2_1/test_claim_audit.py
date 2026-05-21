# tests/orchestrator/v2_1/test_claim_audit.py
from mcp.lib.orchestrator.anti_llm_lint import audit_claims


def test_outperforms_without_quantification_flagged():
    text = "Our model outperforms existing approaches."
    out = audit_claims(text)
    assert any(c["pattern"] == "outperforms" for c in out["clarification_requests"])


def test_outperforms_with_pvalue_not_flagged():
    text = "Our model outperforms ResNet-50 (accuracy 88.4% vs 81.2%, p < 0.001, n=5)."
    out = audit_claims(text)
    assert not any(c["pattern"] == "outperforms"
                   for c in out["clarification_requests"])


def test_novel_without_prior_work_flagged():
    text = "We propose a novel architecture for image recognition."
    out = audit_claims(text)
    assert any(c["pattern"] == "novel" for c in out["clarification_requests"])


def test_novel_with_prior_work_survey_not_flagged():
    text = "We propose a novel architecture; to our knowledge, no prior work has applied X to Y (see Appendix A search protocol)."
    out = audit_claims(text)
    assert not any(c["pattern"] == "novel"
                   for c in out["clarification_requests"])


def test_robust_without_evaluation_flagged():
    text = "The system is robust to noise."
    out = audit_claims(text)
    assert any(c["pattern"] == "robust" for c in out["clarification_requests"])


def test_significant_without_test_stat_flagged():
    text = "The improvement is significant."
    out = audit_claims(text)
    assert any(c["pattern"] == "significant" for c in out["clarification_requests"])

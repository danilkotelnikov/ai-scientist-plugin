# tests/orchestrator/v2_1/test_article_type.py
from mcp.lib.orchestrator.article_type import (
    classify_article_type, phase_order_for, NON_APPLICABLE_PHASES,
)


def test_explicit_flag_wins():
    a = classify_article_type(topic="ridge regression",
                              explicit="experimental")
    assert a == "experimental"


def test_review_keywords_detected():
    for topic in ["recent advances in transformers",
                  "review of antibody design",
                  "literature review of attention mechanisms",
                  "state of the art of cell biology",
                  "survey of large language models"]:
        assert classify_article_type(topic=topic, explicit="auto") == "review"


def test_benchmark_keywords_detected():
    for topic in ["benchmark of LLMs on code",
                  "evaluation suite for video models",
                  "leaderboard of MoE architectures"]:
        assert classify_article_type(topic=topic, explicit="auto") == "benchmark"


def test_default_is_experimental():
    a = classify_article_type(topic="ridge regression on synthetic data",
                              explicit="auto")
    assert a == "experimental"


def test_review_phase_order():
    order = phase_order_for("review")
    assert "1.5" in order
    assert "6R" in order
    assert "7R" in order
    assert "0.75" not in order
    assert "3" not in order
    assert "4" not in order
    assert "5.5" not in order


def test_experimental_phase_order():
    order = phase_order_for("experimental")
    assert "3" in order
    assert "4" in order
    assert "5.5" in order
    assert "1.5" not in order


def test_non_applicable_for_review():
    napps = NON_APPLICABLE_PHASES["review"]
    assert "0.75" in napps
    assert "3" in napps
    assert "4" in napps
    assert "5.5" in napps

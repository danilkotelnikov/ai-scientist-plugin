import pytest
from unittest.mock import MagicMock
from mcp.lib.orchestrator.ensemble import BiasedReviewers, ReviewAggregate


def test_aggregate_median_score():
    fake_dispatcher = MagicMock(side_effect=[
        {"Overall": 4, "Decision": "Reject"},
        {"Overall": 7, "Decision": "Accept"},
        {"Overall": 6, "Decision": "Accept"},
    ])
    br = BiasedReviewers(dispatcher=fake_dispatcher, biases=["positive", "negative", "neutral"])
    agg = br.review(manuscript="...")
    assert agg.median_overall == 6
    assert agg.consensus_high is True


def test_outlier_flag_when_disagreement_high():
    fake_dispatcher = MagicMock(side_effect=[
        {"Overall": 9, "Decision": "Accept"},
        {"Overall": 2, "Decision": "Reject"},
        {"Overall": 8, "Decision": "Accept"},
    ])
    br = BiasedReviewers(dispatcher=fake_dispatcher)
    agg = br.review(manuscript="...")
    assert agg.has_outliers is True
    assert agg.score_iqr >= 4


def test_consensus_low_when_all_agree_below_5():
    fake_dispatcher = MagicMock(side_effect=[
        {"Overall": 3}, {"Overall": 4}, {"Overall": 4},
    ])
    br = BiasedReviewers(dispatcher=fake_dispatcher)
    agg = br.review(manuscript="...")
    assert agg.consensus_high is False


def test_dispatcher_called_with_bias_per_review():
    captured = []

    def fake_dispatcher(*, agent_name, inputs):
        captured.append(inputs.get("system_bias"))
        return {"Overall": 5}

    br = BiasedReviewers(dispatcher=fake_dispatcher, biases=["positive", "negative", "neutral"])
    br.review(manuscript="m", agent_name="reviewer")
    assert captured == ["positive", "negative", "neutral"]

# tests/orchestrator/test_tokens.py
import pytest
from mcp.lib.orchestrator.tokens import TokenTracker, PRICING


def test_add_accumulates_per_phase_per_agent():
    t = TokenTracker()
    t.add(phase="ideation", agent="ideator", prompt_tok=100, completion_tok=200)
    t.add(phase="ideation", agent="ideator", prompt_tok=50, completion_tok=80)
    t.add(phase="hypothesis", agent="hypothesizer", prompt_tok=200, completion_tok=400, thinking_tok=300)

    report = t.report()
    assert report["by_phase"]["ideation"]["prompt"] == 150
    assert report["by_phase"]["ideation"]["completion"] == 280
    assert report["by_phase"]["hypothesis"]["thinking"] == 300
    assert report["by_agent"]["ideator"]["prompt"] == 150


def test_total_cost_usd_uses_pricing_table():
    t = TokenTracker(model="opus", pricing=PRICING)
    t.add(phase="ideation", agent="ideator", prompt_tok=1_000_000, completion_tok=1_000_000)
    cost = t.total_cost_usd()
    # Opus pricing: $15/M input, $75/M output → $90 total
    assert cost == pytest.approx(90.0, rel=0.01)


def test_warn_if_over_budget_returns_true_at_80pct():
    t = TokenTracker(model="opus")
    # 1M input tokens = $15
    t.add(phase="ideation", agent="ideator", prompt_tok=1_000_000, completion_tok=0)
    triggered = t.warn_if_over_budget(budget_usd=18.0)  # 15/18 = 83% > 80%
    assert triggered is True


def test_warn_if_over_budget_returns_false_below_threshold():
    t = TokenTracker(model="opus")
    t.add(phase="ideation", agent="ideator", prompt_tok=100_000, completion_tok=0)
    triggered = t.warn_if_over_budget(budget_usd=20.0)
    assert triggered is False


def test_global_tracker_singleton():
    from mcp.lib.orchestrator.tokens import _GLOBAL_TRACKER
    _GLOBAL_TRACKER.reset()
    _GLOBAL_TRACKER.add(phase="x", agent="y", prompt_tok=10, completion_tok=20)
    report = _GLOBAL_TRACKER.report()
    assert report["totals"]["prompt"] == 10

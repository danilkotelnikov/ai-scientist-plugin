# tests/orchestrator/test_decorators.py
import pytest
from unittest.mock import MagicMock, patch
from mcp.lib.orchestrator.decorators import retry_with_backoff, track_tokens, log_phase


class FakeRateLimitError(Exception):
    pass


def test_retry_succeeds_on_2nd_try():
    calls = {"n": 0}

    @retry_with_backoff(max_tries=3, max_time=10, on=(FakeRateLimitError,))
    def f():
        calls["n"] += 1
        if calls["n"] < 2:
            raise FakeRateLimitError("rate limited")
        return "ok"

    assert f() == "ok"
    assert calls["n"] == 2


def test_retry_raises_after_max_tries():
    @retry_with_backoff(max_tries=2, max_time=10, on=(FakeRateLimitError,))
    def f():
        raise FakeRateLimitError("always fails")

    with pytest.raises(FakeRateLimitError):
        f()


def test_retry_does_not_retry_on_unmatched_exception():
    @retry_with_backoff(max_tries=3, max_time=10, on=(FakeRateLimitError,))
    def f():
        raise ValueError("different error")

    with pytest.raises(ValueError):
        f()


def test_track_tokens_calls_tracker():
    from mcp.lib.orchestrator.tokens import _GLOBAL_TRACKER

    _GLOBAL_TRACKER.reset()

    @track_tokens(phase="ideation", agent="ideator")
    def f():
        # Simulate an LLM result with token counts
        return {"prompt_tokens": 100, "completion_tokens": 200, "thinking_tokens": 50}

    f()
    report = _GLOBAL_TRACKER.report()
    assert report["by_phase"]["ideation"]["prompt"] == 100
    assert report["by_phase"]["ideation"]["completion"] == 200
    assert report["by_phase"]["ideation"]["thinking"] == 50


def test_log_phase_logs_start_and_end(caplog):
    @log_phase
    def f(arg):
        return arg * 2

    import logging
    caplog.set_level(logging.INFO)
    result = f(21)
    assert result == 42
    messages = [r.message for r in caplog.records]
    assert any("start: f" in m for m in messages)
    assert any("end: f" in m for m in messages)

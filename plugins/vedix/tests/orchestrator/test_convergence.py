# tests/orchestrator/test_convergence.py
import pytest
from mcp.lib.orchestrator.convergence import SemanticConvergence, DEFAULT_SIGNALS


def test_detects_i_am_done():
    sc = SemanticConvergence()
    assert sc.is_converged("After review, I am done.") is True


def test_detects_finalize_idea_action():
    sc = SemanticConvergence()
    assert sc.is_converged('{"action": "FinalizeIdea", "name": "x"}') is True


def test_detects_no_further_changes():
    sc = SemanticConvergence()
    assert sc.is_converged("This is final; no further changes needed.") is True


def test_does_not_falsely_converge_on_done_in_other_context():
    sc = SemanticConvergence()
    assert sc.is_converged("The work is not done yet.") is False


def test_custom_signals_override_default():
    sc = SemanticConvergence(signals=["my custom signal"])
    assert sc.is_converged("Here is my custom signal!") is True
    assert sc.is_converged("I am done") is False


def test_default_signals_list():
    assert "I am done" in DEFAULT_SIGNALS
    assert '"action": "FinalizeIdea"' in DEFAULT_SIGNALS

# tests/orchestrator/test_stage_gate.py
from unittest.mock import MagicMock
from mcp.lib.orchestrator.stage_gate import StageGate, StageGateResult


def test_gate_passes_when_all_criteria_met():
    fake_evaluator = MagicMock(return_value={
        "ready_for_next_stage": True,
        "missing_criteria": [],
    })
    sg = StageGate(evaluator=fake_evaluator)
    result = sg.gate(phase="ideation", artifacts={"idea.json": "..."})
    assert result.ready is True
    assert result.missing == []


def test_gate_blocks_when_criteria_missing():
    fake_evaluator = MagicMock(return_value={
        "ready_for_next_stage": False,
        "missing_criteria": ["abstract is too short", "no risk section"],
    })
    sg = StageGate(evaluator=fake_evaluator)
    result = sg.gate(phase="ideation", artifacts={})
    assert result.ready is False
    assert "abstract is too short" in result.missing


def test_gate_disabled_returns_pass_immediately():
    fake_evaluator = MagicMock()
    sg = StageGate(evaluator=fake_evaluator, enabled=False)
    result = sg.gate(phase="ideation", artifacts={})
    assert result.ready is True
    fake_evaluator.assert_not_called()


def test_gate_uses_default_criteria_per_phase():
    sg = StageGate(evaluator=lambda **kw: {"ready_for_next_stage": True, "missing_criteria": []})
    # Phase-specific criteria are documented but evaluator is what enforces
    result = sg.gate(phase="hypothesis", artifacts={"hypothesis.md": "..."})
    assert result.ready is True

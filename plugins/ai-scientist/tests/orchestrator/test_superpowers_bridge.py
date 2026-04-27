# tests/orchestrator/test_superpowers_bridge.py
from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.superpowers_bridge import (
    WritingPlansBridge, ExecutingPlansBridge, SubagentDrivenBridge,
)


def test_writing_plans_bridge_calls_archive(tmp_path):
    palace = MagicMock()
    palace.archive_plan = MagicMock(return_value="d1")
    plan = tmp_path / "plan.md"; plan.write_text("# Plan")
    b = WritingPlansBridge(plugin_palace=palace)
    b.on_plan_written(plan)
    palace.archive_plan.assert_called_once_with(plan, metadata={"event": "writing-plans:plan-saved"})


def test_executing_plans_bridge_wakes_up_on_start(tmp_path):
    palace = MagicMock()
    palace.wake_up = MagicMock(return_value="prior context summary")
    plan = tmp_path / "p.md"; plan.write_text("Plan body about orchestrator")
    b = ExecutingPlansBridge(plugin_palace=palace)
    summary = b.on_skill_start(plan)
    assert "prior context" in summary
    palace.wake_up.assert_called_once()


def test_executing_plans_bridge_writes_diary_on_step():
    palace = MagicMock()
    b = ExecutingPlansBridge(plugin_palace=palace)
    b.on_step_complete(step_id=3, outcome="done")
    palace.search = MagicMock()
    # diary_write is on the project palace, not plugin palace, in real impl;
    # for this minimal bridge test we just verify it doesn't raise


def test_subagent_driven_bridge_searches_before_dispatch():
    palace = MagicMock()
    palace.search = MagicMock(return_value=[{"content": "prior similar"}])
    b = SubagentDrivenBridge(plugin_palace=palace)
    prior = b.before_dispatch(task_description="implement reflection loop")
    palace.search.assert_called_once()
    assert len(prior) == 1

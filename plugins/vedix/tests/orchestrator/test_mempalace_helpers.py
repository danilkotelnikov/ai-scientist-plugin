# tests/orchestrator/test_mempalace_helpers.py
from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.mempalace_helpers import PluginPalace, ProjectPalace


def test_plugin_palace_archive_spec_calls_add_drawer(tmp_path):
    fake_mcp = MagicMock()
    fake_mcp.mempalace_add_drawer = MagicMock(return_value={"success": True, "drawer_id": "d1"})
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\nbody")
    p = PluginPalace(root=tmp_path, mcp=fake_mcp, wing="plugin")
    drawer_id = p.archive_spec(spec, metadata={"version": "1.0"})
    fake_mcp.mempalace_add_drawer.assert_called_once()
    call_kwargs = fake_mcp.mempalace_add_drawer.call_args.kwargs
    assert call_kwargs["wing"] == "plugin"
    assert call_kwargs["room"] == "specs"
    assert "# Spec" in call_kwargs["content"]


def test_plugin_palace_archive_plan_uses_plans_room(tmp_path):
    fake_mcp = MagicMock()
    fake_mcp.mempalace_add_drawer = MagicMock(return_value={"success": True, "drawer_id": "d2"})
    plan = tmp_path / "plan.md"; plan.write_text("# Plan\n")
    p = PluginPalace(root=tmp_path, mcp=fake_mcp, wing="plugin")
    p.archive_plan(plan, metadata={})
    assert fake_mcp.mempalace_add_drawer.call_args.kwargs["room"] == "plans"


def test_project_palace_write_diary(tmp_path):
    fake_mcp = MagicMock()
    fake_mcp.mempalace_diary_write = MagicMock(return_value={"success": True})
    pp = ProjectPalace(root=tmp_path, mcp=fake_mcp, wing="project_xyz")
    pp.write_diary(agent="ideator", content="round 1 done", tags=["round:1"])
    fake_mcp.mempalace_diary_write.assert_called_once()


def test_project_palace_write_findings_uses_research_findings_room(tmp_path):
    fake_mcp = MagicMock()
    fake_mcp.mempalace_add_drawer = MagicMock(return_value={"success": True})
    pp = ProjectPalace(root=tmp_path, mcp=fake_mcp, wing="project_xyz")
    pp.write_findings(section="current_understanding", content="X works")
    call = fake_mcp.mempalace_add_drawer.call_args.kwargs
    assert call["room"] == "research-findings"
    assert "current_understanding" in call["content"]

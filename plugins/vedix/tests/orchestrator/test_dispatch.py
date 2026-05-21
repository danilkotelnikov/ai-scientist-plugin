# tests/orchestrator/test_dispatch.py
import pytest
from unittest.mock import MagicMock
from mcp.lib.orchestrator.dispatch import (
    get_dispatcher, ClaudeCodeDispatcher, CodexDispatcher, GeminiDispatcher,
)


def test_get_dispatcher_claude_code():
    d = get_dispatcher("claude_code")
    assert d is ClaudeCodeDispatcher


def test_get_dispatcher_codex():
    assert get_dispatcher("codex") is CodexDispatcher


def test_get_dispatcher_gemini():
    assert get_dispatcher("gemini") is GeminiDispatcher


def test_get_dispatcher_unknown_raises():
    # Note: Task 1's polish fix changed bare KeyError -> ValueError with valid-set hint
    with pytest.raises(ValueError, match="Unknown host"):
        get_dispatcher("unknown")


def test_claude_code_dispatcher_calls_task_tool():
    fake_task_tool = MagicMock(return_value={"status": "done", "payload": {}})
    d = ClaudeCodeDispatcher(task_tool=fake_task_tool)
    d.dispatch(agent_name="ideator", inputs={"topic": "X"})
    fake_task_tool.assert_called_once()
    call = fake_task_tool.call_args
    assert "ai-scientist-ideator" in str(call)


def test_codex_dispatcher_calls_spawn_agent():
    fake_spawn = MagicMock(return_value={"status": "done"})
    d = CodexDispatcher(spawn_agent=fake_spawn)
    d.dispatch(agent_name="reviewer", inputs={"manuscript": "..."})
    fake_spawn.assert_called_once()


def test_gemini_dispatcher_falls_back_to_inline():
    """Gemini lacks Task; pipeline executes the prompt inline.
    The dispatcher just returns the agent_md path for the caller to load."""
    d = GeminiDispatcher()
    result = d.dispatch(agent_name="reviewer", inputs={"x": 1})
    assert result["mode"] == "inline"
    assert "agent_path" in result
    assert "ai-scientist-reviewer" in result["agent_path"] or "reviewer" in result["agent_path"]

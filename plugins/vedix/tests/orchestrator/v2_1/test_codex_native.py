# tests/orchestrator/v2_1/test_codex_native.py
from unittest.mock import MagicMock
from mcp.lib.orchestrator.dispatch.codex_native import CodexNativeDispatcher


def test_dispatch_wave_spawns_for_each_input():
    spawn = MagicMock(side_effect=[
        {"agent_id": "a1"}, {"agent_id": "a2"}, {"agent_id": "a3"},
    ])
    wait = MagicMock(return_value={
        "status": {"a1": {"payload": {"r": 1}},
                   "a2": {"payload": {"r": 2}},
                   "a3": {"payload": {"r": 3}}},
        "timed_out": False,
    })
    close = MagicMock()
    d = CodexNativeDispatcher(spawn_agent=spawn, wait=wait,
                              close_agent=close, max_threads=6)
    out = d.dispatch_wave(
        agent_name="reviewer",
        inputs_list=[{"bias": "positive"}, {"bias": "negative"},
                     {"bias": "neutral"}])
    assert spawn.call_count == 3
    assert wait.call_count == 1
    # Slot-leak guard: close_agent called for EVERY spawned id
    assert close.call_count == 3
    assert out == [{"r": 1}, {"r": 2}, {"r": 3}]


def test_dispatch_wave_caps_at_max_threads():
    spawn = MagicMock(return_value={"agent_id": "a"})
    wait = MagicMock(return_value={"status": {"a": {"payload": {}}},
                                   "timed_out": False})
    close = MagicMock()
    d = CodexNativeDispatcher(spawn_agent=spawn, wait=wait,
                              close_agent=close, max_threads=2)
    inputs = [{"i": i} for i in range(10)]
    d.dispatch_wave(agent_name="worker", inputs_list=inputs)
    assert spawn.call_count == 2  # capped


def test_close_agent_called_even_when_wait_throws():
    spawn = MagicMock(side_effect=[{"agent_id": "a1"}, {"agent_id": "a2"}])
    wait = MagicMock(side_effect=Exception("network blip"))
    close = MagicMock()
    d = CodexNativeDispatcher(spawn_agent=spawn, wait=wait,
                              close_agent=close, max_threads=6)
    try:
        d.dispatch_wave(agent_name="reviewer",
                        inputs_list=[{"i": 1}, {"i": 2}])
    except Exception:
        pass
    # Slot-leak guard fires regardless
    assert close.call_count == 2


def test_single_dispatch_uses_inline_when_spawn_unavailable():
    d = CodexNativeDispatcher(spawn_agent=None, wait=None,
                              close_agent=None, max_threads=6)
    result = d.dispatch(agent_name="ideator", inputs={"topic": "x"})
    assert result["mode"] == "inline_fallback"
    assert "agent_path" in result or "inputs" in result

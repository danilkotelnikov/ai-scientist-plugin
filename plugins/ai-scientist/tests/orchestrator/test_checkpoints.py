# tests/orchestrator/test_checkpoints.py
from pathlib import Path
from mcp.lib.orchestrator.checkpoints import CheckpointManager


def test_save_and_load_round_trip(tmp_path):
    cm = CheckpointManager(checkpoint_dir=tmp_path)
    state = {"phase": "ideation", "candidates": [1, 2, 3], "winner": 2}
    cm.save("phase_0_5", state)
    loaded = cm.load("phase_0_5")
    assert loaded == state


def test_load_returns_none_for_missing(tmp_path):
    cm = CheckpointManager(checkpoint_dir=tmp_path)
    assert cm.load("never_saved") is None


def test_latest_returns_most_recent(tmp_path):
    cm = CheckpointManager(checkpoint_dir=tmp_path)
    cm.save("phase_0", {"a": 1})
    cm.save("phase_1", {"b": 2})
    cm.save("phase_2", {"c": 3})
    assert cm.latest() == "phase_2"


def test_latest_returns_none_for_empty_dir(tmp_path):
    cm = CheckpointManager(checkpoint_dir=tmp_path)
    assert cm.latest() is None


def test_list_completed_phases(tmp_path):
    cm = CheckpointManager(checkpoint_dir=tmp_path)
    cm.save("phase_0", {})
    cm.save("phase_2", {})
    phases = cm.list_completed()
    assert sorted(phases) == ["phase_0", "phase_2"]

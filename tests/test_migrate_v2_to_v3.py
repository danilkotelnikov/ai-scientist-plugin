# tests/test_migrate_v2_to_v3.py
"""Verify B1 Task 3: detect_v2_state() + migrate() helpers.

Verifies that the v2 → v3 helper detects a pre-existing `~/.ai-scientist/`
install and moves it to `~/.vedix/`, leaving a `~/.ai-scientist.bak/`
breadcrumb so the user knows their old state was relocated.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from migrate_v2_to_v3 import migrate, detect_v2_state  # noqa: E402


def test_detect_v2_state_when_present(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".ai-scientist" / "palace").mkdir(parents=True)
    (home / ".ai-scientist" / "knowledge.db").write_bytes(b"sqlite")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    state = detect_v2_state()
    assert state["v2_root"] == home / ".ai-scientist"
    assert state["has_palace"] is True
    assert state["has_knowledge_db"] is True


def test_migrate_moves_state_to_v3(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".ai-scientist" / "palace").mkdir(parents=True)
    (home / ".ai-scientist" / "palace" / "drawer1.json").write_text('{"a": 1}')
    (home / ".ai-scientist" / "knowledge.db").write_bytes(b"sqlite")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    migrate(confirm=False)

    assert (home / ".vedix" / "palace" / "drawer1.json").exists()
    assert (home / ".vedix" / "knowledge.db").exists()
    # Breadcrumb directory should be left at ~/.ai-scientist.bak/
    assert (home / ".ai-scientist.bak").exists()
    assert (home / ".ai-scientist.bak" / "MIGRATED_TO_VEDIX.txt").exists()
    # Old dir should be moved (no longer present at original location)
    assert not (home / ".ai-scientist").exists()

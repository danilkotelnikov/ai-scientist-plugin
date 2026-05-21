"""Migrate Vedix v2.x state to v3.0 layout.

v2.x stored runtime state under `~/.ai-scientist/`. v3.0 (Vedix) uses
`~/.vedix/`. This helper:

1. Detects whether a v2 install is present via :func:`detect_v2_state`.
2. :func:`migrate` moves `~/.ai-scientist/` → `~/.vedix/` (after optional
   y/N confirmation) and leaves a `~/.ai-scientist.bak/MIGRATED_TO_VEDIX.txt`
   breadcrumb so a returning user can see where their data went.

The bootstrap scripts call this on first v3.0 install when a v2 directory
is detected and a v3 directory is not.
"""
import os
import shutil
from pathlib import Path


def _home() -> Path:
    """Return the user's home directory. Honors USERPROFILE on Windows
    (which is what monkeypatch and PowerShell set) and falls back to HOME."""
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])


def detect_v2_state() -> dict:
    """Report whether a v2.x install is present and what it contains."""
    v2 = _home() / ".ai-scientist"
    return {
        "v2_root": v2,
        "exists": v2.exists(),
        "has_palace": (v2 / "palace").exists(),
        "has_knowledge_db": (v2 / "knowledge.db").exists(),
        "has_corpus": (v2 / "corpus").exists(),
        "has_classifiers": (v2 / "classifiers").exists(),
    }


def migrate(confirm: bool = True) -> None:
    """Move ~/.ai-scientist/ to ~/.vedix/ and leave a breadcrumb."""
    state = detect_v2_state()
    if not state["exists"]:
        print("[migrate] no v2.x install detected at ~/.ai-scientist - nothing to do")
        return

    v2 = state["v2_root"]
    v3 = _home() / ".vedix"

    if v3.exists():
        print(f"[migrate] {v3} already exists; refusing to overwrite")
        return

    if confirm:
        resp = input(f"[migrate] move {v2} -> {v3}? [y/N]: ").strip().lower()
        if resp != "y":
            print("[migrate] aborted by user")
            return

    print(f"[migrate] moving {v2} -> {v3}")
    shutil.move(str(v2), str(v3))

    # Leave a breadcrumb at the old location so users know what happened
    backup_marker = _home() / ".ai-scientist.bak"
    backup_marker.mkdir(exist_ok=True)
    (backup_marker / "MIGRATED_TO_VEDIX.txt").write_text(
        f"This v2 directory was migrated to ~/.vedix/ on Vedix v3.0 install.\n"
        f"State is now at: {v3}\n"
    )
    print(f"[migrate] done. Breadcrumb at {backup_marker}")


if __name__ == "__main__":
    import sys
    confirm = "--no-confirm" not in sys.argv
    migrate(confirm=confirm)

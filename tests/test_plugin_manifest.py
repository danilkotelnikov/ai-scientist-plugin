# tests/test_plugin_manifest.py
"""Verify B1 Task 1 rename: plugins/ai-scientist/ → plugins/vedix/, manifest bumped to 3.0.0.

`json.loads()` returns `Any` at the runtime/JSON-text boundary; that's correct
and per-line `# pyright: ignore[reportAny]` directives are the idiomatic way
to acknowledge it without polluting production code with TypedDict scaffolding
that basedpyright still refuses to recognize through the JSON cast.
"""
import json
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "vedix"


def test_plugin_renamed_to_vedix() -> None:
    assert PLUGIN_DIR.exists(), "plugins/vedix/ must exist after rename"
    manifest = json.loads(  # pyright: ignore[reportAny]
        (PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "vedix"  # pyright: ignore[reportAny]
    assert manifest["version"].startswith("3.0")  # pyright: ignore[reportAny]
    # Claude Code auto-discovers commands from commands/*.md when the manifest
    # omits the `commands` field. Verify the discovery directory + the entry
    # point command file exist on disk.
    cmd_md = PLUGIN_DIR / "commands" / "vedix.md"
    assert cmd_md.exists(), "commands/vedix.md must exist for slash-command discovery"

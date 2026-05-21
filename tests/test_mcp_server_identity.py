# tests/test_mcp_server_identity.py
"""Verify B1 Task 2: MCP server identity renamed to `vedix`, tool namespace swept.

`json.loads()` returns `Any` at the runtime/JSON-text boundary; that's correct
and per-line `# pyright: ignore[reportAny]` directives are the idiomatic way
to acknowledge it without polluting test code with TypedDict scaffolding.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PY = ROOT / "plugins" / "vedix" / "mcp" / "server.py"
MCP_JSON = ROOT / "plugins" / "vedix" / "mcp" / ".mcp.json"


def test_server_py_serverinfo_is_vedix_v3() -> None:
    content = SERVER_PY.read_text(encoding="utf-8")
    # serverInfo block must announce name=vedix, version starting with 3.0
    assert '"name": "vedix"' in content, "server.py serverInfo must declare name=vedix"
    assert re.search(r'"version"\s*:\s*"3\.0', content), (
        "server.py must contain a 3.0.x version literal"
    )


def test_server_py_no_legacy_tool_namespace() -> None:
    content = SERVER_PY.read_text(encoding="utf-8")
    assert "mcp__ai-scientist__" not in content, (
        "server.py must not reference the legacy mcp__ai-scientist__ tool namespace"
    )


def test_mcp_json_has_vedix_server_key() -> None:
    manifest = json.loads(MCP_JSON.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    servers = manifest["mcpServers"]  # pyright: ignore[reportAny]
    assert "vedix" in servers, ".mcp.json must register the `vedix` server key"
    assert "ai-scientist" not in servers, (
        ".mcp.json must not still register the legacy `ai-scientist` server key"
    )

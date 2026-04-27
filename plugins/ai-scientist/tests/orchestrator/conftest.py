"""Override the system-level 'mcp' package (MCP SDK in site-packages) so that
the local mcp/ namespace package inside this plugin root is used instead.

The local mcp/ has no __init__.py (it is a namespace package), which means a
plain sys.path.insert() is insufficient — the installed MCP SDK has a real
__init__.py and always wins.  We inject the local package directly into
sys.modules before any test module is imported.
"""
import sys
import types
import pathlib
import os

# Resolve the plugin root from this conftest's own __file__.  Python resolves
# __file__ correctly even when the path contains non-ASCII (Cyrillic) chars.
_CONFTEST_DIR = pathlib.Path(__file__).resolve().parent          # tests/orchestrator/
_PLUGIN_ROOT  = _CONFTEST_DIR.parent.parent                      # plugins/ai-scientist/
_LOCAL_MCP    = str(_PLUGIN_ROOT / "mcp")                        # plugins/ai-scientist/mcp/

# Only inject when the installed MCP SDK would otherwise win.
_current_mcp = sys.modules.get("mcp")
_current_mcp_path = getattr(_current_mcp, "__path__", [])
if not _current_mcp_path or _LOCAL_MCP not in _current_mcp_path:
    # Remove any previously cached mcp and its sub-modules so that subsequent
    # `import mcp.*` statements walk our injected module's __path__.
    for _key in [k for k in sys.modules if k == "mcp" or k.startswith("mcp.")]:
        del sys.modules[_key]

    _mcp_mod = types.ModuleType("mcp")
    _mcp_mod.__path__ = [_LOCAL_MCP]
    _mcp_mod.__package__ = "mcp"
    sys.modules["mcp"] = _mcp_mod

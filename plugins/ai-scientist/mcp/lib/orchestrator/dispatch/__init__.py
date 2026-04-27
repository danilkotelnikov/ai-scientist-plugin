"""Per-host dispatch backends: claude_code, codex, gemini.

`get_dispatcher(host)` returns the class for a host string. The host is
typically resolved by `codex_bridge.detect_host()`, but this package does
not import or depend on that helper.
"""

from .claude_code import ClaudeCodeDispatcher
from .codex import CodexDispatcher
from .gemini import GeminiDispatcher


_DISPATCHERS = {
    "claude_code": ClaudeCodeDispatcher,
    "codex": CodexDispatcher,
    "gemini": GeminiDispatcher,
}


def get_dispatcher(host: str) -> type:
    """Return the dispatcher class for the given host name.

    Raises:
        ValueError: if `host` is not one of the known backends.
    """
    try:
        return _DISPATCHERS[host]
    except KeyError:
        raise ValueError(
            f"Unknown host {host!r}. Valid values: {list(_DISPATCHERS)}"
        ) from None


__all__ = ["ClaudeCodeDispatcher", "CodexDispatcher", "GeminiDispatcher", "get_dispatcher"]

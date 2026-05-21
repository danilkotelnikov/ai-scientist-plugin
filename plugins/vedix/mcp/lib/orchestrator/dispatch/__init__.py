"""Per-host dispatch backends: claude_code, codex, gemini.

`get_dispatcher(host)` returns the class for a host string. The host is
typically resolved by `codex_bridge.detect_host()`, but this package does
not import or depend on that helper.
"""

from .claude_code import ClaudeCodeDispatcher
from .codex import CodexDispatcher
from .codex_native import CodexNativeDispatcher
from .gemini import GeminiDispatcher


_DISPATCHERS = {
    "claude_code": ClaudeCodeDispatcher,
    "codex": CodexDispatcher,           # v2.0 stub (kept for backward compat)
    "codex_native": CodexNativeDispatcher,  # v2.1 spawn_agent + slot-leak guard
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


__all__ = ["ClaudeCodeDispatcher", "CodexDispatcher",
           "CodexNativeDispatcher", "GeminiDispatcher", "get_dispatcher",
           "dispatch_agent"]


# --------------------------------------------------------------------------- #
# v3.0.0 Block 2 — BYOK ProviderRouter integration.                           #
#                                                                             #
# `dispatch_agent` is a new top-level entry point that routes a request       #
# through the BYOK ProviderRouter (configured via `vedix provider add`).      #
# The legacy per-host `_DISPATCHERS` registry above remains untouched so      #
# v2.1.x callers (codex_bridge.detect_host -> get_dispatcher) keep working.   #
# --------------------------------------------------------------------------- #
import json as _json

_router = None


def _get_router():
    """Lazily build the BYOK ProviderRouter from ~/.vedix/byok/providers.json."""
    global _router
    if _router is None:
        from ..byok import factory as _byok_factory
        _router = _byok_factory.build_router()
    return _router


async def dispatch_agent(
    *,
    agent_type: str,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
):
    """Send a single prompt through the BYOK ProviderRouter.

    `agent_type` is used to look up per-agent-class overrides. If `model` is
    not supplied we resolve to the default model of the first provider in the
    configured chain.
    """
    from ..byok import factory as _byok_factory
    from ..byok.base import ChatRequest, Message

    msgs: list[Message] = []
    if system:
        msgs.append(Message(role="system", content=system))
    msgs.append(Message(role="user", content=prompt))

    if not model:
        cfg = _json.loads(
            (_byok_factory._byok_root() / "providers.json").read_text(encoding="utf-8")
        )
        first = cfg["chain"][0] if cfg.get("chain") else "anthropic"
        model = _byok_factory.default_model(first)

    req = ChatRequest(messages=msgs, model=model, max_tokens=max_tokens)
    router = _get_router()
    return await router.chat(req, agent_class=agent_type)

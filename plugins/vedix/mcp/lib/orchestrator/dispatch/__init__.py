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
           "dispatch_agent", "AGENT_CLASS_DEFAULTS"]


# --------------------------------------------------------------------------- #
# v3.0.0 Block 2 — BYOK ProviderRouter integration.                           #
#                                                                             #
# `dispatch_agent` is a new top-level entry point that routes a request       #
# through the BYOK ProviderRouter (configured via `vedix provider add`).      #
# The legacy per-host `_DISPATCHERS` registry above remains untouched so      #
# v2.1.x callers (codex_bridge.detect_host -> get_dispatcher) keep working.   #
# --------------------------------------------------------------------------- #
import json as _json


# --------------------------------------------------------------------------- #
# v3.0.0 Block 13 — Agent-class defaults registry (SGCA).                     #
#                                                                             #
# Each entry declares per-class preferred providers, max_tokens, and model    #
# overrides. ProviderRouter consults this when no per-agent_class chain was   #
# pre-built (so SGCA agents work without manual `vedix provider add` for     #
# every class). Existing pre-built chains in BYOK config take precedence.     #
# --------------------------------------------------------------------------- #
AGENT_CLASS_DEFAULTS = {
    "paper-extractor": {
        "preferred_providers": ["deepseek", "qwen", "openai", "anthropic"],
        "model_overrides": {
            "deepseek": "deepseek-chat",
            "qwen": "qwen-max",
            "openai": "gpt-5",
            "anthropic": "claude-sonnet-4-20250514",
        },
        "max_tokens": 8192,
        "response_format": "yaml",
    },
    "claim-verifier": {
        "preferred_providers": ["deepseek", "qwen"],
        "model_overrides": {"deepseek": "deepseek-chat", "qwen": "qwen-max"},
        "max_tokens": 1024,
    },
    "paragraph-planner": {
        "preferred_providers": ["deepseek", "qwen"],
        "max_tokens": 2048,
    },
    "lattice-merger": {
        "preferred_providers": ["deepseek", "qwen"],
        "max_tokens": 512,
    },
}


_router = None


def _get_router():
    """Lazily build the BYOK ProviderRouter from ~/.vedix/byok/providers.json."""
    global _router
    if _router is None:
        from ..byok import factory as _byok_factory
        _router = _byok_factory.build_router()
    return _router


# --------------------------------------------------------------------------- #
# Host-native dispatcher injection.                                           #
#                                                                             #
# Per design — BYOK is the fallback path; the PRIMARY path is the agentic     #
# CLI host's native subagent mechanism (Claude Code's Task tool, Codex's     #
# spawn_agent, Gemini's inline reasoning). The MCP server (server.py) sets   #
# `_host_dispatcher` at startup with a callable that takes (agent_type,      #
# prompt, system, max_tokens) and returns a coroutine yielding a ChatResponse#
# -shaped object. Standalone scripts (corpus prep, training, etc.) leave it  #
# None and fall back to BYOK.                                                #
# --------------------------------------------------------------------------- #
_host_dispatcher = None  # type: ignore[assignment]


def set_host_dispatcher(dispatcher_callable) -> None:
    """Called by the MCP server at boot to inject the host-native dispatcher.

    `dispatcher_callable` signature::

        async def dispatch(
            *,
            agent_type: str,
            prompt: str,
            system: str | None = None,
            max_tokens: int = 4096,
        ) -> ChatResponse-shaped object
    """
    global _host_dispatcher
    _host_dispatcher = dispatcher_callable


def detect_host_native_available() -> bool:
    """True if a host-native dispatcher has been injected (we're inside an
    agentic CLI's MCP context). False when running standalone (CLI scripts,
    SaaS, etc.)."""
    return _host_dispatcher is not None


async def dispatch_agent(
    *,
    agent_type: str,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
):
    """Dispatch an agent. Routes to host-native subagent first, BYOK fallback.

    Order:
      1. Host-native (Claude Code Task tool / Codex spawn_agent / Gemini)
         — when the MCP server has injected `_host_dispatcher` at boot.
      2. BYOK ProviderRouter — when running standalone (corpus prep,
         training scripts, SaaS, or any callsite without an agentic CLI
         host wrapping the Python process).

    `agent_type` is the agent class name (matches Claude Code's
    `subagent_type` after the `vedix-` prefix; matches Codex's agent
    name; etc.).
    """
    # --- Path 1: host-native (Claude Code / Codex / Gemini) ---
    if _host_dispatcher is not None:
        try:
            return await _host_dispatcher(
                agent_type=agent_type,
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
            )
        except Exception:
            # Host-native failure (e.g. Task tool timeout) — fall through to BYOK.
            pass

    # --- Path 2: BYOK ProviderRouter ---
    from ..byok import factory as _byok_factory
    from ..byok.base import ChatRequest, Message

    msgs: list[Message] = []
    if system:
        msgs.append(Message(role="system", content=system))
    msgs.append(Message(role="user", content=prompt))

    if not model:
        try:
            cfg = _json.loads(
                (_byok_factory._byok_root() / "providers.json").read_text(encoding="utf-8")
            )
            first = cfg["chain"][0] if cfg.get("chain") else "anthropic"
            model = _byok_factory.default_model(first)
        except FileNotFoundError as e:
            raise RuntimeError(
                "Cannot dispatch agent: no host-native dispatcher injected "
                "(not running inside an agentic CLI) AND no BYOK provider "
                "configured at ~/.vedix/byok/providers.json. Run "
                "`vedix provider add <name> --api-key ...` to configure BYOK, "
                "or launch this code from inside Claude Code / Codex / Gemini."
            ) from e

    req = ChatRequest(messages=msgs, model=model, max_tokens=max_tokens)
    router = _get_router()
    return await router.chat(req, agent_class=agent_type)

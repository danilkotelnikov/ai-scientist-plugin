"""Codex bridge for ai-scientist (Claude Code-exclusive).

Programmatic Python wrapper around openai/codex-plugin-cc's companion script.
Lets the orchestrator delegate tasks to Codex, cross-validate Claude outputs,
and fall back to Codex when Claude hits API errors or ToS violations.

Public surface:
    CodexBridge       -- main client class
    CrossValidation   -- result of a cross_validate() call
    CodexResult       -- result of any task/review/result call
    CodexUnavailable  -- raised if codex-plugin-cc isn't installed or auth fails
    CodexTimeout      -- raised when a job exceeds its timeout

CC-exclusive: the bridge raises CodexUnavailable on hosts other than Claude Code.
"""
from .bridge import (
    CodexBridge,
    CodexResult,
    CrossValidation,
    CodexUnavailable,
    CodexTimeout,
    detect_host,
)

__all__ = [
    "CodexBridge",
    "CodexResult",
    "CrossValidation",
    "CodexUnavailable",
    "CodexTimeout",
    "detect_host",
]

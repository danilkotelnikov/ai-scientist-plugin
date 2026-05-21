"""Phase-0 preflight probes — toolchain, Codex runtime, memory tools.

Closes review-doc findings #14, #16, #17, #20.
"""
from __future__ import annotations
import shutil
from typing import Optional


def _which(cmd: str) -> Optional[str]:
    """Wrapper for shutil.which — patched in tests."""
    return shutil.which(cmd)


def probe_toolchain() -> dict:
    """Probe local LaTeX, Word-export, and PDF-renderer binaries."""
    latex_bins = ["pdflatex", "xelatex", "lualatex", "tectonic", "bibtex"]
    word_bins = ["pandoc"]
    render_bins = ["pdftoppm", "mutool", "magick", "gs"]
    return {
        "latex": {b: bool(_which(b)) for b in latex_bins},
        "word_export": {b: bool(_which(b)) for b in word_bins},
        "visual_validation": {b: bool(_which(b)) for b in render_bins},
    }


def probe_codex_runtime(*, host: str, available_tools: dict) -> dict:
    """Confirm spawn_agent / wait / close_agent are exposed in this session."""
    has_spawn = bool(available_tools.get("spawn_agent"))
    has_wait = bool(available_tools.get("wait"))
    has_close = bool(available_tools.get("close_agent"))
    out = {
        "host": host,
        "spawn_agent_available": has_spawn,
        "wait_available": has_wait,
        "close_agent_available": has_close,
        "max_threads": available_tools.get("max_threads", 6),
        "max_depth": available_tools.get("max_depth", 1),
        "session_policy_evidence": "config.toml [features] / [agents] inspection",
        "fallback": None,
    }
    if not (has_spawn and has_wait and has_close):
        out["fallback"] = "inline_phase_templates"
    return out


def probe_memory_tools(*, expected: list, available: list) -> dict:
    """Compare expected MemPalace tools against what the session exposes."""
    exp = set(expected)
    avail = set(available)
    return {
        "mempalace_expected": list(expected),
        "mempalace_available": list(available),
        "missing": sorted(exp - avail),
        "fallback": "write knowledge_index.json only" if exp - avail else None,
    }

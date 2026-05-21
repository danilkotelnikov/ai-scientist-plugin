"""Gemini CLI dispatcher — falls back to inline reasoning.

Gemini lacks Task / spawn_agent. The pipeline executes the prompt in the
current session. This dispatcher just locates the agent .md file and
returns its path; the pipeline reads it and inlines the body.
"""
from __future__ import annotations
import os
from pathlib import Path


class GeminiDispatcher:
    name = "gemini"

    def dispatch(self, *, agent_name: str, inputs: dict) -> dict:
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
        agent_path = Path(plugin_root) / "agents" / f"{agent_name}.md"
        return {
            "mode": "inline",
            "agent_path": str(agent_path),
            "inputs": inputs,
            "note": "Gemini lacks Task; pipeline must execute this prompt inline.",
        }

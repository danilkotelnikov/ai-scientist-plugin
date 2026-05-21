"""Codex CLI dispatcher — uses spawn_agent."""
from __future__ import annotations
from typing import Callable, Optional


class CodexDispatcher:
    name = "codex"

    def __init__(self, spawn_agent: Optional[Callable] = None):
        self.spawn_agent = spawn_agent

    def dispatch(self, *, agent_name: str, inputs: dict) -> dict:
        if self.spawn_agent is None:
            raise RuntimeError("CodexDispatcher.spawn_agent not injected")
        message = self._build_message(agent_name, inputs)
        return self.spawn_agent(agent_type="worker", message=message)

    @staticmethod
    def _build_message(agent_name: str, inputs: dict) -> str:
        from pathlib import Path
        import os
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
        agent_path = Path(plugin_root) / "agents" / f"{agent_name}.md"
        try:
            agent_body = agent_path.read_text(encoding="utf-8")
        except OSError:
            agent_body = f"(agent file missing: {agent_path})"
        input_block = "\n".join(f"<input name={k!r}>{v}</input>" for k, v in inputs.items())
        return (
            "Your task is to perform the following. Follow the instructions below exactly.\n\n"
            f"<agent-instructions>\n{agent_body}\n</agent-instructions>\n\n"
            f"Inputs:\n{input_block}\n\n"
            "Execute this now. Output ONLY the structured response wrapped in "
            "<output name=\"...\"> tags as specified."
        )

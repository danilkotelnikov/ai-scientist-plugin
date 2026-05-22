"""Claude Code dispatcher — uses the host's Task tool via MCP surface.

The pipeline calls dispatch() but the actual Task() call is performed by
Claude Code itself via mcp__vedix__dispatch_phase. This class is a thin
wrapper that pipeline.py uses; in production the Task tool is injected
by the MCP server's tool-call handler.

Subagent type matches the `name:` field in plugins/vedix/agents/<agent>.md
frontmatter — every agent file declares `name: vedix-<agent_name>` so the
host can resolve Task(subagent_type="vedix-...") to the right prompt.
"""
from __future__ import annotations
from typing import Callable, Optional


class ClaudeCodeDispatcher:
    name = "claude_code"

    def __init__(self, task_tool: Optional[Callable] = None):
        self.task_tool = task_tool

    def dispatch(self, *, agent_name: str, inputs: dict) -> dict:
        """Invoke Task(subagent_type=f"vedix-{agent_name}", prompt=...)."""
        if self.task_tool is None:
            raise RuntimeError(
                "ClaudeCodeDispatcher.task_tool not injected. "
                "MCP server must pass the host's Task tool when constructing."
            )
        subagent_type = f"vedix-{agent_name}"
        prompt = self._build_prompt(agent_name, inputs)
        return self.task_tool(subagent_type=subagent_type, prompt=prompt)

    @staticmethod
    def _build_prompt(agent_name: str, inputs: dict) -> str:
        # Inline inputs as <input name="...">value</input> blocks
        lines = [f"<input name={k!r}>{v}</input>" for k, v in inputs.items()]
        return "\n".join(lines)

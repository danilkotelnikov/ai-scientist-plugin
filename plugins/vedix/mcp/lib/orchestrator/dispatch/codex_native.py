"""Codex-native dispatcher with spawn_agent waves + slot-leak guard.

Closes review-doc findings #11, #12. Slot leak guard for GitHub issue
#18335 (codex_cli unclosed terminal agents).
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Callable, Optional


class CodexNativeDispatcher:
    name = "codex"

    def __init__(self, *,
                 spawn_agent: Optional[Callable] = None,
                 wait: Optional[Callable] = None,
                 close_agent: Optional[Callable] = None,
                 max_threads: int = 6,
                 default_model: str = "gpt-5.5",
                 default_effort: str = "xhigh"):
        self.spawn_agent = spawn_agent
        self.wait = wait
        self.close_agent = close_agent
        self.max_threads = int(max_threads)
        self.default_model = default_model
        self.default_effort = default_effort

    def _build_message(self, agent_name: str, inputs: dict) -> str:
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
        agent_path = Path(plugin_root) / "agents" / f"{agent_name}.md"
        try:
            agent_body = agent_path.read_text(encoding="utf-8")
        except OSError:
            agent_body = f"(agent file missing: {agent_path})"
        input_block = "\n".join(
            f"<input name={k!r}>{v}</input>" for k, v in inputs.items())
        return (
            "Your task is to perform the following. Follow the instructions exactly.\n\n"
            f"<agent-instructions>\n{agent_body}\n</agent-instructions>\n\n"
            f"Inputs:\n{input_block}\n\n"
            "Execute now. Output ONLY the structured response wrapped in "
            "<output name=\"...\"> tags as specified."
        )

    def dispatch(self, *, agent_name: str, inputs: dict) -> dict:
        """Single-shot dispatch. Falls back inline when spawn unavailable."""
        if self.spawn_agent is None:
            plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
            return {
                "mode": "inline_fallback",
                "agent_path": str(Path(plugin_root) / "agents"
                                  / f"{agent_name}.md"),
                "inputs": inputs,
                "reason": "spawn_agent not available in session",
            }
        # Single-shot: just one wave with one input
        return (self.dispatch_wave(agent_name=agent_name,
                                   inputs_list=[inputs]) or [{}])[0]

    def dispatch_wave(self, *, agent_name: str,
                      inputs_list: list,
                      timeout_ms: int = 600_000) -> list:
        """Fan-out / fan-in. Slot-leak-guarded for GitHub issue #18335."""
        if self.spawn_agent is None or self.wait is None or self.close_agent is None:
            # Fall back to sequential inline dispatch
            return [self.dispatch(agent_name=agent_name, inputs=inp)
                    for inp in inputs_list]

        capped = inputs_list[: self.max_threads]
        spawned: list = []
        try:
            for inp in capped:
                r = self.spawn_agent(
                    message=self._build_message(agent_name, inp),
                    agent_type="worker",
                    model=self.default_model,
                    reasoning_effort=self.default_effort,
                    fork_context=False,
                )
                spawned.append(r["agent_id"])
            statuses = self.wait(ids=spawned, timeout_ms=timeout_ms)
            return [statuses["status"].get(aid, {}).get("payload", {})
                    for aid in spawned]
        finally:
            # ALWAYS close — slot-leak guard for issue #18335
            for aid in spawned:
                try:
                    self.close_agent(aid)
                except Exception:
                    pass

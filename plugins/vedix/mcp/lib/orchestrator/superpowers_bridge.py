"""Bridges between superpowers skills (writing-plans, executing-plans,
subagent-driven-development) and the plugin-development palace.

Per spec §4.14 + §7.4.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any


class WritingPlansBridge:
    def __init__(self, plugin_palace: Any):
        self.palace = plugin_palace

    def on_plan_written(self, plan_path: Path) -> None:
        if self.palace is None:
            return
        try:
            self.palace.archive_plan(plan_path, metadata={"event": "writing-plans:plan-saved"})
        except Exception:
            pass


class ExecutingPlansBridge:
    def __init__(self, plugin_palace: Any):
        self.palace = plugin_palace

    def on_skill_start(self, plan_path: Path) -> str:
        if self.palace is None:
            return ""
        try:
            content = Path(plan_path).read_text(encoding="utf-8")
            return self.palace.wake_up(query=content[:500], token_budget=2000)
        except Exception:
            return ""

    def on_step_complete(self, *, step_id: int, outcome: str) -> None:
        # Diary writes happen via the project palace in pipeline.py
        return None

    def on_skill_complete(self, *, plan_path: Path, summary: str) -> None:
        if self.palace is None:
            return
        try:
            self.palace.archive_audit(
                audit_text=f"Plan {plan_path.name} complete:\n{summary}",
                metadata={"event": "executing-plans:complete"},
            )
        except Exception:
            pass


class SubagentDrivenBridge:
    def __init__(self, plugin_palace: Any):
        self.palace = plugin_palace

    def before_dispatch(self, *, task_description: str) -> list:
        if self.palace is None:
            return []
        try:
            return self.palace.search(query=task_description, limit=5)
        except Exception:
            return []

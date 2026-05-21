"""PluginPalace + ProjectPalace ergonomic wrappers around the 29
mcp__mempalace__* tools. Per spec §4.15.

The MCP client is injected so we can mock it in tests. In production,
the MCP server's tool surface is wrapped behind a thin facade.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional


class _PalaceBase:
    def __init__(self, *, root: Path, mcp: Any, wing: str):
        self.root = Path(root)
        self.mcp = mcp
        self.wing = wing


class PluginPalace(_PalaceBase):
    """Plugin-development palace: specs, plans, decisions, dev journal."""

    def archive_spec(self, spec_path: Path, metadata: Optional[dict] = None) -> Optional[str]:
        return self._archive(spec_path, room="specs", metadata=metadata)

    def archive_plan(self, plan_path: Path, metadata: Optional[dict] = None) -> Optional[str]:
        return self._archive(plan_path, room="plans", metadata=metadata)

    def archive_audit(self, audit_text: str, metadata: Optional[dict] = None) -> Optional[str]:
        return self._add_drawer(content=audit_text, room="audits", metadata=metadata)

    def search(self, query: str, limit: int = 5) -> list:
        try:
            r = self.mcp.mempalace_search(query=query, limit=limit)
            return r.get("results", []) if isinstance(r, dict) else []
        except Exception:
            return []

    def wake_up(self, *, query: str = "", token_budget: int = 2000) -> str:
        try:
            r = self.mcp.mempalace_status()
            return json.dumps(r)[:token_budget * 4]
        except Exception:
            return ""

    def _archive(self, path: Path, *, room: str, metadata: Optional[dict]) -> Optional[str]:
        path = Path(path)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None
        meta = dict(metadata or {})
        meta["source_path"] = str(path)
        return self._add_drawer(content=content, room=room, metadata=meta)

    def _add_drawer(self, *, content: str, room: str, metadata: Optional[dict]) -> Optional[str]:
        try:
            r = self.mcp.mempalace_add_drawer(
                wing=self.wing, room=room, content=content,
                source_file=(metadata or {}).get("source_path", ""),
                added_by="orchestrator",
            )
            return r.get("drawer_id") if isinstance(r, dict) else None
        except Exception:
            return None


class ProjectPalace(_PalaceBase):
    """Per-project palace: research-plan, phase-checkpoints, agent-diaries,
    cross-validation, token-budget, research-findings.
    """

    def write_diary(self, *, agent: str, content: str, tags: Optional[list] = None) -> bool:
        try:
            r = self.mcp.mempalace_diary_write(
                wing=self.wing,
                room="agent-diaries",
                content=content,
                tags=tags or [f"agent:{agent}"],
            )
            return bool(r.get("success"))
        except Exception:
            return False

    def write_findings(self, *, section: str, content: str) -> bool:
        body = f"## {section}\n\n{content}"
        try:
            r = self.mcp.mempalace_add_drawer(
                wing=self.wing,
                room="research-findings",
                content=body,
                added_by="meta-analyst",
            )
            return bool(r.get("success"))
        except Exception:
            return False

    def get_phase_history(self, phase: str) -> list:
        try:
            r = self.mcp.mempalace_search(query=f"phase:{phase}", limit=20)
            return r.get("results", []) if isinstance(r, dict) else []
        except Exception:
            return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

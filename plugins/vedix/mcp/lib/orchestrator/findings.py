"""FindingsScaffold — 5-section narrative-memory. Per spec §4.13 + §8.2.

Vendored from AI-Research-SKILLs autoresearch (drawer_kind:
research_findings). Updated by meta-analyst at every outer-loop checkpoint.
Prevents repeated-failure loops across sessions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict


FINDINGS_SECTIONS = [
    "current_understanding",
    "patterns_and_insights",
    "lessons_and_constraints",
    "open_questions",
    "last_direction_decision",
]


@dataclass
class FindingsScaffold:
    sections: Dict[str, str] = field(default_factory=lambda: {s: "" for s in FINDINGS_SECTIONS})

    def update(self, section: str, content: str) -> None:
        if section not in FINDINGS_SECTIONS:
            raise KeyError(f"unknown section {section!r}; expected one of {FINDINGS_SECTIONS}")
        self.sections[section] = content

    def append(self, section: str, content: str) -> None:
        if section not in FINDINGS_SECTIONS:
            raise KeyError(f"unknown section {section!r}")
        existing = self.sections[section]
        self.sections[section] = (existing + "\n- " + content).strip().lstrip("-").strip()
        # Ensure list format
        if not self.sections[section].startswith("- "):
            self.sections[section] = "- " + self.sections[section]

    def to_dict(self) -> dict:
        return dict(self.sections)

    def to_markdown(self) -> str:
        lines = ["# Findings\n"]
        for s in FINDINGS_SECTIONS:
            title = s.replace("_", " ").title()
            body = self.sections[s] or "_(empty)_"
            lines.append(f"## {title}\n\n{body}\n")
        return "\n".join(lines)

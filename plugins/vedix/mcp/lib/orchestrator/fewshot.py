"""Few-shot example injection. Per spec §4.8.

Activates for ideator (paper exemplars), hypothesizer (well-formed
hypothesis exemplars), reviewer (review exemplars). The example files
already exist at mcp/templates/fewshot/ but were never injected.
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterable


class FewShotInjector:
    def inject(self, agent_prompt: str, examples: Iterable[Path]) -> str:
        """Prepend `<example>...</example>` blocks for each example file."""
        blocks = []
        for path in examples:
            p = Path(path)
            if not p.is_file():
                continue
            try:
                body = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            blocks.append(f"<example source={p.name!r}>\n{body}\n</example>")
        if not blocks:
            return agent_prompt
        return "\n\n".join(blocks) + "\n\n" + agent_prompt

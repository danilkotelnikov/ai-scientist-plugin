"""§4.7 Provenance ledger + auto-disclosure.

``ProvenanceLedger`` is an append-only JSONL log: one entry per emitted
sentence with the responsible agent, the LLM model, the cited evidence,
and how many self-reflection rounds produced it. ``generate_disclosure``
distills the ledger into the venue-appropriate AI-disclosure boilerplate.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any


class ProvenanceLedger:
    """Append-only JSONL of sentence-level provenance."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        sentence_id: str,
        sentence: str,
        agent: str,
        model: str,
        evidence: list[str],
        reflection_rounds: int = 0,
    ) -> None:
        entry = {
            "ts": time.time(),
            "sentence_id": sentence_id,
            "sentence": sentence,
            "agent": agent,
            "model": model,
            "evidence": evidence,
            "reflection_rounds": reflection_rounds,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line:
                out.append(json.loads(line))
        return out


def generate_disclosure(
    *,
    ledger_path: Path,
    venue: str,
    out: Path,
) -> Path:
    """Distill the ledger into a markdown disclosure for the given venue."""
    entries = ProvenanceLedger(path=ledger_path).load_all()
    agents = Counter(e["agent"] for e in entries)
    models = Counter(e["model"] for e in entries)
    rounds = Counter(e["reflection_rounds"] for e in entries)
    total = len(entries)

    md = (
        "# AI Disclosure for this manuscript\n\n"
        f"This manuscript was prepared using the **Vedix research workbench** "
        f"({venue} venue profile). The pipeline orchestrated specialized "
        "agents through a sequence of phases. Sentence-level provenance is "
        "recorded in `provenance.jsonl` (one entry per sentence with the "
        "responsible agent, the LLM model that generated it, the cited "
        "evidence, and the number of self-reflection rounds).\n\n"
        "## Aggregate stats\n\n"
        f"- Sentences emitted: {total}\n"
        f"- Agents involved: {', '.join(sorted(agents))}\n"
        f"- Models used: {', '.join(sorted(models))}\n\n"
        "## Per-agent breakdown\n\n"
        + "\n".join(f"- `{a}`: {n} sentences" for a, n in agents.most_common())
        + "\n\n## Per-model breakdown\n\n"
        + "\n".join(f"- `{m}`: {n} sentences" for m, n in models.most_common())
        + "\n\n## Reflection-round distribution\n\n"
        + "\n".join(f"- {r} rounds: {n} sentences" for r, n in rounds.most_common())
        + "\n\n## Author responsibilities\n\n"
        "The human author(s) reviewed every Vedix-emitted sentence, verified "
        "every citation, ran the reproducibility audit "
        "(`reproducibility_audit.json`), inspected the pre-registration audit "
        "(`prereg_audit.json`), and signed off on the final manuscript. "
        "Author identities and corresponding responsibilities appear in the "
        "manuscript header.\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out

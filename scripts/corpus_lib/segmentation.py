"""Stage 5 — split each paper into paragraphs with section guessing.

Paragraph splitter is regex-based on blank-line separators, which is
robust to the messy paragraphation extractors produce. We deliberately
do NOT depend on spaCy at unit-test time — sentence splitting is left to
the trainer's tokenizer at max_length=256/512. spaCy models are still
declared in ``requirements.txt`` for downstream features that want them.

Section-name guessing is a lightweight regex pass over the recent 2
paragraphs of history.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


_SECTION_KW: dict[str, list[str]] = {
    "Introduction": [r"\bintroduction\b", r"\bbackground\b"],
    "Methods": [
        r"\bmethods\b",
        r"\bmethodolog",
        r"\bexperimental\b",
        r"\bmaterials and methods\b",
        r"\bprocedure\b",
        r"\bprotocol\b",
    ],
    "Results": [r"\bresults\b", r"\bfindings\b", r"\bobservations\b"],
    "Discussion": [r"\bdiscussion\b"],
    "Conclusion": [r"\bconclusion\b", r"\bsummary\b"],
}


def _paragraph_split(text: str) -> list[str]:
    """Split on blank lines; drop empties."""
    paras = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paras if p.strip()]


def _guess_section(text: str, idx: int, all_paras: list[str]) -> str:
    """Walk back two paragraphs for a section-header keyword."""
    head_text = " ".join(all_paras[max(0, idx - 2) : idx + 1]).lower()
    for sect, patterns in _SECTION_KW.items():
        if any(re.search(p, head_text) for p in patterns):
            return sect
    return "Body"


def segment(
    text: str,
    *,
    paper_id: str,
    language: str = "en",  # noqa: ARG001 — accepted for parity, used in v3.1+
) -> list[dict]:
    """Split a paper into paragraph records (drops obvious boilerplate)."""
    paragraphs = _paragraph_split(text)
    out: list[dict] = []
    for i, p in enumerate(paragraphs):
        n_words = len(p.split())
        if n_words < 20 or n_words > 600:
            # too short → boilerplate; too long → bad split
            continue
        out.append(
            {
                "paper_id": paper_id,
                "para_idx": i,
                "text": p,
                "n_words": n_words,
                "section": _guess_section(p, i, paragraphs),
            }
        )
    return out


def segment_paper(
    text_file: Path,
    *,
    paper_id: str,
    language: str,
    out_jsonl: Path,
) -> int:
    """Segment one paper and append its paragraph records to ``out_jsonl``."""
    text = text_file.read_text(encoding="utf-8")
    paragraphs = segment(text, paper_id=paper_id, language=language)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("a", encoding="utf-8") as f:
        for p in paragraphs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return len(paragraphs)

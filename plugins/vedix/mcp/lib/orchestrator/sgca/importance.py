from __future__ import annotations
from typing import Iterable


def compute_importance(*, mentions_in_manuscript: int, downstream_anchor_count: int,
                       appears_in_abstract: bool, appears_in_conclusion: bool) -> float:
    """SGCA §5.4 importance formula:
        importance = 0.4*mentions + 0.3*downstream + 0.2*abstract + 0.1*conclusion
    """
    return (
        0.4 * mentions_in_manuscript
        + 0.3 * downstream_anchor_count
        + 0.2 * (1 if appears_in_abstract else 0)
        + 0.1 * (1 if appears_in_conclusion else 0)
    )


def top_headline_claims(candidates: dict[str, dict], *, n: int = 10) -> list[str]:
    """`candidates` keys are claim IDs; values are dicts with keys
    `mentions`, `downstream`, `in_abstract`, `in_conclusion`. Returns the
    top-n claim IDs by descending importance score."""
    scored = [
        (cid, compute_importance(
            mentions_in_manuscript=v["mentions"],
            downstream_anchor_count=v["downstream"],
            appears_in_abstract=v["in_abstract"],
            appears_in_conclusion=v["in_conclusion"],
        ))
        for cid, v in candidates.items()
    ]
    scored.sort(key=lambda cv: cv[1], reverse=True)
    return [cid for cid, _ in scored[:n]]

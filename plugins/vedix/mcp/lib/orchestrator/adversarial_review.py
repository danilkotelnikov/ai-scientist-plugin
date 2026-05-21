"""§4.4 Adversarial multi-pass review.

Run the same manuscript through N stances (steelman, break, re-steelman),
each emitting an integer 1-10 score + 3-sentence rationale. Report
median, min, max, and disagreement (max - min) — high disagreement is a
human-attention signal.
"""
from __future__ import annotations

import json
import re
import statistics
from typing import Any

from . import dispatch as _dispatch_mod


STANCES = [
    "steelman this manuscript — write the strongest possible defense "
    "before finding weaknesses",
    "break this manuscript — adopt a hostile reviewer position; find "
    "every reason this is wrong",
    "re-steelman after reading the break — what is the strongest case "
    "after considering the criticisms",
]


async def _pass(manuscript_text: str, stance: str) -> dict[str, Any]:
    prompt = (
        f"Stance: {stance}\n\n"
        f"Manuscript:\n{manuscript_text[:8000]}\n\n"
        "Score the manuscript 1-10 and give 3 sentences of rationale. "
        'Output JSON: {"score": <int>, "rationale": "<str>"}.\n'
    )
    resp = await _dispatch_mod.dispatch_agent(
        agent_type="adversarial-reviewer", prompt=prompt,
    )
    content = resp.content  # pyright: ignore[reportAny]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        score_match = re.search(r'"score"\s*:\s*(\d+)', content)
        return {
            "score": int(score_match.group(1)) if score_match else 5,
            "rationale": content[:300],
        }


async def review_with_stances(
    *,
    manuscript_text: str,
    n_passes: int = 2,
) -> dict[str, Any]:
    """Run N stances and aggregate scores."""
    stances = STANCES[:n_passes]
    passes: list[dict[str, Any]] = []
    for s in stances:
        p = await _pass(manuscript_text, s)
        p["stance"] = s
        passes.append(p)
    scores = [int(p["score"]) for p in passes]
    return {
        "passes": passes,
        "median_score": int(statistics.median(scores)),
        "min_score": min(scores),
        "max_score": max(scores),
        "disagreement": max(scores) - min(scores),
    }

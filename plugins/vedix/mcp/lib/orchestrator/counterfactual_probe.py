"""§4.3 Counterfactual citation probing.

For each (paragraph, citation) pair, ask the LLM to generate a plausible
decoy of the cited paper (same year, adjacent topic), then ask a second
LLM-judge whether swapping in the decoy changes the paragraph's claim.

* If the judge says ``DIFFERENT`` -> the citation is **load-bearing**.
* If the judge says ``SAME``       -> the citation is **decorative**.

Results are cached by ``(citation_key, hash(paragraph_text))`` so reruns
are cheap.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from . import dispatch as _dispatch_mod


DECOY_PROMPT = (
    "Given the real citation below, invent a plausible-but-fictional "
    "alternative citation with the same publication year and a "
    "thematically-adjacent title. Output JSON with keys: title.\n\n"
    "Real: {real_json}\n"
)

JUDGE_PROMPT = (
    "Read these two variants of the same paragraph. The only difference "
    "is which citation is used.\n\n"
    "Variant A: {variant_a}\n"
    "Variant B: {variant_b}\n\n"
    "Are these making the same factual claim, or different claims? "
    'Respond with exactly "SAME" or "DIFFERENT".\n'
)


async def generate_decoy(real: dict) -> dict:
    """Generate a fictional decoy citation in the same year + adjacent topic."""
    resp = await _dispatch_mod.dispatch_agent(
        agent_type="decoy-generator",
        prompt=DECOY_PROMPT.format(real_json=json.dumps(real)),
    )
    text = resp.content  # pyright: ignore[reportAny]
    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', text)
    title = (
        title_match.group(1)
        if title_match
        else text.strip().split("\n")[0]
    )
    return {"year": real.get("year"), "title": title}


async def probe_citation(
    *,
    paragraph: str,
    citation_key: str,
    real: dict,
    decoy_title: str,
) -> dict[str, Any]:
    """Swap real -> decoy in the paragraph and ask the judge SAME/DIFFERENT."""
    variant_a = paragraph
    variant_b = paragraph.replace(real.get("title", citation_key), decoy_title)
    if variant_a == variant_b:
        # Fallback: just append a marker so the judge sees a delta.
        variant_b = (
            paragraph
            + f" (Note: cites '{decoy_title}' instead of real source)"
        )
    resp = await _dispatch_mod.dispatch_agent(
        agent_type="counterfactual-judge",
        prompt=JUDGE_PROMPT.format(variant_a=variant_a, variant_b=variant_b),
    )
    verdict_text = resp.content.strip().upper()  # pyright: ignore[reportAny]
    load_bearing = "DIFFERENT" in verdict_text
    return {
        "citation_key": citation_key,
        "load_bearing": load_bearing,
        "decoy_title": decoy_title,
        "judge_response": verdict_text,
    }


async def probe_all(
    citations_by_para: dict[str, list[str]],
    references: dict[str, dict],
    paragraphs: dict[str, str],
    cache_path: Optional[Path] = None,
) -> list[dict]:
    """Probe every (paragraph, citation) pair; cache verdicts to disk."""
    cache: dict[str, dict] = {}
    if cache_path and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    results: list[dict] = []
    for para_id, keys in citations_by_para.items():
        para_text = paragraphs.get(para_id, "")
        for k in keys:
            cache_key = f"{k}::{hash(para_text) & 0xffffffff}"
            if cache_key in cache:
                results.append(cache[cache_key])
                continue
            real = {"key": k, **references.get(k, {})}
            decoy = await generate_decoy(real)
            verdict = await probe_citation(
                paragraph=para_text,
                citation_key=k,
                real=real,
                decoy_title=decoy["title"],
            )
            verdict["paragraph_id"] = para_id
            cache[cache_key] = verdict
            results.append(verdict)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache, indent=2), encoding="utf-8",
        )
    return results

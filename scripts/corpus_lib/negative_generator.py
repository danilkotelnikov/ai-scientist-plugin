"""Stage 8 — generate adversarial AI-style negatives via the BYOK provider.

For every positive paragraph we ask the user's BYOK provider to rewrite
it in an unmistakably AI register. The rewriter is instructed to keep
the technical content intact but to inject ≥3 markers from the Tier-1
"AI tell" blacklist used by ``anti_llm_lint`` so the classifier learns
the same stylistic cues we lint for.

The BYOK round-trip goes through ``orchestrator.dispatch.dispatch_agent``;
tests patch ``negative_generator.dispatch_agent`` directly to inject a
fake response object that exposes ``.content``.
"""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

# We import dispatch_agent under both layouts:
#   • Production: ``plugins.vedix.mcp.lib.orchestrator.dispatch``
#   • prepare_corpus.py adds plugins/vedix/mcp/lib to sys.path so the
#     ``orchestrator.dispatch`` short form also works.
# Either way the binding lives on this module so tests can patch it.
_PLUGIN_LIB = Path(__file__).resolve().parents[2] / "plugins" / "vedix" / "mcp" / "lib"
if _PLUGIN_LIB.exists() and str(_PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_LIB))

try:
    from orchestrator.dispatch import dispatch_agent  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - production wiring imported separately
    async def dispatch_agent(**_kw):  # type: ignore[no-redef]
        raise RuntimeError(
            "negative_generator.dispatch_agent stub called without a wired "
            "BYOK ProviderRouter. Patch this function in tests or wire B2."
        )


# Tier-1 + Tier-2 "AI tell" markers; full list lives in
# plugins/vedix/mcp/lib/orchestrator/anti_llm_lint.py — this excerpt is
# what we hint to the rewriter to inject.
TIER1_BLACKLIST_HINT: list[str] = [
    "delve",
    "intricate",
    "tapestry",
    "myriad",
    "navigate",
    "underscore",
    "showcase",
    "leverage",
    "harness",
    "robust",
    "It is important to note that",
    "It is worth mentioning that",
    "In conclusion",
    "Furthermore",
    "Moreover",
    "Notably",
]


PROMPT = """Rewrite this academic paragraph in clearly AI-generated register.
Inject these markers naturally (pick at least 3): {markers}
Maintain the technical content but make the prose unmistakably AI-stylistic.

Original paragraph:
{text}

Output ONLY the rewritten paragraph, no commentary.
"""


def _synthetic_negative(text: str) -> str:
    """Template-based degraded fallback when no BYOK provider is configured.

    Wraps the original paragraph in canonical AI-stylistic scaffolding using
    randomly-picked Tier-1 markers. Not as discriminative as an LLM-generated
    negative but adequate for keeping the corpus pipeline end-to-end usable
    while the user sets up their LLM key.
    """
    markers = random.sample(TIER1_BLACKLIST_HINT, 3)
    return (
        f"{markers[0]}, this passage shows how researchers leverage methods to navigate "
        f"the intricate tapestry of findings. {text} {markers[1]}, the underlying "
        f"showcase of robust evidence underscores the myriad implications. "
        f"{markers[2]}, the work delves into these dimensions."
    )


async def generate_one_negative(text: str) -> str:
    """Ask the BYOK provider to rewrite ``text`` with AI-tell markers.

    Falls back to ``_synthetic_negative`` (template-based) if no BYOK
    provider is configured or the LLM call fails — so corpus prep can
    finish end-to-end even before the user wires up an LLM key.
    """
    markers = random.sample(TIER1_BLACKLIST_HINT, 4)
    try:
        resp = await dispatch_agent(
            agent_type="register-negative-generator",
            prompt=PROMPT.format(text=text, markers=", ".join(markers)),
            max_tokens=600,
        )
        return resp.content.strip()
    except FileNotFoundError:
        # No ~/.vedix/byok/providers.json — degraded fallback.
        return _synthetic_negative(text)
    except Exception:  # noqa: BLE001
        # LLM call failed (rate limit / auth / network) — still produce a
        # negative so the trainer can run.
        return _synthetic_negative(text)


async def generate_negatives(
    positives: list[dict],
    *,
    concurrency: int = 4,
) -> list[dict]:
    """Return one negative per positive, capped at ``concurrency`` in flight."""
    sem = asyncio.Semaphore(concurrency)

    async def _g(p: dict) -> dict:
        async with sem:
            neg_text = await generate_one_negative(p["text"])
        return {
            "paper_id": p["paper_id"] + "_neg",
            "para_idx": p.get("para_idx", -1),
            "text": neg_text,
            "n_words": len(neg_text.split()),
            "section": p.get("section", "Body"),
            "label": 0,
            "label_source": "adversarial_generator",
            "source_para_id": p["paper_id"],
        }

    return list(await asyncio.gather(*[_g(p) for p in positives]))

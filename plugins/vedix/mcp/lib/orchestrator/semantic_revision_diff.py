"""§4.5 Semantic revision diff.

Embed each sentence of the old and new revisions, then for every old
sentence find its best-match new sentence by cosine similarity. Low
similarity = high revision risk (probably a claim change, not a
paraphrase). Polarity inversions ("increased" -> "decreased") drop the
cosine substantially.
"""
from __future__ import annotations

import re
from typing import Any

_MODEL_CACHE: Any = None


def _model() -> Any:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        from sentence_transformers import SentenceTransformer
        _MODEL_CACHE = SentenceTransformer("intfloat/multilingual-e5-large")
    return _MODEL_CACHE


def _sentences(text: str) -> list[str]:
    """Cheap sentence splitter."""
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in raw if s]


def diff_revisions(*, old: str, new: str) -> dict[str, Any]:
    """Compute per-sentence + overall semantic similarity between two revisions."""
    import numpy as np

    old_sents = _sentences(old)
    new_sents = _sentences(new)
    if not old_sents or not new_sents:
        return {"overall_similarity": 0.0, "per_sentence": []}
    m = _model()
    o_emb = m.encode(
        ["query: " + s for s in old_sents], normalize_embeddings=True,
    )
    n_emb = m.encode(
        ["query: " + s for s in new_sents], normalize_embeddings=True,
    )
    sim_matrix = o_emb @ n_emb.T
    per_sentence: list[dict[str, Any]] = []
    for i, os_ in enumerate(old_sents):
        j = int(np.argmax(sim_matrix[i]))
        sim = float(sim_matrix[i][j])
        # Thresholds calibrated for multilingual-e5-large:
        #   >= 0.95  : virtually identical wording -> low risk
        #   >= 0.80  : likely paraphrase -> medium risk (human glance)
        #   < 0.80   : likely a content change (polarity flip, swapped
        #              referent, new claim) -> high risk (human review)
        if sim < 0.80:
            risk = "high"
        elif sim < 0.95:
            risk = "medium"
        else:
            risk = "low"
        per_sentence.append({
            "old_idx": i,
            "new_idx": j,
            "old": os_,
            "new": new_sents[j],
            "similarity": round(sim, 3),
            "risk": risk,
        })
    overall = float(np.mean([p["similarity"] for p in per_sentence]))
    return {
        "overall_similarity": round(overall, 3),
        "per_sentence": per_sentence,
    }

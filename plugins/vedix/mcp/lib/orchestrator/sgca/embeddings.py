"""Embedding helpers — multilingual-e5-large. Production-grade calls go
through these wrappers; tests patch them."""
from __future__ import annotations
from functools import lru_cache


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("intfloat/multilingual-e5-large")


async def label_cosine(a: str, b: str) -> float:
    m = _model()
    import numpy as np
    va = m.encode([f"query: {a}"], normalize_embeddings=True)[0]
    vb = m.encode([f"query: {b}"], normalize_embeddings=True)[0]
    return float(np.dot(va, vb))


async def context_cosine(papers_a: list[str], papers_b: list[str]) -> float:
    # Mean embedding of sample sentences from each paper-set; cosine between means.
    # Stub returns 0.5 when contexts unavailable; full impl reads from kg_store.
    if not papers_a or not papers_b:
        return 0.5
    return 0.5  # See Task 5 integration for the full version.


async def llm_judge_synonymy(a: str, b: str) -> float:
    # Stub: routed through Block 2 ProviderRouter (`paragraph-planner` agent-class) in prod.
    return 0.5

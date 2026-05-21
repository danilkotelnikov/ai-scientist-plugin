from __future__ import annotations
from enum import Enum
from typing import Optional
from .schema import ConceptLatticeEntry


class MergeDecision(str, Enum):
    AUTO_MERGE = "auto_merge"
    SURFACE_CONFLICT = "surface_conflict"
    KEEP_DISTINCT = "keep_distinct"


def compute_merge_confidence(*, embedding_cosine: float, context_cosine: float, llm_judge: float) -> float:
    """SGCA §3.2: merge_confidence = 0.6*label + 0.3*context + 0.1*llm-judge."""
    return 0.6 * embedding_cosine + 0.3 * context_cosine + 0.1 * llm_judge


class LatticeMerger:
    def __init__(self, *, merge_threshold: float = 0.9, distinct_threshold: float = 0.5):
        self.merge_threshold = merge_threshold
        self.distinct_threshold = distinct_threshold

    async def decide(self, existing: ConceptLatticeEntry, incoming: ConceptLatticeEntry) -> MergeDecision:
        conf = await self._compute_confidence(existing, incoming)
        if conf >= self.merge_threshold:
            return MergeDecision.AUTO_MERGE
        if conf < self.distinct_threshold:
            return MergeDecision.KEEP_DISTINCT
        return MergeDecision.SURFACE_CONFLICT

    async def _compute_confidence(self, existing: ConceptLatticeEntry, incoming: ConceptLatticeEntry) -> float:
        # Stub: overridden in production by an embeddings + LLM-judge pipeline.
        # See Task 5/Task 8 for integration.
        from .embeddings import label_cosine, context_cosine, llm_judge_synonymy
        ec = await label_cosine(existing.canonical_label_en, incoming.canonical_label_en)
        cc = await context_cosine(existing.appears_in_papers, incoming.appears_in_papers)
        lj = await llm_judge_synonymy(existing.canonical_label_en, incoming.canonical_label_en)
        return compute_merge_confidence(embedding_cosine=ec, context_cosine=cc, llm_judge=lj)

    def apply_merge(self, existing: ConceptLatticeEntry, incoming: ConceptLatticeEntry) -> ConceptLatticeEntry:
        if existing.appearance_count >= incoming.appearance_count:
            canonical = existing
            alt = incoming
        else:
            canonical = incoming
            alt = existing
        return ConceptLatticeEntry(
            id=canonical.id,
            canonical_label_en=canonical.canonical_label_en,
            canonical_label_ru=canonical.canonical_label_ru or alt.canonical_label_ru,
            alt_labels=list({*canonical.alt_labels, *alt.alt_labels, alt.canonical_label_en}),
            broader=list({*canonical.broader, *alt.broader}),
            narrower=list({*canonical.narrower, *alt.narrower}),
            related=list({*canonical.related, *alt.related}),
            appears_in_papers=list({*canonical.appears_in_papers, *alt.appears_in_papers}),
            appearance_count=canonical.appearance_count + alt.appearance_count,
            drift_warning=canonical.drift_warning or alt.drift_warning,
        )

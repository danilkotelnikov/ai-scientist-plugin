from __future__ import annotations
from typing import Iterable
from .schema import AllowedSet, NodeId
from .kg_store import KGStore


async def _cosine(topic: str, paraphrase: str) -> float:
    """Stub for tests; production uses sentence-transformers."""
    from .embeddings import label_cosine
    return await label_cosine(topic, paraphrase)


class ParagraphPlanner:
    def __init__(self, *, store: KGStore, max_size: int = 30, min_relevance: float = 0.4):
        self.store = store
        self.max_size = max_size
        self.min_relevance = min_relevance

    async def compute(self, *, paragraph_id: str, paragraph_topic: str,
                      hypothesis_anchors: list[NodeId]) -> AllowedSet:
        candidates: list[tuple[NodeId, float]] = []
        for pid in self.store.list_paper_ids():
            paper = self.store.read_paper(pid)
            if paper is None:
                continue
            for c in paper.nodes.claims:
                cos = await _cosine(paragraph_topic, c.paraphrase)
                if cos >= self.min_relevance:
                    candidates.append((c.id, cos))
            for m in paper.nodes.methods:
                cos = await _cosine(paragraph_topic, m.paraphrase)
                if cos >= self.min_relevance:
                    candidates.append((m.id, cos * 0.8))  # slight down-weight vs claims

        candidates.sort(key=lambda np: np[1], reverse=True)
        ordered = [nid for nid, _ in candidates]

        # Pin hypothesis anchors at the front (deduped)
        seen: set[NodeId] = set()
        final: list[NodeId] = []
        for nid in list(hypothesis_anchors) + ordered:
            if nid in seen:
                continue
            seen.add(nid)
            final.append(nid)
            if len(final) >= self.max_size:
                break

        return AllowedSet(
            paragraph_id=paragraph_id,
            paragraph_topic=paragraph_topic,
            nodes=final,
            max_size=self.max_size,
            kg_revision_id=self.store.kg_revision_id(),
        )

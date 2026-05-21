import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.sgca.lattice_merger import (
    LatticeMerger, MergeDecision, compute_merge_confidence,
)
from plugins.vedix.mcp.lib.orchestrator.sgca.schema import ConceptLatticeEntry


def test_compute_merge_confidence_uses_60_30_10_weights():
    score = compute_merge_confidence(
        embedding_cosine=1.0, context_cosine=1.0, llm_judge=1.0,
    )
    assert score == pytest.approx(1.0)
    score = compute_merge_confidence(
        embedding_cosine=0.5, context_cosine=0.5, llm_judge=0.5,
    )
    assert score == pytest.approx(0.5)
    # 0.6*0.9 + 0.3*0.8 + 0.1*0.7 = 0.54 + 0.24 + 0.07 = 0.85
    score = compute_merge_confidence(
        embedding_cosine=0.9, context_cosine=0.8, llm_judge=0.7,
    )
    assert score == pytest.approx(0.85, abs=1e-6)


@pytest.mark.asyncio
async def test_auto_merge_above_threshold():
    existing = ConceptLatticeEntry(id="concept:foo", canonical_label_en="HOMO-LUMO gap",
                                    alt_labels=[], appearance_count=5)
    incoming = ConceptLatticeEntry(id="concept:bar", canonical_label_en="frontier orbital energy",
                                    alt_labels=[], appearance_count=1)
    merger = LatticeMerger(merge_threshold=0.9)
    with patch.object(merger, "_compute_confidence", new=AsyncMock(return_value=0.95)):
        decision = await merger.decide(existing, incoming)
        assert decision == MergeDecision.AUTO_MERGE


@pytest.mark.asyncio
async def test_surface_conflict_below_threshold():
    existing = ConceptLatticeEntry(id="concept:foo", canonical_label_en="catalysis", appearance_count=5)
    incoming = ConceptLatticeEntry(id="concept:bar", canonical_label_en="proteolysis", appearance_count=1)
    merger = LatticeMerger(merge_threshold=0.9)
    with patch.object(merger, "_compute_confidence", new=AsyncMock(return_value=0.65)):
        decision = await merger.decide(existing, incoming)
        assert decision == MergeDecision.SURFACE_CONFLICT


@pytest.mark.asyncio
async def test_distinct_below_lower_threshold():
    existing = ConceptLatticeEntry(id="concept:foo", canonical_label_en="catalysis", appearance_count=5)
    incoming = ConceptLatticeEntry(id="concept:bar", canonical_label_en="trampoline", appearance_count=1)
    merger = LatticeMerger(merge_threshold=0.9, distinct_threshold=0.3)
    with patch.object(merger, "_compute_confidence", new=AsyncMock(return_value=0.1)):
        decision = await merger.decide(existing, incoming)
        assert decision == MergeDecision.KEEP_DISTINCT


def test_merge_promotes_higher_appearance_count_as_canonical():
    existing = ConceptLatticeEntry(id="concept:foo", canonical_label_en="HOMO-LUMO gap", appearance_count=17)
    incoming = ConceptLatticeEntry(id="concept:bar", canonical_label_en="frontier orbital energy", appearance_count=1)
    merger = LatticeMerger(merge_threshold=0.9)
    merged = merger.apply_merge(existing, incoming)
    assert merged.canonical_label_en == "HOMO-LUMO gap"
    assert "frontier orbital energy" in merged.alt_labels
    assert merged.appearance_count == 18

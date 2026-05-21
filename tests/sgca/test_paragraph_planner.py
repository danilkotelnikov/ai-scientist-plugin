import pytest
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.sgca.paragraph_planner import ParagraphPlanner
from plugins.vedix.mcp.lib.orchestrator.sgca.kg_store import KGStore, Tier
from plugins.vedix.mcp.lib.orchestrator.sgca.schema import (
    KGFragment, KGNodes, Claim, Author, RawPointer, Provenance,
)


def _claim(pid, cid, paraphrase):
    return Claim(id=cid, type="empirical", paraphrase=paraphrase,
                 verbatim_quote="q", quote_byte_range=[0, 1],
                 page=1, section="Results", confidence=0.9, hedge=False,
                 provenance=Provenance(extractor_model="x", extractor_ts=0))


def _seed(store, papers):
    for pid, pp in papers:
        store.write_paper(KGFragment(
            paper_id=pid, doi=f"10/{pid}", title=pid, year=2024,
            authors=[Author(id=f"author:{pid}", name=pid)], language="en", license="CC-BY",
            raw_pointer=RawPointer(text=f"raw/{pid}.txt", byte_len=10),
            nodes=KGNodes(claims=[_claim(pid, f"{pid}.c1", pp)]),
            edges=[],
        ))


@pytest.mark.asyncio
async def test_allowed_set_returns_at_most_max_size(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="pp1")
    _seed(store, [(f"p{i}", f"claim about topic {i}") for i in range(50)])
    planner = ParagraphPlanner(store=store)

    async def _fake_cosine(topic, paraphrase):
        return 1.0 - 0.01 * int(paraphrase.rsplit(" ", 1)[-1])

    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.paragraph_planner._cosine",
               side_effect=_fake_cosine):
        allowed = await planner.compute(paragraph_id="para1",
                                        paragraph_topic="topic 0",
                                        hypothesis_anchors=[])
    assert len(allowed.nodes) <= allowed.max_size
    # First should be p0.c1 (cosine 1.0)
    assert "p0.c1" in allowed.nodes[:5]


@pytest.mark.asyncio
async def test_hypothesis_anchors_always_included(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="pp2")
    _seed(store, [(f"p{i}", f"claim {i}") for i in range(40)])
    planner = ParagraphPlanner(store=store)
    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.paragraph_planner._cosine",
               new=AsyncMock(return_value=0.5)):
        allowed = await planner.compute(paragraph_id="p", paragraph_topic="t",
                                        hypothesis_anchors=["p39.c1"])
    assert "p39.c1" in allowed.nodes


@pytest.mark.asyncio
async def test_kg_revision_id_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="pp3")
    _seed(store, [("a", "claim a")])
    planner = ParagraphPlanner(store=store)
    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.paragraph_planner._cosine",
               new=AsyncMock(return_value=0.9)):
        allowed = await planner.compute(paragraph_id="p", paragraph_topic="t", hypothesis_anchors=[])
    assert allowed.kg_revision_id == store.kg_revision_id()

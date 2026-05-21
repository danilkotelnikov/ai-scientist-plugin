import pytest
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.sgca.claim_verifier import ClaimVerifier
from plugins.vedix.mcp.lib.orchestrator.sgca.schema import (
    KGFragment, KGNodes, Claim, Author, RawPointer, Provenance,
    SentenceBucket, Anchor,
)
from plugins.vedix.mcp.lib.orchestrator.sgca.kg_store import KGStore, Tier


def _seed_one_claim(store):
    store.write_paper(KGFragment(
        paper_id="smith2024", doi="10.1/x", title="t", year=2024,
        authors=[Author(id="author:s", name="S")], language="en", license="CC-BY",
        raw_pointer=RawPointer(text="raw/x.txt", byte_len=10),
        nodes=KGNodes(claims=[
            Claim(id="smith2024.c1", type="empirical",
                  paraphrase="HOMO-LUMO gap correlates with DA rate (r=0.78)",
                  verbatim_quote="correlation r=0.78 between HOMO-LUMO gap and Diels-Alder rate",
                  quote_byte_range=[0, 60],
                  page=1, section="Results", confidence=0.9, hedge=False,
                  provenance=Provenance(extractor_model="x", extractor_ts=0)),
        ]),
        edges=[],
    ))


@pytest.mark.asyncio
async def test_cite_passes_when_entailed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="cv1")
    _seed_one_claim(store)
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1",
        text="Diels-Alder rate constants scale with HOMO-LUMO gap [smith2024.c1].",
        bucket="cite",
        anchors=[Anchor(node_id="smith2024.c1", anchor_role="primary")],
    )
    fake_judge = AsyncMock(return_value={"status": "pass", "score": 0.93,
                                         "rationale": "paraphrase faithful"})
    with patch.object(verifier, "_llm_entailment", new=fake_judge):
        result = await verifier.verify(sentence)
    assert result.verifier.status == "pass"
    assert result.verifier.entailment_score == pytest.approx(0.93)


@pytest.mark.asyncio
async def test_cite_fails_when_contradicts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="cv2")
    _seed_one_claim(store)
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1",
        text="Diels-Alder kinetics are independent of HOMO-LUMO gap [smith2024.c1].",
        bucket="cite",
        anchors=[Anchor(node_id="smith2024.c1", anchor_role="primary")],
    )
    fake_judge = AsyncMock(return_value={"status": "fail-entailment", "score": 0.1,
                                         "rationale": "sentence asserts opposite"})
    with patch.object(verifier, "_llm_entailment", new=fake_judge):
        result = await verifier.verify(sentence)
    assert result.verifier.status == "fail-entailment"


@pytest.mark.asyncio
async def test_cite_fails_when_anchor_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="cv3")
    _seed_one_claim(store)
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1",
        text="x",
        bucket="cite",
        anchors=[Anchor(node_id="nonexistent.c1", anchor_role="primary")],
    )
    result = await verifier.verify(sentence)
    assert result.verifier.status == "fail-bucket"
    assert "anchor not found in KG" in result.verifier.rationale

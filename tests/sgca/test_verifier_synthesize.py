import pytest
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.sgca.claim_verifier import ClaimVerifier
from plugins.vedix.mcp.lib.orchestrator.sgca.schema import (
    KGFragment, KGNodes, Claim, Author, RawPointer, Provenance,
    SentenceBucket, Anchor,
)
from plugins.vedix.mcp.lib.orchestrator.sgca.kg_store import KGStore, Tier


def _seed_two_claims(store):
    for pid, cid, paraphrase in [
        ("smith2024", "smith2024.c1", "HOMO-LUMO gap correlates with DA rate in electron-poor dienophiles"),
        ("jones2022", "jones2022.c4", "DFT predicts cycloaddition TS energy from MO overlap"),
    ]:
        store.write_paper(KGFragment(
            paper_id=pid, doi=f"10/{pid}", title=pid, year=2024,
            authors=[Author(id=f"author:{pid}", name=pid)], language="en", license="CC-BY",
            raw_pointer=RawPointer(text=f"raw/{pid}.txt", byte_len=10),
            nodes=KGNodes(claims=[
                Claim(id=cid, type="empirical", paraphrase=paraphrase,
                      verbatim_quote=paraphrase, quote_byte_range=[0, len(paraphrase)],
                      page=1, section="Results", confidence=0.9, hedge=False,
                      provenance=Provenance(extractor_model="x", extractor_ts=0)),
            ]),
            edges=[],
        ))


@pytest.mark.asyncio
async def test_synthesize_passes_when_path_nontrivial(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="syn1")
    _seed_two_claims(store)
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1",
        text="MO-derived energies predict both DA rate and cycloaddition TS, suggesting a unified frontier-orbital framework.",
        bucket="synthesize",
        anchors=[
            Anchor(node_id="smith2024.c1", anchor_role="support"),
            Anchor(node_id="jones2022.c4", anchor_role="support"),
        ],
        evidence_path="smith2024.c1 + jones2022.c4 -> frontier-orbital framework",
    )
    fake_judge = AsyncMock(return_value={"status": "pass",
                                         "synthesis_check": "pass",
                                         "rationale": "non-trivial integration"})
    with patch.object(verifier, "_llm_synthesis_judge", new=fake_judge):
        result = await verifier.verify(sentence)
    assert result.verifier.status == "pass"
    assert result.verifier.synthesis_check == "pass"


@pytest.mark.asyncio
async def test_synthesize_fails_when_trivial_restatement(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="syn2")
    _seed_two_claims(store)
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1",
        text="HOMO-LUMO gap correlates with DA rate in electron-poor dienophiles.",  # = anchor 0
        bucket="synthesize",
        anchors=[
            Anchor(node_id="smith2024.c1", anchor_role="support"),
            Anchor(node_id="jones2022.c4", anchor_role="support"),
        ],
        evidence_path="smith2024.c1 + jones2022.c4 -> restatement",
    )
    fake_judge = AsyncMock(return_value={"status": "fail-entailment",
                                         "synthesis_check": "trivial-restatement",
                                         "rationale": "sentence is verbatim anchor 0"})
    with patch.object(verifier, "_llm_synthesis_judge", new=fake_judge):
        result = await verifier.verify(sentence)
    assert result.verifier.synthesis_check == "trivial-restatement"


@pytest.mark.asyncio
async def test_synthesize_requires_two_anchors(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Pydantic validator on SentenceBucket should reject construction
    with pytest.raises(Exception):
        SentenceBucket(sentence_id="s1", text="x", bucket="synthesize",
                       anchors=[Anchor(node_id="smith2024.c1", anchor_role="support")])

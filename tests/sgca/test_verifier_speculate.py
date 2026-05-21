import pytest
import time
from plugins.vedix.mcp.lib.orchestrator.sgca.claim_verifier import ClaimVerifier
from plugins.vedix.mcp.lib.orchestrator.sgca.schema import (
    SentenceBucket, SpeculationAuthorization,
)
from plugins.vedix.mcp.lib.orchestrator.sgca.kg_store import KGStore, Tier


@pytest.mark.asyncio
async def test_speculate_passes_when_setup_form_authorized(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="sp1")
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1", text="We hypothesize that X causes Y.", bucket="speculate",
        anchors=[],
        hedge_language="we hypothesize that",
        authorization=SpeculationAuthorization(
            source="setup_form", authorized_at=time.time() - 100, authorized_by="me@x"),
    )
    result = await verifier.verify(sentence)
    assert result.verifier.status == "pass"


@pytest.mark.asyncio
async def test_speculate_fails_when_no_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="sp2")
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1", text="We hypothesize that X causes Y.", bucket="speculate",
        anchors=[], hedge_language="we hypothesize that",
    )
    result = await verifier.verify(sentence)
    assert result.verifier.status == "pending-user-approval"


@pytest.mark.asyncio
async def test_speculate_fails_without_hedge_language(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = KGStore(tier=Tier.JOB, scope_id="sp3")
    verifier = ClaimVerifier(store=store)
    sentence = SentenceBucket(
        sentence_id="s1", text="X causes Y.", bucket="speculate", anchors=[],
        authorization=SpeculationAuthorization(
            source="setup_form", authorized_at=time.time(), authorized_by="me@x"),
    )
    result = await verifier.verify(sentence)
    assert result.verifier.status == "fail-bucket"
    assert "hedge_language required" in result.verifier.rationale or "hedge_language" in result.verifier.rationale

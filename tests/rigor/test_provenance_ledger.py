"""Tests for §4.7 provenance ledger + auto-disclosure."""
from __future__ import annotations

from plugins.vedix.mcp.lib.orchestrator.provenance_ledger import (
    ProvenanceLedger, generate_disclosure,
)


def test_record_and_load(tmp_path):
    ledger = ProvenanceLedger(path=tmp_path / "provenance.jsonl")
    ledger.record(
        sentence_id="s1", sentence="The cat sat.",
        agent="manuscript-writer", model="claude-opus-4",
        evidence=["ref1"], reflection_rounds=2,
    )
    entries = ledger.load_all()
    assert len(entries) == 1
    assert entries[0]["agent"] == "manuscript-writer"


def test_generate_disclosure_for_preprint(tmp_path):
    ledger = ProvenanceLedger(path=tmp_path / "provenance.jsonl")
    ledger.record(
        sentence_id="s1", sentence="Drafted.",
        agent="manuscript-writer", model="claude-opus-4",
        evidence=[], reflection_rounds=1,
    )
    ledger.record(
        sentence_id="s2", sentence="Audited.",
        agent="manuscript-writer", model="claude-opus-4",
        evidence=["smith2024"], reflection_rounds=2,
    )
    out = tmp_path / "AI_disclosure.md"
    generate_disclosure(
        ledger_path=tmp_path / "provenance.jsonl",
        venue="preprint", out=out,
    )
    text = out.read_text(encoding="utf-8")
    assert "Vedix" in text
    assert "claude-opus-4" in text
    assert "manuscript-writer" in text

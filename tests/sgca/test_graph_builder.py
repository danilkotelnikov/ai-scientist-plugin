import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.sgca.graph_builder import GraphBuilder, ExtractionFailure
from plugins.vedix.mcp.lib.orchestrator.sgca.kg_store import KGStore, Tier

FAKE_PAPER_TEXT = "Smith et al. report a correlation r=0.78 between HOMO-LUMO gap and Diels-Alder rate."

FAKE_EXTRACTION_YAML = """
paper_id: smith2024
doi: 10.1/x
title: t
year: 2024
authors:
  - {id: "author:smith", name: "J Smith"}
venue: J
language: en
license: CC-BY
raw_pointer:
  text: raw/smith2024.txt
  byte_len: 90
nodes:
  claims:
    - id: smith2024.claim01
      type: empirical
      paraphrase: HOMO-LUMO gap correlates with Diels-Alder rate
      verbatim_quote: "correlation r=0.78 between HOMO-LUMO gap and Diels-Alder rate"
      quote_byte_range: [22, 83]
      page: 1
      section: Results
      confidence: 0.92
      hedge: false
      entities: []
      methods: []
      limitations: []
      provenance: {extractor_model: stub, extractor_ts: 0}
  methods: []
  results: []
  limitations: []
  entities: []
edges:
  - {from: "paper:smith2024", to: "smith2024.claim01", kind: contains}
"""


@pytest.mark.asyncio
async def test_graph_builder_extracts_one_paper(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "smith2024.txt").write_text(FAKE_PAPER_TEXT, encoding="utf-8")

    paper_list = [{"id": "smith2024", "doi": "10.1/x", "title": "t",
                   "raw_text_path": str(raw_dir / "smith2024.txt")}]

    store = KGStore(tier=Tier.JOB, scope_id="job123")
    builder = GraphBuilder(store=store, concurrency=2)

    fake_response = type("R", (), {"content": FAKE_EXTRACTION_YAML.strip()})()
    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.graph_builder.dispatch_agent",
               new=AsyncMock(return_value=fake_response)):
        report = await builder.run(paper_list=paper_list)

    assert report["extracted"] == 1
    assert report["failed"] == 0
    loaded = store.read_paper("smith2024")
    assert loaded is not None
    assert loaded.nodes.claims[0].id == "smith2024.claim01"


@pytest.mark.asyncio
async def test_verbatim_quote_validation_rejects_drift(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    # Raw text that does NOT contain the claimed quote
    (raw_dir / "smith2024.txt").write_text("totally unrelated content", encoding="utf-8")
    paper_list = [{"id": "smith2024", "doi": "10.1/x", "title": "t",
                   "raw_text_path": str(raw_dir / "smith2024.txt")}]
    store = KGStore(tier=Tier.JOB, scope_id="job_drift")
    builder = GraphBuilder(store=store, concurrency=2, max_retries=1)
    fake_response = type("R", (), {"content": FAKE_EXTRACTION_YAML.strip()})()
    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.graph_builder.dispatch_agent",
               new=AsyncMock(return_value=fake_response)):
        report = await builder.run(paper_list=paper_list)
    assert report["extracted"] == 0
    assert report["failed"] == 1
    assert any("verbatim quote not found in raw" in f["reason"] for f in report["failures"])


@pytest.mark.asyncio
async def test_schema_violation_retried_once_then_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "p.txt").write_text("text", encoding="utf-8")
    paper_list = [{"id": "p", "doi": "10.1/p", "title": "t",
                   "raw_text_path": str(raw_dir / "p.txt")}]
    store = KGStore(tier=Tier.JOB, scope_id="job_bad")
    builder = GraphBuilder(store=store, concurrency=1, max_retries=1)
    # Both attempts return invalid YAML
    bad_response = type("R", (), {"content": "not valid yaml schema {{"})()
    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.graph_builder.dispatch_agent",
               new=AsyncMock(return_value=bad_response)):
        report = await builder.run(paper_list=paper_list)
    assert report["failed"] == 1

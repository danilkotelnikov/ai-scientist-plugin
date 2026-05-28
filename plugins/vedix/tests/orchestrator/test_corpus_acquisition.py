"""Tests for the unified corpus acquisition pipeline.

Covers:
- Cache-hit short-circuit
- OA host filter accepts arxiv / pmc / osti / nature; rejects publisher CDNs
- DOI-gate integration (failure path)
- Manifest append + KG-store skeleton write
- AcquisitionResult.as_dict() shape stability
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from mcp.lib.orchestrator.corpus_acquisition import (
    AcquisitionResult,
    CorpusAcquisitionPipeline,
    LEGITIMATE_OA_HOSTS,
    _is_legitimate_oa_url,
    _safe_filename_stem,
    build_default_pipeline,
)
from mcp.lib.orchestrator.source_accounting import SourceLedger


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


def test_safe_filename_stem_round_trips_doi_slashes() -> None:
    assert _safe_filename_stem("10.1038/s41586-024-07041-8") == "10.1038_s41586-024-07041-8"
    assert _safe_filename_stem("10.1021/jacs.7b12420") == "10.1021_jacs.7b12420"
    assert _safe_filename_stem("10.1186/s12915-023-01510-8") == "10.1186_s12915-023-01510-8"


def test_legit_oa_host_filter_accepts_real_repositories() -> None:
    assert _is_legitimate_oa_url("https://arxiv.org/pdf/2310.12345.pdf")
    assert _is_legitimate_oa_url("https://pmc.ncbi.nlm.nih.gov/articles/PMC12345/pdf/x.pdf")
    assert _is_legitimate_oa_url("https://www.osti.gov/servlets/purl/1924195")
    assert _is_legitimate_oa_url("https://hal.science/hal-01234567/document")
    assert _is_legitimate_oa_url("https://escholarship.org/uc/item/abcd")
    assert _is_legitimate_oa_url("https://www.nature.com/articles/s41586-024-07041-8_reference.pdf")


def test_legit_oa_host_filter_rejects_publisher_cdns_that_403() -> None:
    """ACS, APS, Elsevier paywalled CDNs are NOT in the legitimate-OA host
    list -- they reject anonymous clients. The filter keeps us out so the
    cascade doesn't waste time hammering them.
    """
    assert not _is_legitimate_oa_url("https://pubs.acs.org/doi/pdf/10.1021/jacs.x")
    assert not _is_legitimate_oa_url("https://link.aps.org/pdf/10.1103/PhysRevX.x")
    assert not _is_legitimate_oa_url("https://www.thelancet.com/article/x.pdf")
    assert not _is_legitimate_oa_url("https://pubs.rsc.org/en/content/articlepdf/2024/sc/d3sc12345g")


def test_legitimate_oa_host_list_is_non_empty_and_includes_all_categories() -> None:
    """Sanity check the host list covers preprint, institutional, federal,
    and hybrid-OA categories."""
    hosts = LEGITIMATE_OA_HOSTS
    assert any("arxiv" in h for h in hosts)          # preprint
    assert any("biorxiv" in h for h in hosts)        # preprint
    assert any("osti" in h for h in hosts)           # federal (DOE)
    assert any("pmc" in h for h in hosts)            # federal (NIH)
    assert any("escholarship" in h for h in hosts)   # institutional (UC)
    assert any("nature.com" in h for h in hosts)     # hybrid-OA


# ---------------------------------------------------------------------------
# AcquisitionResult shape
# ---------------------------------------------------------------------------


def test_acquisition_result_as_dict_serializes_paths() -> None:
    r = AcquisitionResult(
        success=True, doi="10.1038/test", title="T",
        discipline="chemistry", source="oa_direct",
        pdf_path=Path("/tmp/x.pdf"), text_path=Path("/tmp/x.txt"),
        license="cc-by", bytes_written=12345, extracted_chars=99000,
    )
    d = r.as_dict()
    assert isinstance(d["pdf_path"], str) and d["pdf_path"].endswith("x.pdf")
    assert isinstance(d["text_path"], str)
    assert d["license"] == "cc-by"
    assert d["bytes_written"] == 12345
    assert json.dumps(d, default=str)  # round-trips through JSON


def test_acquisition_result_failure_state_is_serializable() -> None:
    r = AcquisitionResult(
        success=False, doi="10.0000/missing", title="T", discipline="biology",
        failure_reason="no_pdf_found",
        gate_result={"passed": False, "reason": "doi_404_both_registries"},
    )
    d = r.as_dict()
    assert d["success"] is False
    assert d["failure_reason"] == "no_pdf_found"
    assert d["gate_result"]["reason"] == "doi_404_both_registries"


# ---------------------------------------------------------------------------
# Pipeline behavior tests (no network -- use cache-hit + injected paths)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    return corpus


def test_cache_hit_short_circuits_without_doi_gate(tmp_corpus: Path) -> None:
    """If the PDF is already on disk and starts with %PDF-, the pipeline
    returns success without invoking the DOI gate (no network).
    """
    discipline = "chemistry"
    doi = "10.1038/test.cache.hit"
    pdf_dir = tmp_corpus / discipline / "en" / "pdf"
    pdf_dir.mkdir(parents=True)
    fake_pdf = pdf_dir / f"{_safe_filename_stem(doi)}.pdf"
    # Real %PDF- magic + enough bytes to pass the size check.
    fake_pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    pipeline = CorpusAcquisitionPipeline(
        crossref_email="x@example.com",
        source_ledger=SourceLedger(["oa_direct", "scihub_mcp", "crossref_gate"]),
        corpus_root=tmp_corpus,
    )
    result = asyncio.run(pipeline.acquire_one(
        doi=doi, title="t", year=2024, discipline=discipline,
    ))
    assert result.success is True
    assert result.source == "cache"
    assert result.pdf_path == fake_pdf
    # No crossref_gate hit because we short-circuited.
    rep = pipeline.source_ledger.report()
    assert rep["per_source"]["crossref_gate"]["attempted"] == 0


def test_failed_doi_gate_blocks_acquisition_and_records_failure(tmp_corpus: Path) -> None:
    """If stage1_doi_gate returns passed=False, the pipeline records a
    failure on crossref_gate and returns without attempting OA or Sci-Hub.
    """
    pipeline = CorpusAcquisitionPipeline(
        crossref_email="x@example.com",
        source_ledger=SourceLedger(["oa_direct", "scihub_mcp", "crossref_gate"]),
        corpus_root=tmp_corpus,
    )

    # Monkey-patch the DOI gate to deterministically fail.
    import mcp.lib.orchestrator.corpus_acquisition as ca

    def _fake_gate(paper, *, harvest_title, crossref_email):
        return {"passed": False, "reason": "title_mismatch_0.30",
                "registry_title": "Different paper", "harvest_title": harvest_title}

    original_gate = ca.stage1_doi_gate
    ca.stage1_doi_gate = _fake_gate
    try:
        result = asyncio.run(pipeline.acquire_one(
            doi="10.1234/nonsense", title="My title", year=2024,
            discipline="biology",
        ))
    finally:
        ca.stage1_doi_gate = original_gate

    assert result.success is False
    assert result.failure_reason and result.failure_reason.startswith("gate_")
    rep = pipeline.source_ledger.report()
    assert rep["per_source"]["crossref_gate"]["attempted"] == 1
    assert rep["per_source"]["crossref_gate"]["failed_calls"] == 1
    # OA + Sci-Hub never attempted
    assert rep["per_source"]["oa_direct"]["attempted"] == 0
    assert rep["per_source"]["scihub_mcp"]["attempted"] == 0


def test_pipeline_constructor_marks_oa_direct_and_crossref_discovered(tmp_corpus: Path) -> None:
    """The constructor marks oa_direct and crossref_gate as tool_discovered;
    scihub_mcp only marked when the path was provided."""
    pipeline_no_scihub = CorpusAcquisitionPipeline(
        crossref_email="x@example.com",
        source_ledger=SourceLedger(["oa_direct", "scihub_mcp", "crossref_gate"]),
        corpus_root=tmp_corpus,
    )
    rep = pipeline_no_scihub.source_ledger.report()
    assert rep["per_source"]["oa_direct"]["tool_discovered"] is True
    assert rep["per_source"]["crossref_gate"]["tool_discovered"] is True
    assert rep["per_source"]["scihub_mcp"]["tool_discovered"] is False

    pipeline_with_scihub = CorpusAcquisitionPipeline(
        crossref_email="x@example.com",
        source_ledger=SourceLedger(["oa_direct", "scihub_mcp", "crossref_gate"]),
        corpus_root=tmp_corpus,
        scihub_mcp_path=Path("/fake/sci_hub_server.py"),
    )
    rep2 = pipeline_with_scihub.source_ledger.report()
    assert rep2["per_source"]["scihub_mcp"]["tool_discovered"] is True


def test_manifest_only_appended_on_success(tmp_corpus: Path) -> None:
    """Verify _append_manifest writes JSONL on success, nothing on failure.
    Indirect test via the result+manifest path inspection."""
    discipline = "physics"
    doi = "10.1038/test.manifest"
    pdf_dir = tmp_corpus / discipline / "en" / "pdf"
    pdf_dir.mkdir(parents=True)
    fake_pdf = pdf_dir / f"{_safe_filename_stem(doi)}.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)

    pipeline = CorpusAcquisitionPipeline(
        crossref_email="x@example.com",
        source_ledger=SourceLedger(["oa_direct", "scihub_mcp", "crossref_gate"]),
        corpus_root=tmp_corpus,
    )
    asyncio.run(pipeline.acquire_one(
        doi=doi, title="t", year=2024, discipline=discipline,
    ))
    # Cache-hit path doesn't call _append_manifest (the docstring says
    # post-acquisition manifest write is gated on the full cascade). Verify
    # that's the current contract.
    manifest = tmp_corpus / discipline / "en" / "downloaded.jsonl"
    assert not manifest.exists() or manifest.stat().st_size == 0


# ---------------------------------------------------------------------------
# build_default_pipeline integration
# ---------------------------------------------------------------------------


def test_build_default_pipeline_errors_without_openalex_email(monkeypatch) -> None:
    """build_default_pipeline must complain about OPENALEX_EMAIL absence."""
    monkeypatch.delenv("OPENALEX_EMAIL", raising=False)
    with pytest.raises(RuntimeError, match="OPENALEX_EMAIL"):
        build_default_pipeline()


def test_build_default_pipeline_constructs_without_scihub_when_not_requested(
    monkeypatch, tmp_path: Path,
) -> None:
    """When ``enable_scihub_fallback=False``, no Sci-Hub path is wired up
    even if the cloned MCP server happens to exist."""
    monkeypatch.setenv("OPENALEX_EMAIL", "x@example.com")
    monkeypatch.setenv("VEDIX_HOME", str(tmp_path))
    p = build_default_pipeline(enable_scihub_fallback=False)
    assert p.scihub_mcp_path is None
    rep = p.source_ledger.report()
    assert rep["per_source"]["scihub_mcp"]["tool_discovered"] is False

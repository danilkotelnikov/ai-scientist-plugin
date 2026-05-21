# tests/orchestrator/v2_1/test_cross_validator_stage1.py
import pytest
from unittest.mock import patch, MagicMock
from mcp.lib.orchestrator.cross_validator import (
    DOI_REGEX, stage1_doi_gate, normalize_doi,
)


def test_doi_regex_accepts_well_formed():
    assert DOI_REGEX.match("10.1038/s41586-024-12345-6")
    assert DOI_REGEX.match("10.1109/CVPR.2024.00001")
    assert DOI_REGEX.match("10.48550/arXiv.2401.12345")


def test_doi_regex_rejects_malformed():
    assert not DOI_REGEX.match("not-a-doi")
    assert not DOI_REGEX.match("10/short")
    assert not DOI_REGEX.match("https://doi.org/10.1038/example")


def test_normalize_doi_strips_url_prefix():
    assert normalize_doi("https://doi.org/10.1038/s41586") == "10.1038/s41586"
    assert normalize_doi("doi:10.1038/s41586") == "10.1038/s41586"
    assert normalize_doi("10.1038/s41586") == "10.1038/s41586"
    assert normalize_doi("  10.1038/S41586  ") == "10.1038/s41586"


def test_stage1_drops_paper_with_no_doi():
    paper = {"title": "Test paper", "doi": ""}
    result = stage1_doi_gate(paper, harvest_title="Test paper", crossref_email="t@e.com")
    assert result["passed"] is False
    assert result["reason"] == "no_doi"


def test_stage1_drops_on_title_mismatch():
    fake_get = MagicMock(return_value=MagicMock(
        status_code=200,
        json=lambda: {"message": {"title": ["Completely Different Title"]}},
    ))
    paper = {"doi": "10.1038/s41586-test", "title": "Original Title"}
    with patch("mcp.lib.orchestrator.cross_validator.httpx.get", fake_get):
        result = stage1_doi_gate(paper, harvest_title="Original Title",
                                 crossref_email="t@e.com")
    assert result["passed"] is False
    assert "title_mismatch" in result["reason"]


def test_stage1_passes_on_good_match():
    fake_get = MagicMock(return_value=MagicMock(
        status_code=200,
        json=lambda: {"message": {"title": ["Original Paper Title"]}},
    ))
    paper = {"doi": "10.1038/s41586-test", "title": "Original Paper Title"}
    with patch("mcp.lib.orchestrator.cross_validator.httpx.get", fake_get):
        result = stage1_doi_gate(paper, harvest_title="Original Paper Title",
                                 crossref_email="t@e.com")
    assert result["passed"] is True
    assert result["doi"] == "10.1038/s41586-test"
    assert result["title_score"] >= 0.85


def test_stage1_drops_on_crossref_404():
    fake_get = MagicMock(return_value=MagicMock(status_code=404, json=lambda: {}))
    paper = {"doi": "10.1038/nonexistent", "title": "Anything"}
    with patch("mcp.lib.orchestrator.cross_validator.httpx.get", fake_get):
        with patch("mcp.lib.orchestrator.cross_validator._datacite_resolves",
                   return_value=None):
            result = stage1_doi_gate(paper, harvest_title="Anything",
                                     crossref_email="t@e.com")
    assert result["passed"] is False
    assert "doi_404" in result["reason"]

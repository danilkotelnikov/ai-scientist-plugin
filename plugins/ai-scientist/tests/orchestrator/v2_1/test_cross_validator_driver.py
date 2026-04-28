# tests/orchestrator/v2_1/test_cross_validator_driver.py
from unittest.mock import patch, MagicMock
from mcp.lib.orchestrator.cross_validator import validate_corpus


def test_validate_corpus_drops_no_doi_papers():
    papers = [
        {"key": "A", "doi": "10.1/x", "title": "A paper"},
        {"key": "B", "doi": "", "title": "B paper"},
        {"key": "C", "doi": "10.1/y", "title": "C paper"},
    ]
    with patch("mcp.lib.orchestrator.cross_validator._crossref_resolve") as cr:
        cr.return_value = {"title": ["A paper"]}  # all titles match
        with patch("mcp.lib.orchestrator.cross_validator._openalex_get",
                   return_value=None):
            with patch("mcp.lib.orchestrator.cross_validator._semantic_scholar_get",
                       return_value=None):
                report = validate_corpus(papers, crossref_email="t@e.com",
                                         openalex_email="t@e.com",
                                         semantic_scholar_key=None,
                                         annas_enabled=False,
                                         consensus_enabled=False,
                                         pubmed_enabled=False)
    assert report["total_papers"] == 3
    assert report["doi_gate_passed"] == 2
    assert any(d["key"] == "B" for d in report["dropped"])
    assert len(report["validated"]) == 2


def test_validate_corpus_emits_status_field():
    papers = [{"key": "A", "doi": "10.1/x", "title": "A"}]
    with patch("mcp.lib.orchestrator.cross_validator._crossref_resolve",
               return_value={"title": ["A"]}):
        with patch("mcp.lib.orchestrator.cross_validator._openalex_get",
                   return_value={"title": "A", "year": 2024,
                                 "authors": ["X"], "venue": "V",
                                 "abstract": "abstr",
                                 "oa_url": "u", "oa_status": "open"}):
            with patch("mcp.lib.orchestrator.cross_validator._semantic_scholar_get",
                       return_value=None):
                report = validate_corpus(papers, crossref_email="t@e.com",
                                         openalex_email="t@e.com",
                                         semantic_scholar_key=None,
                                         annas_enabled=False,
                                         consensus_enabled=False,
                                         pubmed_enabled=False)
    assert report["validated"][0]["status"] in ("validated", "unverified")

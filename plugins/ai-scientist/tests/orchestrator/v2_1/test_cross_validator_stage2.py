# tests/orchestrator/v2_1/test_cross_validator_stage2.py
import pytest
from unittest.mock import patch, MagicMock
from mcp.lib.orchestrator.cross_validator import stage2_enrich, ENRICH_FIELDS


def test_enrich_uses_openalex_first():
    paper = {"doi": "10.1038/test", "title": "T"}
    fake_oa = {"title": "T", "authorships": [{"author": {"display_name": "A"}}],
               "publication_year": 2024,
               "host_venue": {"display_name": "Nature"},
               "abstract_inverted_index": {"hello": [0]},
               "open_access": {"is_oa": True, "oa_url": "https://x.com/y.pdf"}}
    with patch("mcp.lib.orchestrator.cross_validator._openalex_get",
               return_value=fake_oa):
        with patch("mcp.lib.orchestrator.cross_validator._semantic_scholar_get",
                   return_value=None):
            out = stage2_enrich(paper, openalex_email="t@e.com",
                                semantic_scholar_key=None,
                                consensus_enabled=False, annas_enabled=False,
                                pubmed_enabled=False)
    assert out["abstract"]
    assert out["year"] == 2024
    assert "openalex" in out["enriched_from"]


def test_enrich_falls_back_to_semantic_scholar_for_abstract():
    paper = {"doi": "10.1038/test"}
    with patch("mcp.lib.orchestrator.cross_validator._openalex_get",
               return_value={"title": "T"}):
        with patch("mcp.lib.orchestrator.cross_validator._semantic_scholar_get",
                   return_value={"abstract": "S2 abstract", "tldr": {"text": "tldr"}}):
            out = stage2_enrich(paper, openalex_email="t@e.com",
                                semantic_scholar_key="key",
                                consensus_enabled=False, annas_enabled=False,
                                pubmed_enabled=False)
    assert out["abstract"] == "S2 abstract"
    assert out["s2_tldr"] == "tldr"
    assert "semantic_scholar" in out["enriched_from"]


def test_enrich_skips_annas_for_closed_access():
    paper = {"doi": "10.1038/test", "oa_status": "closed"}
    annas_called = MagicMock()
    with patch("mcp.lib.orchestrator.cross_validator._openalex_get",
               return_value={}):
        with patch("mcp.lib.orchestrator.cross_validator._semantic_scholar_get",
                   return_value={}):
            with patch("mcp.lib.orchestrator.cross_validator._annas_extract_oa",
                       annas_called):
                stage2_enrich(paper, openalex_email="t@e.com",
                              semantic_scholar_key=None,
                              consensus_enabled=False, annas_enabled=True,
                              pubmed_enabled=False)
    annas_called.assert_not_called()


def test_enrich_uses_annas_for_open_access_with_missing_abstract():
    paper = {"doi": "10.1038/test", "oa_status": "open",
             "oa_url": "https://x.com/y.pdf"}
    with patch("mcp.lib.orchestrator.cross_validator._openalex_get",
               return_value={}):
        with patch("mcp.lib.orchestrator.cross_validator._semantic_scholar_get",
                   return_value={}):
            with patch("mcp.lib.orchestrator.cross_validator._annas_extract_oa",
                       return_value="OA full-text snippet here..."):
                out = stage2_enrich(paper, openalex_email="t@e.com",
                                    semantic_scholar_key=None,
                                    consensus_enabled=False,
                                    annas_enabled=True, pubmed_enabled=False)
    assert "OA full-text" in out.get("abstract", "")
    assert out["abstract_source"] == "fulltext_extraction"

"""Tests for §4.2 citation graph analytics."""
from __future__ import annotations

import pytest

pytest.importorskip("networkx")


def test_chronology_violation_detected():
    from plugins.vedix.mcp.lib.orchestrator.citation_graph import (
        chronology_violations,
    )
    references = {"smith2030": {"year": 2030, "venue": "Nature"}}
    citations_by_para = {"para1": ["smith2030"]}
    violations = chronology_violations(
        references, citations_by_para, manuscript_year=2026,
    )
    assert ("para1", "smith2030", 2030, 2026) in violations


def test_dangling_reference_detected():
    from plugins.vedix.mcp.lib.orchestrator.citation_graph import (
        dangling_references,
    )
    references = {"a2020": {"year": 2020}, "b2021": {"year": 2021}}
    citations_by_para = {"para1": ["a2020"]}
    dangling = dangling_references(references, citations_by_para)
    assert "b2021" in dangling
    assert "a2020" not in dangling


def test_self_citation_ratio():
    from plugins.vedix.mcp.lib.orchestrator.citation_graph import (
        self_citation_ratio,
    )
    references = {
        "smith2020": {"first_author": "Smith"},
        "jones2021": {"first_author": "Jones"},
        "smith2022": {"first_author": "Smith"},
    }
    citations_by_para = {"para1": ["smith2020", "jones2021", "smith2022"]}
    ratio = self_citation_ratio(
        references, citations_by_para, manuscript_authors=["Smith"],
    )
    assert ratio == pytest.approx(2 / 3)


def test_analyze_emits_report():
    from plugins.vedix.mcp.lib.orchestrator.citation_graph import analyze
    references = {
        "a2020": {"year": 2020, "first_author": "Smith", "venue": "Nature"},
    }
    citations_by_para = {"para1": ["a2020"]}
    paragraphs = {"para1": "we follow a2020 word " * 30}
    report = analyze(
        references=references,
        citations_by_para=citations_by_para,
        paragraphs=paragraphs,
        manuscript_year=2026,
        manuscript_authors=[],
    )
    assert "per_paragraph" in report
    assert "overall" in report

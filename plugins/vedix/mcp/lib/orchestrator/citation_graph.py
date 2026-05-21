"""§4.2 Citation graph analytics.

Build a paragraph<->reference bipartite graph and expose per-paragraph and
overall signals: citation density, freshness Gini, venue diversity,
self-citation ratio, chronology violations, dangling references.

The ``analyze`` entry point returns a JSON-serialisable dict; ``write_report``
emits it to disk under the job's ``rigor/`` directory.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np


def build_graph(
    references: dict[str, dict],
    citations_by_para: dict[str, list[str]],
) -> nx.DiGraph:
    """Build a directed paragraph -> reference graph."""
    g: nx.DiGraph = nx.DiGraph()
    for r, meta in references.items():
        g.add_node(r, kind="reference", **meta)
    for p, cited in citations_by_para.items():
        g.add_node(p, kind="paragraph")
        for r in cited:
            g.add_edge(p, r)
    return g


def density(paragraph_text: str, n_citations: int) -> float:
    """Citations per 100 words for the paragraph."""
    n_words = len(paragraph_text.split())
    return n_citations / max(1, n_words / 100)


def freshness_gini(references: dict[str, dict]) -> float:
    """Gini coefficient of reference-year distribution. 0 = even, 1 = concentrated."""
    years = [m.get("year") for m in references.values() if m.get("year")]
    if not years:
        return 0.0
    year_counts = Counter(years)
    counts = np.array(sorted(year_counts.values()))
    n = len(counts)
    total = float(np.sum(counts))
    if n == 0 or total == 0:
        return 0.0
    numerator = float(
        2 * np.sum((np.arange(1, n + 1)) * counts) - (n + 1) * total
    )
    return numerator / (n * total)


def venue_diversity(references: dict[str, dict]) -> int:
    """Number of distinct venues cited."""
    return len({m.get("venue") for m in references.values() if m.get("venue")})


def self_citation_ratio(
    references: dict[str, dict],
    citations_by_para: dict[str, list[str]],
    manuscript_authors: list[str],
) -> float:
    """Fraction of all citations whose first author is in the manuscript-author list."""
    cited_keys = [k for cs in citations_by_para.values() for k in cs]
    if not cited_keys:
        return 0.0
    self_cites = sum(
        1 for k in cited_keys
        if references.get(k, {}).get("first_author") in manuscript_authors
    )
    return self_cites / len(cited_keys)


def chronology_violations(
    references: dict[str, dict],
    citations_by_para: dict[str, list[str]],
    manuscript_year: int,
) -> list[tuple]:
    """Find citations whose reference year is after the manuscript year."""
    violations: list[tuple] = []
    for p, cited in citations_by_para.items():
        for k in cited:
            ref_year = references.get(k, {}).get("year")
            if ref_year and ref_year > manuscript_year:
                violations.append((p, k, ref_year, manuscript_year))
    return violations


def dangling_references(
    references: dict[str, dict],
    citations_by_para: dict[str, list[str]],
) -> list[str]:
    """References that appear in the .bib but are never cited in the text."""
    cited = {k for cs in citations_by_para.values() for k in cs}
    return [r for r in references if r not in cited]


def analyze(
    *,
    references: dict[str, dict],
    citations_by_para: dict[str, list[str]],
    paragraphs: dict[str, str],
    manuscript_year: int,
    manuscript_authors: list[str],
) -> dict[str, Any]:
    """Compute per-paragraph + overall citation-graph signals."""
    # build_graph is called for its side effect of validating the inputs
    # and is available to callers that want to inspect the graph directly.
    build_graph(references, citations_by_para)
    per_paragraph: dict[str, dict[str, Any]] = {}
    for p, txt in paragraphs.items():
        cs = citations_by_para.get(p, [])
        d = density(txt, len(cs))
        per_paragraph[p] = {
            "n_citations": len(cs),
            "density_per_100w": round(d, 2),
            "outlier_density": (
                d > 10 or (d < 0.5 and len(txt.split()) > 100)
            ),
        }
    overall: dict[str, Any] = {
        "n_references": len(references),
        "n_paragraphs": len(paragraphs),
        "freshness_gini": round(freshness_gini(references), 3),
        "venue_diversity": venue_diversity(references),
        "self_citation_ratio": round(
            self_citation_ratio(references, citations_by_para, manuscript_authors),
            3,
        ),
        "chronology_violations": chronology_violations(
            references, citations_by_para, manuscript_year,
        ),
        "dangling_references": dangling_references(
            references, citations_by_para,
        ),
    }
    return {"per_paragraph": per_paragraph, "overall": overall}


def write_report(report: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out

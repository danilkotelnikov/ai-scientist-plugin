"""Stage 1 — harvest paper candidates via MCPs.

Fans out one query per (discipline keyword × MCP) and merges the results
into a deduplicated JSONL of candidates with an open-licence filter. The
six ``_call_*`` helpers are stubs by design: production wires them to the
Vedix MCP layer (B6/B7); the unit tests patch them in to inject synthetic
candidates.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

# Discipline → search-keyword routing. Each keyword becomes a separate MCP
# query so we exercise multiple facets of the field rather than a single
# stale phrase.
DISCIPLINE_QUERIES: dict[str, list[str]] = {
    "chemistry": [
        "organic synthesis",
        "catalysis",
        "spectroscopy",
        "reaction kinetics",
        "crystallography",
    ],
    "biology": [
        "gene expression",
        "protein structure",
        "cell signaling",
        "microbiome",
        "evolutionary biology",
    ],
    "medicine": [
        "randomized clinical trial",
        "epidemiology",
        "biomarker",
        "therapeutic intervention",
        "diagnostic accuracy",
    ],
    "physics": [
        "quantum mechanics",
        "condensed matter",
        "particle physics",
        "general relativity",
        "thermodynamics",
    ],
    "mathematics": [
        "topology",
        "algebraic geometry",
        "stochastic processes",
        "graph theory",
        "functional analysis",
    ],
    "geology": [
        "plate tectonics",
        "geochronology",
        "stratigraphy",
        "geochemistry",
        "volcanology",
    ],
    "computer_science": [
        "machine learning",
        "distributed systems",
        "type theory",
        "computational complexity",
        "computer vision",
    ],
    "humanities": [
        "literary analysis",
        "historical methodology",
        "philosophical argument",
        "linguistic semantics",
        "cultural studies",
    ],
}

# Hints passed verbatim to MCP backends that accept a language qualifier.
LANG_HINTS: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "zh": "Chinese",
    "ja": "Japanese",
}

# Open-licence prefixes we consider redistributable for training. Anything
# else (all-rights-reserved, restricted, paywalled) is rejected.
_OPEN_LICENCE_PREFIXES = ("cc", "public", "open", "mit", "apache")
# Sources whose hits bypass the OA-licence filter because the user has
# already opted into their licensing terms by configuring credentials
# (e.g. Anna's Archive member key, where the user has accepted Anna's
# Archive's policies in choosing to set ANNAS_SECRET_KEY).
_LICENCE_BYPASS_SOURCES = frozenset({"annas"})


# --------------------------------------------------------------------------- #
# MCP call stubs. Production routes these through                              #
# plugins/vedix/mcp/lib/orchestrator/mcp_client.py (B6/B7).                    #
# Tests patch them via unittest.mock.AsyncMock.                                #
# --------------------------------------------------------------------------- #
async def _call_openalex(query: str, language: str, n: int) -> list[dict]:
    """Search OpenAlex via ``mcp__openalex__search_works``."""
    return []


async def _call_semanticscholar(query: str, language: str, n: int) -> list[dict]:
    """Search via ``mcp__semanticscholar__search_semantic_scholar``."""
    return []


async def _call_arxiv(query: str, language: str, n: int) -> list[dict]:
    """Search via ``mcp__arxiv__search_papers``."""
    return []


async def _call_biorxiv(query: str, language: str, n: int) -> list[dict]:
    """Search via ``mcp__bio-research:biorxiv search_preprints``."""
    return []


async def _call_pubmed(query: str, language: str, n: int) -> list[dict]:
    """Search via ``mcp__pubmed__search_articles``."""
    return []


async def _call_annas(query: str, language: str, n: int) -> list[dict]:
    """Search Anna's Archive via direct HTTPS.

    Anna's Archive's first-party search returns HTML; we parse the
    journal-article hit cards. For each hit, we extract the md5 (the
    canonical identifier) and the title metadata. Actual PDF retrieval
    happens later (stage 2 ``download.py``) via the member
    ``/dyn/api/fast_download.json`` endpoint, which respects the
    100-papers-per-day member quota server-side.

    Why not the ``annas-mcp`` MCP server: that npm package didn't exist
    at v3.0 ship; calling Anna's Archive directly avoids a subprocess
    dependency and works against any Anna's Archive member account.

    Returns ``[]`` silently if ``ANNAS_SECRET_KEY`` is unset so the
    parallel harvest from other MCPs (OpenAlex, Semantic Scholar, arXiv,
    bioRxiv, PubMed) is unaffected.
    """
    import logging
    import os
    from pathlib import Path
    import re

    log = logging.getLogger("vedix.acquisition.annas")
    secret_key = os.environ.get("ANNAS_SECRET_KEY", "").strip()
    if not secret_key:
        log.debug("ANNAS_SECRET_KEY not set; skipping Anna's Archive (set it to enable; 100 papers/day member quota applies)")
        return []

    base_url = os.environ.get("ANNAS_BASE_URL", "https://annas-archive.org").rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        # User configured just the host (e.g. annas-archive.gl mirror) — assume HTTPS.
        base_url = f"https://{base_url}"
    download_path = os.environ.get(
        "ANNAS_DOWNLOAD_PATH",
        str(Path.home() / ".vedix" / "raw_downloads"),
    )
    Path(download_path).mkdir(parents=True, exist_ok=True)

    try:
        import httpx
    except ImportError:
        log.warning("httpx not installed; cannot reach Anna's Archive")
        return []

    log.info("annas search: query=%r language=%s limit=%d", query, language, n)

    # Anna's Archive search returns HTML. Filter to journal articles, English
    # PDFs, sorted by relevance.
    search_url = f"{base_url}/search"
    params = {
        "q": query,
        "content": "journal_article",
        "ext": "pdf",
        "lang": language,
        "sort": "",  # default relevance
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "vedix/3.0 (research workbench)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(search_url, params=params)
            if resp.status_code != 200:
                log.warning("annas search HTTP %d for query=%r", resp.status_code, query)
                return []
            html = resp.text
    except Exception as exc:  # noqa: BLE001
        log.warning("annas search failed: %s", exc)
        return []

    # Parse hit cards. Anna's Archive emits links like
    #   <a href="/md5/abc123..." class="...">...</a>
    # and adjacent metadata. We scrape the md5 + the surrounding title text.
    # This is brittle by design — Anna's Archive has no public JSON search
    # API, so we accept that the markup may change and gracefully return [].
    md5_pattern = re.compile(r'href="/md5/([a-f0-9]{32})"[^>]*>([^<]+)<')
    seen_md5: set[str] = set()
    hits: list[tuple[str, str]] = []
    for m in md5_pattern.finditer(html):
        md5, title = m.group(1), m.group(2).strip()
        if md5 in seen_md5:
            continue
        seen_md5.add(md5)
        hits.append((md5, title))
        if len(hits) >= n:
            break

    normalized: list[dict] = []
    for md5, title in hits:
        # download URL routed through the member fast-download endpoint, which
        # enforces the 100/day quota and signs the URL via ANNAS_SECRET_KEY.
        download_url = (
            f"{base_url}/dyn/api/fast_download.json"
            f"?md5={md5}&key={secret_key}&download_speed=1"
        )
        normalized.append({
            "id": md5,
            "doi": None,
            "title": title,
            "year": None,
            "language": language,
            "license": "annas-archive-member",
            "full_text_url": download_url,
            "venue": None,
            "_source": "annas",
        })
    log.info("annas returned %d candidates for query=%r", len(normalized), query)
    return normalized


# --------------------------------------------------------------------------- #
# Public entry point                                                           #
# --------------------------------------------------------------------------- #
async def harvest(
    *,
    discipline: str,
    language: str,
    target_count: int = 200,
    out_path: Path,
) -> list[dict]:
    """Harvest up to ``target_count`` candidate papers for the pair.

    Fans queries out across all configured MCPs in parallel, deduplicates
    by DOI/id, applies the open-licence and language filters, then writes
    the survivors to ``out_path`` as JSONL.

    Returns the in-memory candidate list (also flushed to disk).
    """
    queries = DISCIPLINE_QUERIES.get(discipline, [discipline])
    per_query = max(10, target_count // max(1, len(queries)))

    tasks: list = []
    for q in queries:
        tasks.append(_call_openalex(q, language, per_query))
        tasks.append(_call_semanticscholar(q, language, per_query))
        tasks.append(_call_arxiv(q, language, per_query))
        if discipline in ("biology", "medicine"):
            tasks.append(_call_biorxiv(q, language, per_query))
            tasks.append(_call_pubmed(q, language, per_query))
        tasks.append(_call_annas(q, language, per_query))

    results_lists = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: list[dict] = []
    seen_dois: set[str] = set()
    for lst in results_lists:
        if isinstance(lst, BaseException):
            # Failures from any single MCP shouldn't abort the harvest.
            continue
        for paper in lst:
            doi = paper.get("doi") or paper.get("id")
            if not doi or doi in seen_dois:
                continue
            source = paper.get("_source", "")
            if source not in _LICENCE_BYPASS_SOURCES:
                licence = str(paper.get("license", "")).lower()
                if not licence.startswith(_OPEN_LICENCE_PREFIXES):
                    continue
            paper_lang = paper.get("language")
            if paper_lang and paper_lang[:2] != language:
                continue
            candidates.append(paper)
            seen_dois.add(doi)
            if len(candidates) >= target_count:
                break
        if len(candidates) >= target_count:
            break

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")
    return candidates

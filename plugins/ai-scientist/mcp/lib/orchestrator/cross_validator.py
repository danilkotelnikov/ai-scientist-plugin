"""Strict literature cross-validator. Per spec §4.

Stage 1: DOI gate (hard) — Crossref/DataCite resolve + fuzzy title match.
Stage 2: enrichment cascade (soft) — OpenAlex/S2/Consensus/Anna's OA-only/PubMed.
Stage 3: claim support (optional) — top-cited papers only.
"""
from __future__ import annotations
import re
import time
from typing import Optional

import httpx

DOI_REGEX = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")
TITLE_FUZZY_THRESHOLD = 0.85


def normalize_doi(raw: str) -> str:
    """Strip url prefix / doi: prefix; lowercase; strip whitespace."""
    s = (raw or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def _crossref_resolve(doi: str, email: str, timeout: float = 10.0) -> Optional[dict]:
    """Polite-pool Crossref resolve. Returns message dict or None."""
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": f"ai-scientist-plugin/2.1 (mailto:{email})"}
    try:
        r = httpx.get(url, headers=headers, timeout=timeout,
                      params={"mailto": email})
    except (httpx.RequestError, httpx.TimeoutException):
        return None
    if r.status_code == 200:
        return r.json().get("message") or {}
    return None


def _datacite_resolves(doi: str, timeout: float = 10.0) -> Optional[dict]:
    """DataCite fallback for non-Crossref DOIs."""
    url = f"https://api.datacite.org/dois/{doi}"
    try:
        r = httpx.get(url, timeout=timeout)
    except (httpx.RequestError, httpx.TimeoutException):
        return None
    if r.status_code == 200:
        attrs = r.json().get("data", {}).get("attributes", {})
        return {"title": [attrs.get("titles", [{}])[0].get("title", "")],
                "author": attrs.get("creators", []),
                "issued": {"date-parts": [[attrs.get("publicationYear")]]}}
    return None


def _fuzzy_title_match(a: str, b: str) -> float:
    """Token-sort-ratio normalized to [0, 1]."""
    try:
        from rapidfuzz.fuzz import token_sort_ratio
    except ImportError:
        # Fallback: lowercased equality
        return 1.0 if a.lower().strip() == b.lower().strip() else 0.0
    return token_sort_ratio(a, b) / 100.0


def stage1_doi_gate(paper: dict, *, harvest_title: str,
                    crossref_email: str) -> dict:
    """Stage 1 — strict DOI gate. Returns dict with passed: bool."""
    raw = paper.get("doi", "")
    doi = normalize_doi(raw)
    if not doi or not DOI_REGEX.match(doi):
        return {"passed": False, "reason": "no_doi"}
    cr = _crossref_resolve(doi, email=crossref_email)
    registry_data = cr
    if cr is None:
        # Try DataCite (datasets, preprints)
        dc = _datacite_resolves(doi)
        if dc is None:
            return {"passed": False, "reason": "doi_404_both_registries"}
        registry_data = dc
    registry_title = ""
    titles = registry_data.get("title", [])
    if isinstance(titles, list) and titles:
        registry_title = titles[0]
    score = _fuzzy_title_match(harvest_title, registry_title)
    if score < TITLE_FUZZY_THRESHOLD:
        return {"passed": False,
                "reason": f"title_mismatch_{score:.2f}",
                "registry_title": registry_title,
                "harvest_title": harvest_title}
    return {"passed": True, "doi": doi, "title_score": score,
            "registry_data": registry_data}


ENRICH_FIELDS = {"abstract", "authors", "year", "venue", "oa_url", "issn"}


def _reconstruct_abstract(inverted_index: dict) -> str:
    """OpenAlex stores abstracts as inverted indexes. Reconstruct."""
    if not inverted_index:
        return ""
    pos = []
    for word, positions in inverted_index.items():
        for p in positions:
            pos.append((p, word))
    pos.sort()
    return " ".join(w for _, w in pos)


def _openalex_get(doi: str, email: str, timeout: float = 10.0) -> Optional[dict]:
    """OpenAlex singleton lookup. Free with API key. Returns Work or None."""
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    try:
        r = httpx.get(url, params={"mailto": email}, timeout=timeout)
    except (httpx.RequestError, httpx.TimeoutException):
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    abstract = _reconstruct_abstract(data.get("abstract_inverted_index") or {})
    return {
        "title": data.get("title", ""),
        "authors": [a.get("author", {}).get("display_name", "")
                    for a in data.get("authorships", [])],
        "year": data.get("publication_year"),
        "venue": (data.get("host_venue") or {}).get("display_name", ""),
        "abstract": abstract,
        "oa_url": (data.get("open_access") or {}).get("oa_url"),
        "oa_status": "open" if (data.get("open_access") or {}).get("is_oa")
                     else "closed",
    }


def _semantic_scholar_get(doi: str, key: Optional[str],
                          timeout: float = 10.0) -> Optional[dict]:
    """Semantic Scholar single-paper lookup."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    fields = "title,authors,year,venue,abstract,tldr,openAccessPdf"
    headers = {"x-api-key": key} if key else {}
    try:
        r = httpx.get(url, headers=headers, params={"fields": fields},
                      timeout=timeout)
    except (httpx.RequestError, httpx.TimeoutException):
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    return {
        "title": data.get("title", ""),
        "authors": [a.get("name", "") for a in (data.get("authors") or [])],
        "year": data.get("year"),
        "venue": data.get("venue", ""),
        "abstract": data.get("abstract", ""),
        "tldr": data.get("tldr"),
        "oa_url": (data.get("openAccessPdf") or {}).get("url"),
    }


def _annas_extract_oa(doi: str, oa_url: str) -> Optional[str]:
    """Anna's Archive OA-only abstract extraction. Returns first 500 chars or None.

    Implementation note: in production, the orchestrator passes a callable
    that wraps mcp__annas-mcp__article_search. This stub is replaced at
    pipeline assembly time. Returning None signals 'no extraction'.
    """
    return None


def stage2_enrich(paper: dict, *, openalex_email: str,
                  semantic_scholar_key: Optional[str],
                  consensus_enabled: bool, annas_enabled: bool,
                  pubmed_enabled: bool) -> dict:
    """Stage 2 — soft enrichment cascade. Never drops papers; only fills fields."""
    enriched = dict(paper)
    enriched.setdefault("enriched_from", [])
    missing = lambda: ENRICH_FIELDS - {k for k in enriched
                                       if enriched.get(k)}
    doi = enriched.get("doi", "")

    # 2a — OpenAlex
    if missing():
        oa = _openalex_get(doi, email=openalex_email)
        if oa:
            # Normalize: reconstruct abstract from inverted index if needed
            if not oa.get("abstract") and oa.get("abstract_inverted_index"):
                oa = dict(oa)
                oa["abstract"] = _reconstruct_abstract(oa["abstract_inverted_index"])
            # Normalize: extract nested author names if authorships present
            if not oa.get("authors") and oa.get("authorships"):
                oa = dict(oa)
                oa["authors"] = [a.get("author", {}).get("display_name", "")
                                 for a in oa["authorships"]]
            # Normalize: extract year from publication_year
            if not oa.get("year") and oa.get("publication_year"):
                oa = dict(oa)
                oa["year"] = oa["publication_year"]
            # Normalize: extract venue from host_venue
            if not oa.get("venue") and oa.get("host_venue"):
                oa = dict(oa)
                hv = oa["host_venue"]
                oa["venue"] = hv.get("display_name", "") if isinstance(hv, dict) else str(hv)
            # Normalize: extract oa_url from open_access
            if not oa.get("oa_url") and oa.get("open_access"):
                oa = dict(oa)
                oa["oa_url"] = (oa["open_access"] or {}).get("oa_url")
                if not oa.get("oa_status"):
                    oa["oa_status"] = "open" if (oa.get("open_access") or {}).get("is_oa") else "closed"
            for k, v in oa.items():
                if v and not enriched.get(k):
                    enriched[k] = v
            if any(v for v in oa.values()):
                enriched["enriched_from"].append("openalex")

    # 2b — Semantic Scholar (best for abstract + tldr)
    if "abstract" in missing() or "oa_url" in missing():
        s2 = _semantic_scholar_get(doi, key=semantic_scholar_key)
        if s2:
            for k, v in s2.items():
                if v and not enriched.get(k):
                    enriched[k] = v
            if s2.get("tldr"):
                enriched["s2_tldr"] = s2["tldr"].get("text", "") if isinstance(
                    s2["tldr"], dict) else s2["tldr"]
            if any(v for v in s2.values()):
                enriched["enriched_from"].append("semantic_scholar")

    # 2c — Anna's Archive (OA-only)
    if annas_enabled and "abstract" in missing():
        if enriched.get("oa_status") == "open" and enriched.get("oa_url"):
            snippet = _annas_extract_oa(doi, enriched["oa_url"])
            if snippet:
                enriched["abstract"] = snippet
                enriched["abstract_source"] = "fulltext_extraction"
                enriched["enriched_from"].append("annas_archive")

    enriched["missing_after_enrich"] = sorted(missing())
    return enriched

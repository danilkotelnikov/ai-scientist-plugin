#!/usr/bin/env python3
"""Corpus scraper for paywalled content (Sci-Hub channel).

Two transport modes (``--via mcp`` or ``--via direct``; default direct):

* ``mcp`` -- talks to the cloned Sci-Hub MCP at
  ``~/.vedix/external/Sci-Hub-MCP-Server/sci_hub_server.py``. Use this
  when you want to round-trip through the same MCP the live pipeline
  uses, e.g. for end-to-end testing of the literature-searcher agent.

* ``direct`` -- bypasses the upstream ``scihub`` PyPI package (whose
  HTML parser hasn't been updated since the .tw/.is/.mn mirror era)
  and talks to ``sci-hub.ru`` directly via httpx. Pulls the embedded
  PDF URL out of the response page, then streams. This is the
  resilient path; it's what we use for corpus building.

Complements ``scrape_journals.py`` (Anna's Archive -- daily quota +
burst-rate limit) and ``scrape_oa.py`` (OpenAlex OA-direct -- only OA
papers). This script fetches the long tail of paywalled papers from
flagship venues (JACS, Cell, ACS, Angewandte, Chemical Reviews,
Physical Review X, ...) via the Sci-Hub MCP at
``~/.vedix/external/Sci-Hub-MCP-Server/sci_hub_server.py``.

Pipeline
--------
1. OpenAlex discovers the top-cited DOIs for each (journal, discipline)
   target (same query as ``scrape_journals.py``; no OA filter — we
   actively want paywalled content here).
2. The Sci-Hub MCP is spawned as a subprocess via
   ``corpus_lib.mcp_client.MCPClient``.
3. For each DOI: ``search_scihub_by_doi`` → ``pdf_url``;
   ``download_scihub_pdf(pdf_url, output_path)`` → PDF on disk.
4. pdfminer.six extracts plaintext.
5. Output lands at ``~/.vedix/corpus/<discipline>/en/`` so it merges
   with the existing Nature / OA-direct corpus.

Why this is useful
------------------
Anna's Archive throttles aggressively after ~40 requests/day per key.
Sci-Hub uses different mirrors and a different rate-limit shape; it
covers the same paywalled set with a different backoff curve, so
running both gives the corpus better odds of capturing flagship
paywalled venues that block anonymous publisher fetches (ACS, APS).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

# Reuse the existing async MCP stdio client.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_lib.mcp_client import MCPClient  # noqa: E402

# Reuse Nature scraper's OpenAlex discovery and helpers.
import httpx  # noqa: E402


USER_AGENT = "vedix/3.0 (research workbench)"

# Browser-like headers for the direct sci-hub.ru fetch. Some mirrors
# return a stripped response to obvious bot UAs; this matches a recent
# Chrome on Windows.
DIRECT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sci-hub.ru/",
}

# Default live mirrors. SCIHUB_BASE_URLS env var overrides (comma-sep).
DEFAULT_LIVE_MIRRORS = [
    "https://sci-hub.ru",
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://www.tesble.com",
]


def _live_mirrors() -> list[str]:
    raw = os.environ.get("SCIHUB_BASE_URLS", "").strip()
    if raw:
        return [m.strip().rstrip("/") for m in raw.split(",") if m.strip()]
    return list(DEFAULT_LIVE_MIRRORS)


async def direct_fetch_pdf_url(
    doi: str, *, client: httpx.AsyncClient, log: logging.Logger,
) -> str | None:
    """Resolve a DOI to a PDF URL via direct sci-hub.ru HTML scrape.

    Sci-Hub's response page embeds the PDF in either an ``<embed>``,
    ``<iframe>``, or a ``location.href`` JavaScript redirect. We try
    each mirror in order until one returns a parseable PDF URL.
    """
    for mirror in _live_mirrors():
        url = f"{mirror}/{doi}"
        try:
            r = await client.get(url, headers=DIRECT_HEADERS, timeout=30)
        except Exception as exc:  # noqa: BLE001
            log.debug("  %s unreachable: %s", mirror, exc)
            continue
        if r.status_code != 200:
            log.debug("  %s returned HTTP %d", mirror, r.status_code)
            continue
        html = r.text

        # Try in order: embed[src], iframe[src], plain location.href hint.
        pdf_url: str | None = None
        m = re.search(r'<embed[^>]+src\s*=\s*["\']([^"\']+\.pdf[^"\']*)', html, re.I)
        if not m:
            m = re.search(r'<iframe[^>]+src\s*=\s*["\']([^"\']+\.pdf[^"\']*)', html, re.I)
        if not m:
            m = re.search(r'location\.href\s*=\s*["\']([^"\']+\.pdf[^"\']*)', html, re.I)
        if m:
            pdf_url = m.group(1)
        if not pdf_url:
            log.debug("  %s: no PDF URL pattern matched in response", mirror)
            continue

        # Normalize. Sci-Hub returns either '//host/path' or '/path' or
        # an absolute URL.
        if pdf_url.startswith("//"):
            pdf_url = "https:" + pdf_url
        elif pdf_url.startswith("/"):
            pdf_url = mirror + pdf_url
        # Trim url-fragment '#' that some mirrors append.
        pdf_url = pdf_url.split("#")[0]
        log.info("  resolved via %s -> %s", mirror, pdf_url)
        return pdf_url

    log.warning("  no mirror returned a PDF URL for DOI=%s", doi)
    return None


async def direct_download_pdf(
    pdf_url: str, dest: Path, *, client: httpx.AsyncClient, log: logging.Logger,
) -> bool:
    """Stream a Sci-Hub PDF URL to disk; validate %PDF- magic bytes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        async with client.stream(
            "GET", pdf_url, headers=DIRECT_HEADERS, timeout=120, follow_redirects=True,
        ) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=64_000):
                    f.write(chunk)
    except Exception as exc:  # noqa: BLE001
        log.warning("  direct stream failed: %s", exc)
        if dest.exists():
            dest.unlink()
        return False

    if dest.stat().st_size < 1024:
        log.warning("  file too small (%d bytes); discarding", dest.stat().st_size)
        dest.unlink()
        return False
    if dest.read_bytes()[:5] != b"%PDF-":
        log.warning("  magic bytes mismatch; discarding")
        dest.unlink()
        return False
    return True


# Journal ISSNs paired with their canonical English discipline. These
# overlap with ``scrape_journals.JOURNAL_PRESETS`` but specifically
# target paywalled venues that Anna's and OA-direct couldn't capture.
JOURNAL_PRESETS: dict[str, dict[str, str]] = {
    "nature":          {"issn": "0028-0836", "full_name": "Nature"},
    "science":         {"issn": "0036-8075", "full_name": "Science"},
    "cell":            {"issn": "0092-8674", "full_name": "Cell"},
    "jacs":            {"issn": "0002-7863", "full_name": "Journal of the American Chemical Society"},
    "angewandte":      {"issn": "1433-7851", "full_name": "Angewandte Chemie International Edition"},
    "acs-catalysis":   {"issn": "2155-5435", "full_name": "ACS Catalysis"},
    "chem-reviews":    {"issn": "0009-2665", "full_name": "Chemical Reviews"},
    "acs-central":     {"issn": "2374-7943", "full_name": "ACS Central Science"},
    "phys-rev-x":      {"issn": "2160-3308", "full_name": "Physical Review X"},
    "phys-rev-letters":{"issn": "0031-9007", "full_name": "Physical Review Letters"},
    "nejm":            {"issn": "0028-4793", "full_name": "New England Journal of Medicine"},
    "lancet":          {"issn": "0140-6736", "full_name": "The Lancet"},
}


# Curated default mix targeting the gap: paywalled flagships that
# previous scrapes couldn't reach. 9 papers total.
DEFAULT_MIX: list[tuple[str, str, int]] = [
    ("jacs",            "chemistry",         1),
    ("angewandte",      "chemistry",         1),
    ("chem-reviews",    "chemistry",         1),
    ("acs-central",     "chemistry",         1),
    ("cell",            "biology",           1),
    ("phys-rev-x",      "physics",           1),
    ("phys-rev-letters","physics",           1),
    ("nejm",            "medicine",          1),
    ("science",         "computer_science",  1),
]


DISCIPLINE_CONCEPTS: dict[str, str] = {
    "chemistry":        "C185592680",
    "physics":          "C121332964",
    "biology":          "C86803240",
    "medicine":         "C71924100",
    "computer_science": "C41008148",
    "materials":        "C192562407",
    "geology":          "C127313418",
}


def _safe_stem(doi: str) -> str:
    """Turn a DOI into a filesystem-safe stem (no slashes etc.)."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", doi)


async def fetch_openalex_dois(
    *, issn: str, target: int, candidates: int, email: str,
    from_year: int, to_year: int | None,
    concept_id: str | None,
    log: logging.Logger,
) -> list[dict[str, Any]]:
    """Query OpenAlex for top-cited papers from a journal/discipline pair.

    Unlike :mod:`scrape_oa`, this does NOT filter on ``is_oa:true`` —
    we want paywalled flagship content here.
    """
    filter_parts = [
        f"primary_location.source.issn:{issn}",
        "type:article",
        "language:en",
        f"from_publication_date:{from_year}-01-01",
    ]
    if to_year is not None:
        filter_parts.append(f"to_publication_date:{to_year}-12-31")
    if concept_id is not None:
        filter_parts.append(f"concepts.id:{concept_id}")

    params = {
        "filter": ",".join(filter_parts),
        "per_page": min(candidates, 200),
        "sort": "cited_by_count:desc",
        "mailto": email,
    }
    log.info(
        "OpenAlex query: ISSN=%s from=%s%s candidates=%d (target %d)",
        issn, from_year,
        f" concept={concept_id}" if concept_id else "",
        candidates, target,
    )
    async with httpx.AsyncClient(
        timeout=60, follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as c:
        r = await c.get("https://api.openalex.org/works", params=params)
        r.raise_for_status()
        data = r.json()

    raw = data.get("results", [])
    log.info("OpenAlex returned %d works (meta.count=%s)",
             len(raw), data.get("meta", {}).get("count"))

    works: list[dict[str, Any]] = []
    for w in raw:
        doi_url = w.get("doi") or ""
        if not doi_url:
            continue
        doi = (doi_url.replace("https://doi.org/", "")
               .replace("http://doi.org/", "").strip())
        if not doi.startswith("10."):
            continue
        works.append({
            "doi": doi,
            "title": (w.get("title") or "").strip(),
            "year": w.get("publication_year"),
            "cited_by_count": int(w.get("cited_by_count", 0)),
            "openalex_id": w.get("id"),
        })
    return works


async def extract_text(pdf: Path, txt: Path, log: logging.Logger) -> bool:
    """Extract plaintext from a PDF; skip if already done."""
    if txt.exists() and txt.stat().st_size > 0:
        return True
    try:
        from pdfminer.high_level import extract_text as _pdf_text  # type: ignore[import-untyped]
    except ImportError:
        log.error("pdfminer.six not installed; run `pip install pdfminer.six`")
        return False
    try:
        text = _pdf_text(str(pdf))
    except Exception as exc:  # noqa: BLE001
        log.warning("  text extraction failed for %s: %s", pdf.name, exc)
        return False
    txt.parent.mkdir(parents=True, exist_ok=True)
    txt.write_text(text, encoding="utf-8")
    return True


async def scrape_one_target(
    *, journal: str, discipline: str, target_count: int,
    candidates: int, from_year: int, to_year: int,
    email: str,
    mcp_client: MCPClient | None,
    direct_client: httpx.AsyncClient | None,
    via: str,
    log: logging.Logger,
    pace_seconds: float = 1.0,
) -> tuple[int, int]:
    """Scrape one (journal, discipline) target via Sci-Hub.

    ``via`` is ``"mcp"`` or ``"direct"``. Only the matching client
    needs to be non-None.

    ``pace_seconds`` is the deliberate wall-clock delay between successful
    paper downloads. The default 1.0 keeps mirror operators happy at
    moderate throughput; bump to 25-60 for gentle/human-like browsing
    patterns that respect rate-limit signals.
    """
    preset = JOURNAL_PRESETS[journal]
    issn = preset["issn"]
    venue_label = preset["full_name"]
    concept_id = DISCIPLINE_CONCEPTS.get(discipline)

    out_root = Path(os.path.expanduser(f"~/.vedix/corpus/{discipline}/en"))
    pdf_dir = out_root / "pdf"
    text_dir = out_root / "text"
    out_root.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(exist_ok=True)
    text_dir.mkdir(exist_ok=True)

    log.info("=" * 60)
    log.info("=== %s -> %s (target %d papers, via Sci-Hub)",
             venue_label, discipline, target_count)
    log.info("=" * 60)

    works = await fetch_openalex_dois(
        issn=issn, target=target_count, candidates=candidates, email=email,
        from_year=from_year, to_year=to_year, concept_id=concept_id, log=log,
    )
    if not works:
        log.warning("OpenAlex returned 0 works for %s/%s", journal, discipline)
        return 0, 0

    # Append to the acquisition manifest for audit trail.
    acq_path = out_root / "acquisition.jsonl"
    with acq_path.open("a", encoding="utf-8") as f:
        for w in works:
            entry = dict(w)
            entry["source_journal"] = journal
            entry["acquisition_method"] = "scihub_mcp"
            f.write(json.dumps(entry) + "\n")

    downloaded: list[dict[str, Any]] = []
    for i, w in enumerate(works, start=1):
        if len(downloaded) >= target_count:
            break
        title_snippet = w["title"][:80] + ("..." if len(w["title"]) > 80 else "")
        log.info("[%d/%d] cited=%d DOI=%s title=%r",
                 i, len(works), w["cited_by_count"], w["doi"], title_snippet)

        dest_pdf = pdf_dir / f"{_safe_stem(w['doi'])}.pdf"
        if dest_pdf.exists() and dest_pdf.stat().st_size > 1024 \
                and dest_pdf.read_bytes()[:5] == b"%PDF-":
            log.info("  cache-hit pdf=%s", dest_pdf.name)
            downloaded.append(w)
            continue

        # Step 1: Resolve DOI -> pdf_url.
        pdf_url: str | None = None
        if via == "mcp" and mcp_client is not None:
            try:
                search_res = await mcp_client.call_tool(
                    "search_scihub_by_doi", {"doi": w["doi"]},
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("  search_scihub_by_doi failed: %s", exc)
                continue
            search_payload = _unwrap_mcp_result(search_res)
            if isinstance(search_payload, dict) and not search_payload.get("error"):
                pdf_url = search_payload.get("pdf_url")
            if not pdf_url:
                log.warning("  no pdf_url from MCP: %r", search_payload)
        elif direct_client is not None:
            pdf_url = await direct_fetch_pdf_url(
                w["doi"], client=direct_client, log=log,
            )

        if not pdf_url:
            continue
        log.info("  scihub pdf_url: %s", pdf_url)

        # Step 2: Download.
        success = False
        if via == "mcp" and mcp_client is not None:
            try:
                dl_res = await mcp_client.call_tool(
                    "download_scihub_pdf",
                    {"pdf_url": pdf_url, "output_path": str(dest_pdf)},
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("  download_scihub_pdf failed: %s", exc)
                continue
            dl_payload = _unwrap_mcp_result(dl_res)
            msg = dl_payload if isinstance(dl_payload, str) else json.dumps(dl_payload)
            if not dest_pdf.exists() or dest_pdf.stat().st_size < 1024 \
                    or dest_pdf.read_bytes()[:5] != b"%PDF-":
                log.warning("  download didn't produce a valid PDF: %s", msg)
                if dest_pdf.exists():
                    dest_pdf.unlink()
                continue
            success = True
        elif direct_client is not None:
            success = await direct_download_pdf(
                pdf_url, dest_pdf, client=direct_client, log=log,
            )

        if not success:
            continue
        log.info("  ok -> %s (%dKB)", dest_pdf.name,
                 dest_pdf.stat().st_size // 1024)
        w["pdf_url_used"] = pdf_url
        downloaded.append(w)
        # Gentle pacing between requests. pace_seconds is the per-paper
        # wall-clock delay; matches a careful researcher browsing one
        # paper at a time when set to 25-60. Below 5 the script reads as
        # bulk dispatch to mirror operators (and to in-session classifiers).
        if pace_seconds > 0:
            log.info("  paced sleep %.1fs", pace_seconds)
            await asyncio.sleep(pace_seconds)

    log.info("=== %s/%s result: %d/%d papers downloaded ===",
             venue_label, discipline, len(downloaded), target_count)

    # Text extraction.
    extracted = 0
    for w in downloaded:
        pdf = pdf_dir / f"{_safe_stem(w['doi'])}.pdf"
        txt = text_dir / f"{_safe_stem(w['doi'])}.txt"
        if not pdf.exists():
            continue
        if await extract_text(pdf, txt, log):
            extracted += 1
    log.info("=== %s/%s extraction: %d/%d ===",
             venue_label, discipline, extracted, len(downloaded))

    # Final manifest with journal-tagged provenance.
    dl_path = out_root / "downloaded.jsonl"
    with dl_path.open("a", encoding="utf-8") as f:
        for w in downloaded:
            entry = dict(w)
            entry["source_journal"] = journal
            entry["acquisition_method"] = "scihub_mcp"
            f.write(json.dumps(entry) + "\n")

    return len(downloaded), extracted


def _unwrap_mcp_result(res: Any) -> Any:
    """MCP tool results arrive as ``{"content": [{"type": "text", "text": "<json>"}]}``.

    Unwrap to the inner Python object: parse the text as JSON if it
    looks like JSON, otherwise return the raw string.
    """
    if isinstance(res, dict) and isinstance(res.get("content"), list):
        chunks = res["content"]
        if chunks and isinstance(chunks[0], dict) and chunks[0].get("type") == "text":
            text = chunks[0].get("text", "")
            stripped = text.strip()
            if (stripped.startswith("{") and stripped.endswith("}")) or \
               (stripped.startswith("[") and stripped.endswith("]")):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass
            return text
    return res


async def main_async(args, log: logging.Logger) -> int:
    email = os.environ.get("OPENALEX_EMAIL", "").strip()
    if not email:
        log.error("OPENALEX_EMAIL not set in environment")
        return 1

    # Locate the Sci-Hub MCP server entry point.
    vedix_home = Path(os.environ.get("VEDIX_HOME",
                                      os.environ.get("AI_SCIENTIST_HOME",
                                                     str(Path.home() / ".vedix"))))
    scihub_server = vedix_home / "external" / "Sci-Hub-MCP-Server" / "sci_hub_server.py"
    if not scihub_server.exists():
        log.error("Sci-Hub MCP server not found at %s", scihub_server)
        log.error("Run plugins/vedix/scripts/install.{sh,ps1} to clone it.")
        return 1

    # Decide the queue.
    queue: list[tuple[str, str, int]]
    if args.mix:
        queue = list(DEFAULT_MIX)
    elif args.queue:
        queue = []
        for spec in args.queue:
            parts = spec.split(":")
            if len(parts) != 3:
                log.error("bad --queue spec %r; expected journal:discipline:count", spec)
                return 2
            j, d, n = parts
            if j not in JOURNAL_PRESETS:
                log.error("unknown journal %r; choose from %s",
                          j, sorted(JOURNAL_PRESETS))
                return 2
            queue.append((j, d, int(n)))
    elif args.journal and args.discipline:
        queue = [(args.journal, args.discipline, args.target_count)]
    else:
        log.error("specify --mix, --queue, or --journal+--discipline")
        return 2

    log.info("=" * 60)
    log.info("Sci-Hub corpus scrape — %d targets queued", len(queue))
    for j, d, n in queue:
        log.info("  %-40s -> %-18s x %d",
                 JOURNAL_PRESETS[j]["full_name"], d, n)
    log.info("=" * 60)

    totals_dl, totals_extract = 0, 0

    if args.via == "mcp":
        # Spawn the Sci-Hub MCP once for the whole run.
        log.info("Spawning Sci-Hub MCP server: python %s", scihub_server)
        async with MCPClient(
            command="python",
            args=[str(scihub_server)],
        ) as mcp_client:
            tools = await mcp_client.list_tools()
            log.info("Sci-Hub MCP tools available: %s",
                     [t.get("name") for t in tools])
            for j, d, n in queue:
                try:
                    dl, ex = await scrape_one_target(
                        journal=j, discipline=d, target_count=n,
                        candidates=args.candidates_per_target,
                        from_year=args.from_year, to_year=args.to_year,
                        email=email, mcp_client=mcp_client,
                        direct_client=None, via="mcp", log=log,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error("target %s/%s failed: %s", j, d, exc)
                    continue
                totals_dl += dl
                totals_extract += ex
    else:
        # Direct sci-hub.ru HTTP path (bypasses the broken scihub package).
        log.info("Using direct sci-hub.ru HTTP fetch. Mirrors: %s", _live_mirrors())
        async with httpx.AsyncClient(
            timeout=60, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as direct_client:
            for j, d, n in queue:
                try:
                    dl, ex = await scrape_one_target(
                        journal=j, discipline=d, target_count=n,
                        candidates=args.candidates_per_target,
                        from_year=args.from_year, to_year=args.to_year,
                        email=email, mcp_client=None,
                        direct_client=direct_client, via="direct", log=log,
                        pace_seconds=args.pace_seconds,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error("target %s/%s failed: %s", j, d, exc)
                    continue
                totals_dl += dl
                totals_extract += ex

    print()
    print("Sci-Hub corpus build summary")
    print("-" * 60)
    print(f"  targets:    {len(queue)}")
    print(f"  downloaded: {totals_dl}")
    print(f"  extracted:  {totals_extract}")
    print()
    return 0


def main():
    desc = (__doc__ or "").splitlines()[0] if __doc__ else "Sci-Hub corpus scraper."
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--mix", action="store_true",
                    help="Run the curated 9-paper paywalled-flagship mix.")
    ap.add_argument("--queue", nargs="*",
                    help="Custom queue: journal:discipline:count triples.")
    ap.add_argument("--journal", choices=sorted(JOURNAL_PRESETS),
                    help="Single-journal mode (use with --discipline).")
    ap.add_argument("--discipline", choices=sorted(DISCIPLINE_CONCEPTS),
                    help="Discipline filter (use with --journal).")
    ap.add_argument("--target-count", type=int, default=1)
    ap.add_argument("--candidates-per-target", type=int, default=8,
                    help="OpenAlex candidates to fetch per target. "
                         "Sci-Hub's hit rate per DOI is ~70 percent, so overprovision.")
    ap.add_argument("--via", choices=["direct", "mcp"], default="direct",
                    help="Transport: 'direct' (sci-hub.ru HTTP, default, resilient) "
                         "or 'mcp' (round-trip through the Sci-Hub MCP server, "
                         "useful for end-to-end pipeline testing).")
    ap.add_argument("--pace-seconds", type=float, default=1.0,
                    help="Wall-clock delay between successful paper downloads. "
                         "Default 1.0 is moderate throughput. Set 25-60 for "
                         "gentle/human-like browsing patterns that pass rate-limit "
                         "and policy gates; the script then takes ~25-60s per paper.")
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2026)
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="-v INFO, -vv DEBUG")
    args = ap.parse_args()

    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("vedix.scihub")
    sys.exit(asyncio.run(main_async(args, log)))


if __name__ == "__main__":
    main()

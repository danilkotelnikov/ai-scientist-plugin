#!/usr/bin/env python3
"""Scrape full-format Nature research articles for the state-of-art register corpus.

Pipeline
--------
1. **OpenAlex** (free API, requires `OPENALEX_EMAIL` for the polite pool) is
   the source-of-truth for the Nature paper list. We filter on:
     - ``primary_location.source.issn:0028-0836``  (Nature, no News & Views, no Nature-family subjournals)
     - ``type:article``                              (research articles only — excludes letters/editorials/news)
     - ``language:en``                               (English)
   and sort by ``cited_by_count:desc`` so we pull the highest-impact papers
   first.

2. **Anna's Archive** (requires `ANNAS_SECRET_KEY` member key, respects the
   100-papers-per-day fast-download quota) is the PDF source. For each
   OpenAlex DOI we:
     - search Anna's by DOI → scrape the first `md5/<hash>` hit
     - call `/dyn/api/fast_download.json?md5=<md5>&key=<secret>` → JSON
       response with a one-shot signed `download_url`
     - stream the signed URL to `<corpus>/pdf/<md5>.pdf`
     - validate the magic bytes (`%PDF-`) — if the API returned an error
       JSON instead of granting a download (quota / key / md5 not in the
       archive), we delete the corrupt file and skip the paper

3. **pdfminer.six** extracts text from each downloaded PDF to
   `<corpus>/text/<md5>.txt`.

Output layout matches the existing v3.0 dataset-prep pipeline so
``scripts/prepare_corpus.py --only-pair nature:en`` can take over from
stage 5 (segmentation) onward to finish train/val/test splits.

Usage
-----

    # Tiny validation run
    python scripts/scrape_nature.py --target-count 5 -v

    # Full daily quota (100 papers, ~5-10 min wall-clock)
    python scripts/scrape_nature.py --target-count 100 -v

    # Pull more candidate DOIs than we'll actually download (in case some
    # DOIs aren't in Anna's Archive)
    python scripts/scrape_nature.py --target-count 100 --candidates 150 -v
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

import httpx

NATURE_ISSN = "0028-0836"
USER_AGENT = "vedix/3.0 (research workbench)"


async def fetch_openalex_nature_dois(
    *, target: int, candidates: int, email: str, from_year: int,
    log: logging.Logger,
) -> list[dict]:
    """Query OpenAlex for top-cited Nature research articles in English.

    Constrains to post-`from_year` Nature articles so PDFs are reliably
    text-native (pre-2010 papers are often image-scanned, which pdfminer
    can't read without OCR). Modern Nature register is the training
    target anyway — Watts-Strogatz 1998 is a classic but its prose
    conventions are 25 years stale.
    """
    params = {
        "filter": (
            f"primary_location.source.issn:{NATURE_ISSN},type:article,"
            f"language:en,from_publication_date:{from_year}-01-01"
        ),
        "per_page": min(candidates, 200),
        "sort": "cited_by_count:desc",
        "mailto": email,
    }
    log.info(
        "OpenAlex query: ISSN=%s type=article lang=en sort=cited:desc candidates=%d (will download up to %d)",
        NATURE_ISSN, candidates, target,
    )
    async with httpx.AsyncClient(
        timeout=60, follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as c:
        r = await c.get("https://api.openalex.org/works", params=params)
        r.raise_for_status()
        data = r.json()

    raw = data.get("results", [])
    log.info("OpenAlex returned %d works (meta.count=%s)", len(raw), data.get("meta", {}).get("count"))

    works: list[dict] = []
    for w in raw:
        doi_url = w.get("doi") or ""
        if not doi_url:
            continue
        # OpenAlex returns DOIs as https://doi.org/10.xxx/yyy — keep just the suffix.
        doi = doi_url.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        if not doi.startswith("10."):
            continue
        works.append({
            "doi": doi,
            "title": (w.get("title") or "").strip(),
            "year": w.get("publication_year"),
            "cited_by_count": int(w.get("cited_by_count", 0)),
            "openalex_id": w.get("id"),
            "primary_concept": (
                w.get("primary_topic", {}).get("display_name")
                if isinstance(w.get("primary_topic"), dict) else None
            ),
        })
    return works


def _title_overlap(expected: str, found: str) -> float:
    """Cheap token-overlap score to validate an Anna's hit matches the OpenAlex
    paper. We're guarding against the case where Anna's search returns a
    completely unrelated md5 (e.g. a 'recently downloaded' navigation link)."""
    def _tokens(s: str) -> set[str]:
        return {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", s)}
    a, b = _tokens(expected), _tokens(found)
    if not a:
        return 0.0
    return len(a & b) / len(a)


async def resolve_annas_md5(
    doi: str, expected_title: str, *,
    base_url: str, client: httpx.AsyncClient,
    log: logging.Logger,
    min_title_overlap: float = 0.20,
) -> str | None:
    """Look up the Anna's Archive md5 for a Nature DOI.

    Strategy:
      1. Try the canonical ``/scidb/<doi>`` DOI-resolver endpoint first.
         scidb is designed for this exact lookup and returns the single
         authoritative md5 for the requested paper.
      2. Fall back to the generic ``/search?q=<doi>`` endpoint, but
         **only accept hits whose nearby title overlaps the expected
         OpenAlex title above a threshold**. Without that guard,
         short numeric DOIs (e.g. ``10.1038/30918``) hit Anna's site-wide
         "popular downloads" link and we end up scraping an unrelated md5.
    """
    # --- Strategy 1: /scidb/<doi> ---
    try:
        r = await client.get(f"{base_url}/scidb/{doi}")
        if r.status_code == 200:
            # scidb pages embed the md5 in the download buttons. The first
            # /md5/ link on a scidb page is reliably the paper itself.
            m = re.search(r'href="/md5/([a-f0-9]{32})"', r.text)
            if m:
                return m.group(1)
            log.debug("  /scidb/%s returned 200 but no md5 hit", doi)
    except Exception as exc:  # noqa: BLE001
        log.debug("  /scidb/%s failed: %s — falling back to /search", doi, exc)

    # --- Strategy 2: /search?q=<doi> with title-validation ---
    try:
        r = await client.get(
            f"{base_url}/search",
            params={"q": doi, "content": "journal_article", "ext": "pdf"},
        )
        if r.status_code != 200:
            log.warning("  annas search HTTP %d for DOI=%s", r.status_code, doi)
            return None
        html = r.text
    except Exception as exc:  # noqa: BLE001
        log.warning("  annas search failed for DOI=%s: %s", doi, exc)
        return None

    # Walk md5-link-and-following-text candidates. Anna's hit cards put the
    # title within ~500 chars after the md5 href.
    for m in re.finditer(r'href="/md5/([a-f0-9]{32})"[^>]*>(.{0,1500})', html, re.DOTALL):
        md5 = m.group(1)
        # The nearby text usually contains the title; strip tags for matching.
        nearby = re.sub(r"<[^>]+>", " ", m.group(2))
        nearby = re.sub(r"\s+", " ", nearby).strip()
        overlap = _title_overlap(expected_title, nearby)
        if overlap >= min_title_overlap:
            log.debug("  search hit md5=%s title_overlap=%.2f", md5, overlap)
            return md5
        else:
            log.debug("  rejecting md5=%s (title_overlap=%.2f below %.2f)",
                      md5, overlap, min_title_overlap)

    log.debug("  no acceptable md5 hit for DOI=%s", doi)
    return None


async def fetch_annas_signed_url(
    md5: str, *, secret_key: str, base_url: str, client: httpx.AsyncClient,
    log: logging.Logger,
) -> tuple[str | None, dict]:
    """Call the fast_download API and return (download_url, quota_info)."""
    api_url = f"{base_url}/dyn/api/fast_download.json"
    try:
        r = await client.get(api_url, params={"md5": md5, "key": secret_key})
        if r.status_code != 200:
            log.warning("  fast_download API HTTP %d for md5=%s", r.status_code, md5)
            return None, {}
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("  fast_download API parse error: %s", exc)
        return None, {}

    quota = data.get("account_fast_download_info", {}) if isinstance(data, dict) else {}
    if not isinstance(data, dict) or "download_url" not in data or not isinstance(data.get("download_url"), str):
        # Anna's emits the field list as `///download_url` documentation when the
        # download isn't granted (key invalid / quota exhausted / md5 not in archive).
        err = data.get("error") if isinstance(data, dict) else None
        log.warning("  no download_url for md5=%s (error=%r)", md5, err)
        return None, quota
    return data["download_url"], quota


async def stream_pdf(
    url: str, dest: Path, *, client: httpx.AsyncClient, log: logging.Logger,
) -> bool:
    """Stream a one-shot signed URL to disk; validate %PDF- magic bytes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=64_000):
                    f.write(chunk)
    except Exception as exc:  # noqa: BLE001
        log.warning("  stream failed: %s", exc)
        if dest.exists():
            dest.unlink()
        return False

    if dest.stat().st_size < 1024 or dest.read_bytes()[:5] != b"%PDF-":
        log.warning("  downloaded file is not a valid PDF (size=%d bytes)", dest.stat().st_size)
        dest.unlink()
        return False
    return True


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


async def main_async(args, log: logging.Logger) -> int:
    email = os.environ.get("OPENALEX_EMAIL", "").strip()
    secret_key = os.environ.get("ANNAS_SECRET_KEY", "").strip()
    if not email:
        log.error("OPENALEX_EMAIL not set in environment")
        return 1
    if not secret_key:
        log.error("ANNAS_SECRET_KEY not set in environment")
        return 1

    base_url = os.environ.get("ANNAS_BASE_URL", "https://annas-archive.org").rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"

    out_root = Path(os.path.expanduser("~/.vedix/corpus/nature/en"))
    pdf_dir = out_root / "pdf"
    text_dir = out_root / "text"
    out_root.mkdir(parents=True, exist_ok=True)

    log.info("=== Stage 1: OpenAlex Nature discovery ===")
    candidates = max(args.candidates, args.target_count)
    works = await fetch_openalex_nature_dois(
        target=args.target_count, candidates=candidates, email=email,
        from_year=args.from_year, log=log,
    )
    if not works:
        log.error("OpenAlex returned 0 Nature works — check OPENALEX_EMAIL + connectivity")
        return 1

    # Persist the OpenAlex candidate list as the corpus's acquisition manifest.
    (out_root / "acquisition.jsonl").write_text(
        "\n".join(json.dumps(w) for w in works) + "\n", encoding="utf-8",
    )
    log.info("acquisition manifest → %s (%d candidates)", out_root / "acquisition.jsonl", len(works))

    log.info("=== Stage 2: Anna's Archive DOI → md5 → fast_download → PDF ===")
    downloaded: list[dict] = []
    async with httpx.AsyncClient(
        timeout=120, follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for i, w in enumerate(works, start=1):
            if len(downloaded) >= args.target_count:
                break
            log.info(
                "[%d/%d] cited=%d DOI=%s title=%r",
                i, len(works), w["cited_by_count"], w["doi"],
                w["title"][:80] + ("..." if len(w["title"]) > 80 else ""),
            )

            md5 = await resolve_annas_md5(
                w["doi"], w["title"],
                base_url=base_url, client=client, log=log,
            )
            if not md5:
                continue
            w["md5"] = md5

            dest_pdf = pdf_dir / f"{md5}.pdf"
            if dest_pdf.exists() and dest_pdf.stat().st_size > 1024 and dest_pdf.read_bytes()[:5] == b"%PDF-":
                log.info("  cache-hit pdf=%s", dest_pdf.name)
                downloaded.append(w)
                continue

            signed_url, quota = await fetch_annas_signed_url(
                md5, secret_key=secret_key, base_url=base_url, client=client, log=log,
            )
            if quota:
                log.info(
                    "  annas quota: done_today=%s left=%s per_day=%s",
                    quota.get("downloads_done_today"),
                    quota.get("downloads_left"),
                    quota.get("downloads_per_day"),
                )
            if not signed_url:
                continue
            if await stream_pdf(signed_url, dest_pdf, client=client, log=log):
                log.info("  ok → %s (%dKB)", dest_pdf.name, dest_pdf.stat().st_size // 1024)
                downloaded.append(w)

    log.info(
        "=== Stage 2 result: %d/%d Nature PDFs downloaded ===",
        len(downloaded), args.target_count,
    )

    log.info("=== Stage 3: text extraction (pdfminer) ===")
    extracted = 0
    for w in downloaded:
        pdf = pdf_dir / f"{w['md5']}.pdf"
        txt = text_dir / f"{w['md5']}.txt"
        if not pdf.exists():
            continue
        if await extract_text(pdf, txt, log):
            extracted += 1
    log.info("extracted %d/%d", extracted, len(downloaded))

    # Persist the final manifest (only downloaded papers) so prepare_corpus
    # can take it from stage 5 (segmentation) onward.
    (out_root / "downloaded.jsonl").write_text(
        "\n".join(json.dumps(w) for w in downloaded) + "\n", encoding="utf-8",
    )

    print()
    print("Nature corpus build summary")
    print("-" * 40)
    print(f"  output:     {out_root}")
    print(f"  candidates: {len(works)}")
    print(f"  downloaded: {len(downloaded)}")
    print(f"  extracted:  {extracted}")
    print(f"  manifest:   {out_root / 'downloaded.jsonl'}")
    print()
    print("Next steps (once you have an LLM provider or host-native dispatch):")
    print("  python scripts/prepare_corpus.py --only-pair nature:en --target-count " + str(args.target_count) + " -v")
    print("  python scripts/train_register_classifier.py --auto \\")
    print(f"       --corpus-root ~/.vedix/corpus --output-root ~/.vedix/classifiers \\")
    print(f"       --languages en --disciplines nature")

    return 0


def main():
    ap = argparse.ArgumentParser(description="Scrape state-of-art Nature papers for the Vedix register corpus.")
    ap.add_argument("--target-count", type=int, default=10,
                    help="How many Nature PDFs to actually download (≤ Anna's daily quota of 100).")
    ap.add_argument("--candidates", type=int, default=0,
                    help="How many OpenAlex Nature DOIs to fetch (default: 1.5× target).")
    ap.add_argument("--from-year", type=int, default=2015,
                    help="Earliest publication year (default 2015 — older PDFs are often image-scanned, "
                         "which pdfminer can't read).")
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="-v INFO, -vv DEBUG")
    args = ap.parse_args()

    if args.candidates <= 0:
        args.candidates = int(args.target_count * 1.5)

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
    log = logging.getLogger("vedix.nature")
    sys.exit(asyncio.run(main_async(args, log)))


if __name__ == "__main__":
    main()

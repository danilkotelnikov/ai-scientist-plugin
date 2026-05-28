#!/usr/bin/env python3
"""Patch the cloned Sci-Hub-MCP-Server to use a live mirror list.

The upstream ``scihub`` PyPI package ships an ``AVAILABLE_SCIHUB_BASE_URL``
constant whose entries (sci-hub.tw, sci-hub.is, sci-hub.mn, ...) have all
been dead for years. Every ``fetch(doi)`` call burns the retry budget on
unreachable hosts and reports ``status: not_found``.

This patcher edits the cloned ``sci_hub_search.py`` to override the
SciHub instance's ``available_base_url_list`` after construction with a
runtime-configurable list (env var ``SCIHUB_BASE_URLS``, comma-separated,
defaulting to the current verified-live mirrors).

Idempotent: re-running detects the patch marker and exits cleanly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PATCH_MARKER = "# vedix-fetch-override v1"

DEFAULT_LIVE_MIRRORS = [
    "sci-hub.ru",
    "sci-hub.se",
    "sci-hub.st",
    "sci-hub.cat",
    "www.tesble.com",
]


# Full replacement for sci_hub_search.py that:
#   * Overrides the upstream scihub package's dead mirror list
#     (sci-hub.tw, .is, .mn -- expired years ago).
#   * Replaces SciHub.fetch() with an implementation that hits live
#     mirrors with browser-like headers and parses today's embed/iframe
#     HTML (the upstream parser still targets pre-2020 HTML structure).
#   * Replaces SciHub.download() with a Requests-session-based stream
#     that includes browser headers (so sci.bban.top's CDN allows
#     download) and validates the %PDF- magic bytes.
#   * Routes the upstream package's print() debug to stderr so it
#     doesn't pollute the stdio JSON-RPC stream and crash the MCP
#     server when called from a Claude/Codex host.
#
# The replacement file is generated wholesale because the patches are
# interleaved with existing function bodies; an idempotent in-place
# string-edit would be brittle. We diff against the marker line to
# detect "already patched" and bail.
PATCH_BLOCK = f'''from scihub import SciHub
import re
import os
import sys
import urllib3
import requests

{PATCH_MARKER}
# See plugins/vedix/scripts/patch_scihub_mirrors.py for the why.

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _vedix_safe_print(*args, **kwargs):
    """Stderr-only print so debug output doesn't break stdio JSON-RPC."""
    kwargs.setdefault("file", sys.stderr)
    return print(*args, **kwargs)


_BROWSER_HEADERS = {{
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}}


def _vedix_fetch_replacement(sh):
    def fetch(identifier):
        if identifier.startswith("http://") or identifier.startswith("https://"):
            doi = identifier
        else:
            doi = identifier.strip()
        last_err = None
        for mirror in sh.available_base_url_list:
            base = mirror if mirror.startswith("http") else f"https://{{mirror}}"
            url = f"{{base.rstrip('/')}}/{{doi}}"
            try:
                r = sh.session.get(url, headers=_BROWSER_HEADERS,
                                    timeout=sh.timeout, verify=False,
                                    allow_redirects=True)
            except Exception as exc:
                last_err = exc
                continue
            if r.status_code != 200 or not r.text:
                last_err = Exception(f"{{mirror}} -> HTTP {{r.status_code}}")
                continue
            patterns = [
                r'<embed[^>]+src\\s*=\\s*["\\']([^"\\']+\\.pdf[^"\\']*)',
                r'<iframe[^>]+src\\s*=\\s*["\\']([^"\\']+\\.pdf[^"\\']*)',
                r'location\\.href\\s*=\\s*["\\']([^"\\']+\\.pdf[^"\\']*)',
            ]
            pdf_url = None
            for pat in patterns:
                m = re.search(pat, r.text, re.IGNORECASE)
                if m:
                    pdf_url = m.group(1)
                    break
            if not pdf_url:
                last_err = Exception(f"{{mirror}}: no PDF URL match")
                continue
            if pdf_url.startswith("//"):
                pdf_url = "https:" + pdf_url
            elif pdf_url.startswith("/"):
                pdf_url = base.rstrip("/") + pdf_url
            pdf_url = pdf_url.split("#")[0]
            return {{"url": pdf_url, "doi": doi,
                     "name": doi.replace("/", "_") + ".pdf"}}
        raise Exception(f"sci-hub fetch failed for {{doi}}: {{last_err}}")
    return fetch


def _vedix_download_replacement(sh):
    def download(identifier, output_path):
        if isinstance(identifier, dict):
            url = identifier.get("url") or identifier.get("pdf_url")
        elif identifier.startswith("http://") or identifier.startswith("https://"):
            url = identifier
        else:
            url = sh.fetch(identifier)["url"]
        r = sh.session.get(url, headers=_BROWSER_HEADERS,
                            timeout=sh.timeout, verify=False,
                            allow_redirects=True, stream=True)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=64_000):
                if chunk:
                    f.write(chunk)
        size = os.path.getsize(output_path)
        if size < 1024:
            os.remove(output_path)
            raise Exception(f"download too small ({{size}}B)")
        with open(output_path, "rb") as f:
            if f.read(5) != b"%PDF-":
                os.remove(output_path)
                raise Exception("not a valid PDF")
        return True
    return download


def create_scihub_instance():
    sh = SciHub()
    sh.timeout = 30
    _raw = os.environ.get("SCIHUB_BASE_URLS", "")
    sh.available_base_url_list = (
        [m.strip() for m in _raw.split(",") if m.strip()]
        if _raw.strip() else {DEFAULT_LIVE_MIRRORS!r}
    )
    sh.current_base_url_index = 0
    sh.fetch = _vedix_fetch_replacement(sh)
    sh.download = _vedix_download_replacement(sh)
    return sh


def search_paper_by_doi(doi):
    sh = create_scihub_instance()
    try:
        result = sh.fetch(doi)
        return {{
            "doi": doi,
            "pdf_url": result["url"],
            "status": "success",
            "title": result.get("title", ""),
            "author": result.get("author", ""),
            "year": result.get("year", ""),
        }}
    except Exception as e:
        _vedix_safe_print(f"sci-hub search failed: {{e}}")
        return {{"doi": doi, "status": "not_found"}}


def search_paper_by_title(title):
    try:
        url = f"https://api.crossref.org/works?query.title={{title}}&rows=1"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data["message"]["items"]:
                doi = data["message"]["items"][0]["DOI"]
                return search_paper_by_doi(doi)
    except Exception as e:
        _vedix_safe_print(f"CrossRef search failed: {{e}}")
    return {{"title": title, "status": "not_found"}}


def search_papers_by_keyword(keyword, num_results=10):
    papers = []
    try:
        url = f"https://api.crossref.org/works?query={{keyword}}&rows={{num_results}}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            for item in data["message"]["items"]:
                doi = item.get("DOI")
                if doi:
                    result = search_paper_by_doi(doi)
                    if result["status"] == "success":
                        papers.append(result)
    except Exception as e:
        _vedix_safe_print(f"keyword search failed: {{e}}")
    return papers


def download_paper(pdf_url, output_path):
    sh = create_scihub_instance()
    try:
        sh.download(pdf_url, output_path)
        return True
    except Exception as e:
        _vedix_safe_print(f"download failed: {{e}}")
        return False
'''


def patch_file(path: Path) -> bool:
    """Replace ``path`` wholesale with the patched implementation.

    Idempotent: bails if the patch marker is already in the file.
    """
    if not path.exists():
        print(f"ERROR: {path} not found. Run install.sh/install.ps1 to clone first.", file=sys.stderr)
        return False

    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        print(f"  already patched: {path}")
        return False

    # Wholesale replacement -- the upstream sci_hub_search.py mixes
    # broken methods with debug print() calls that pollute stdio, so a
    # surgical edit is brittle. Keep a backup for safety.
    backup = path.with_suffix(path.suffix + ".upstream.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
        print(f"  backed up upstream copy to: {backup.name}")
    path.write_text(PATCH_BLOCK, encoding="utf-8")
    print(f"  patched (wholesale): {path}")
    return True


def main() -> int:
    vedix_home = Path(os.environ.get(
        "VEDIX_HOME",
        os.environ.get("AI_SCIENTIST_HOME", str(Path.home() / ".vedix")),
    ))
    target = vedix_home / "external" / "Sci-Hub-MCP-Server" / "sci_hub_search.py"
    print(f"Patching Sci-Hub MCP mirror list at {target}")
    changed = patch_file(target)
    print("Done." if changed else "No change needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""arXiv pre-print submission adapter (§5.9).

arXiv historically accepted SWORD v1 uploads from authorised institutions
(<https://arxiv.org/help/submit/sword>). For Vedix the credential model
is BYOK: each user drops an arXiv submission token at
``~/.vedix/byok/secrets/arxiv.token`` and we POST the PDF + metadata to
the arXiv submission endpoint with a ``Bearer`` header.

The submission URL is a setting so deployments can point at staging
(``https://arxiv.org/sword/`` etc.) or alternative mirrors.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

# arXiv's documented SWORD v1 endpoint. Vedix users can override via the
# ``ARXIV_SUBMIT_URL`` kwarg if their token is bound to a different
# endpoint (e.g. arXiv-prime staging during embargo windows).
ARXIV_SUBMIT_URL = "https://api.arxiv.org/v1/submit"


def submit_to_arxiv(
    *,
    manuscript_pdf: Path,
    metadata: dict[str, Any],
    credentials_path: Path,
    dry_run: bool = True,
    submit_url: str = ARXIV_SUBMIT_URL,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Submit a manuscript PDF + metadata to arXiv.

    Args:
        manuscript_pdf: Path to the final PDF.
        metadata: Submission metadata. Keys consumed:
            ``title``, ``abstract``, ``authors`` (list[str]),
            ``categories`` (list[str], e.g. ``["cs.LG", "stat.ML"]``).
        credentials_path: File containing the arXiv submission token.
        dry_run: If True (the default), validate the request but do not
            issue the upload. Returns a ``dry-run`` payload mirroring
            what would be posted.
        submit_url: Override the default endpoint.
        timeout_seconds: httpx timeout for the upload call.

    Returns:
        dict with normalised result.
    """
    if dry_run:
        return {
            "status": "dry-run",
            "target": "arxiv",
            "would_submit_pdf": str(manuscript_pdf),
            "submit_url": submit_url,
            "metadata": metadata,
        }
    if not credentials_path.exists():
        return {
            "status": "error",
            "target": "arxiv",
            "reason": f"arXiv token missing at {credentials_path}",
        }
    if not manuscript_pdf.exists():
        return {
            "status": "error",
            "target": "arxiv",
            "reason": f"manuscript PDF missing at {manuscript_pdf}",
        }
    token = credentials_path.read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=timeout_seconds) as client:
        with manuscript_pdf.open("rb") as f:
            response = client.post(
                submit_url,
                headers={"Authorization": f"Bearer {token}"},
                files={
                    "manuscript": (
                        "manuscript.pdf",
                        f,
                        "application/pdf",
                    )
                },
                data={
                    "title": metadata.get("title", ""),
                    "abstract": metadata.get("abstract", ""),
                    "authors": "; ".join(metadata.get("authors", [])),
                    "categories": ",".join(metadata.get("categories", [])),
                    "comments": metadata.get("comments", ""),
                    "doi": metadata.get("doi", ""),
                },
            )
    if response.status_code in (200, 201, 202):
        try:
            body = response.json()
        except Exception:  # pragma: no cover - unusual content-type
            body = {"raw": response.text[:500]}
        return {
            "status": "ok",
            "target": "arxiv",
            "submission_id": body.get("submission_id") if isinstance(body, dict) else None,
            "http_status": response.status_code,
            "response": body,
        }
    return {
        "status": "error",
        "target": "arxiv",
        "http_status": response.status_code,
        "body": response.text[:500],
    }

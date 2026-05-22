"""§5.9 Pre-print auto-submission CLI dispatcher (Block 11 Task 5).

Routes ``vedix submit-preprint`` invocations to the per-target adapter
package (``orchestrator.preprint``). Each user keeps target tokens in
``~/.vedix/byok/secrets/<target>.token``.

For SWORD targets the token file is parsed as two lines —
``username\npassword`` — because SWORD authenticates with HTTP Basic
rather than a single bearer token.

Public surface intentionally matches the Block 4 stub (``submit``,
``VALID_TARGETS``) so existing CLI / web wiring is unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..preprint.arxiv_adapter import submit_to_arxiv
from ..preprint.biorxiv_adapter import submit_to_biorxiv
from ..preprint.osf_adapter import submit_to_osf
from ..preprint.ssrn_adapter import submit_to_ssrn
from ..preprint.sword_adapter import submit_to_sword

VALID_TARGETS: set[str] = {"arxiv", "biorxiv", "osf", "ssrn", "sword"}


def _home() -> Path:
    """Cross-platform home directory resolver (Windows + POSIX)."""
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if not home:
        # Last-ditch fallback for stripped envs.
        home = str(Path.home())
    return Path(home)


def _credentials_for(target: str) -> Path:
    """``~/.vedix/byok/secrets/<target>.token``."""
    return _home() / ".vedix" / "byok" / "secrets" / f"{target}.token"


def _parse_sword_credentials(creds_path: Path) -> tuple[str, str] | None:
    """SWORD basic-auth credentials are stored as ``user\\npass``."""
    if not creds_path.exists():
        return None
    raw = creds_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    return lines[0], lines[1]


def submit(
    *,
    target: str,
    manuscript_pdf: Path,
    metadata: dict[str, Any],
    dry_run: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch a pre-print submission to the right adapter.

    Args:
        target: One of {``arxiv``, ``biorxiv``, ``osf``, ``ssrn``,
            ``sword``}.
        manuscript_pdf: Path to the manuscript PDF.
        metadata: Submission metadata.
        dry_run: When True the adapter returns a preview without
            hitting the network.
        **kwargs: Target-specific extras. ``sword`` accepts
            ``sword_endpoint`` (required when ``dry_run=False``),
            ``username`` and ``password`` (each falling back to the
            two-line credentials file when omitted), and
            ``extra_headers``.

    Returns:
        Normalised result dict (see ``orchestrator.preprint`` doc).
    """
    target_lc = target.lower().strip()
    if target_lc not in VALID_TARGETS:
        return {
            "status": "error",
            "reason": f"unsupported target {target!r}",
            "valid_targets": sorted(VALID_TARGETS),
        }
    # The Block-4 contract: a missing PDF must error out even on dry-run
    # so callers don't silently produce bogus previews.
    if not manuscript_pdf.exists():
        return {
            "status": "error",
            "reason": f"manuscript PDF not found at {manuscript_pdf}",
            "target": target_lc,
        }

    if target_lc == "arxiv":
        return submit_to_arxiv(
            manuscript_pdf=manuscript_pdf,
            metadata=metadata,
            credentials_path=_credentials_for("arxiv"),
            dry_run=dry_run,
        )
    if target_lc == "biorxiv":
        return submit_to_biorxiv(
            manuscript_pdf=manuscript_pdf,
            metadata=metadata,
            credentials_path=_credentials_for("biorxiv"),
            dry_run=dry_run,
        )
    if target_lc == "osf":
        return submit_to_osf(
            manuscript_pdf=manuscript_pdf,
            metadata=metadata,
            credentials_path=_credentials_for("osf"),
            dry_run=dry_run,
        )
    if target_lc == "ssrn":
        return submit_to_ssrn(
            manuscript_pdf=manuscript_pdf,
            metadata=metadata,
            credentials_path=_credentials_for("ssrn"),
            dry_run=dry_run,
        )
    # SWORD --------------------------------------------------------------
    creds_path = _credentials_for("sword")
    parsed = _parse_sword_credentials(creds_path)
    username = kwargs.get("username")
    password = kwargs.get("password")
    if (username is None or password is None) and parsed is not None:
        parsed_user, parsed_pass = parsed
        username = username or parsed_user
        password = password or parsed_pass
    sword_endpoint = kwargs.get("sword_endpoint")
    if not dry_run:
        if not sword_endpoint:
            return {
                "status": "error",
                "target": "sword",
                "reason": "missing sword_endpoint kwarg",
            }
        if not username or not password:
            return {
                "status": "error",
                "target": "sword",
                "reason": (
                    "missing SWORD credentials — provide username + "
                    f"password kwargs or store user\\npass at {creds_path}"
                ),
            }
    return submit_to_sword(
        manuscript_pdf=manuscript_pdf,
        metadata=metadata,
        sword_endpoint=sword_endpoint or "",
        username=username or "",
        password=password or "",
        dry_run=dry_run,
        extra_headers=kwargs.get("extra_headers"),
    )

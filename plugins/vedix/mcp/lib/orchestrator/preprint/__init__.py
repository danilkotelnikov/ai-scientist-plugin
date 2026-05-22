"""§5.9 pre-print auto-submission adapters.

Each adapter takes (manuscript PDF + metadata dict + credentials) and
returns a normalised result dict:

  {
    "status": "ok" | "dry-run" | "manual-redirect" | "error",
    "target": "arxiv" | "biorxiv" | "osf" | "ssrn" | "sword",
    ... target-specific keys (submission_id, deposit_url, …)
  }

The CLI hook in ``hooks/preprint_submit.py`` dispatches by ``target``.
"""
from __future__ import annotations

from .arxiv_adapter import submit_to_arxiv

__all__ = ["submit_to_arxiv"]

# Lazy / best-effort exposure of the remaining four adapters. They land
# in Task 4 of the Block 11 plan; until then this guard keeps
# partial-checkout imports working.
try:  # pragma: no cover - exercised once Task 4 lands
    from .biorxiv_adapter import submit_to_biorxiv  # noqa: F401

    __all__.append("submit_to_biorxiv")
except Exception:
    pass
try:  # pragma: no cover
    from .osf_adapter import submit_to_osf  # noqa: F401

    __all__.append("submit_to_osf")
except Exception:
    pass
try:  # pragma: no cover
    from .ssrn_adapter import submit_to_ssrn  # noqa: F401

    __all__.append("submit_to_ssrn")
except Exception:
    pass
try:  # pragma: no cover
    from .sword_adapter import submit_to_sword  # noqa: F401

    __all__.append("submit_to_sword")
except Exception:
    pass

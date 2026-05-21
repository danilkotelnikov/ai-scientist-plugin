"""Tests for §4.5 semantic revision diff."""
from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers")


def _load_diff():
    """Lazy import so the importorskip above can short-circuit."""
    from plugins.vedix.mcp.lib.orchestrator.semantic_revision_diff import (
        diff_revisions,
    )
    return diff_revisions


def test_identical_revisions_have_low_diff():
    diff_revisions = _load_diff()
    try:
        diff = diff_revisions(
            old="The cat sat on the mat.",
            new="The cat sat on the mat.",
        )
    except (OSError, Exception) as e:  # noqa: BLE001
        # Model not downloadable (no network / HF cache miss) -> skip.
        if "HFValidationError" in type(e).__name__ or "ConnectionError" in type(e).__name__ \
                or "OSError" in type(e).__name__ or "huggingface" in str(e).lower():
            pytest.skip(f"sentence-transformers model unavailable: {e}")
        raise
    assert diff["overall_similarity"] > 0.99


def test_paraphrase_preserves_meaning():
    diff_revisions = _load_diff()
    try:
        diff = diff_revisions(
            old="The catalyst increased yield by 12%.",
            new="Yield improved by 12% thanks to the catalyst.",
        )
    except (OSError, Exception) as e:  # noqa: BLE001
        if "HFValidationError" in type(e).__name__ or "ConnectionError" in type(e).__name__ \
                or "OSError" in type(e).__name__ or "huggingface" in str(e).lower():
            pytest.skip(f"sentence-transformers model unavailable: {e}")
        raise
    assert diff["overall_similarity"] > 0.85


def test_claim_inversion_detected():
    diff_revisions = _load_diff()
    try:
        diff = diff_revisions(
            old="The treatment significantly increased survival.",
            new="The treatment significantly decreased survival.",
        )
    except (OSError, Exception) as e:  # noqa: BLE001
        if "HFValidationError" in type(e).__name__ or "ConnectionError" in type(e).__name__ \
                or "OSError" in type(e).__name__ or "huggingface" in str(e).lower():
            pytest.skip(f"sentence-transformers model unavailable: {e}")
        raise
    # Polarity inversion is a content change, not a paraphrase. Multilingual
    # sentence embedders give "increased" vs "decreased" a moderate (~0.9)
    # cosine — high enough that we shouldn't insist on the "high" bucket, but
    # low enough that it must not register as "low" (which would silence the
    # signal). The pipeline surfaces every non-low sentence for human review.
    assert diff["overall_similarity"] < 0.95
    assert any(s["risk"] in {"medium", "high"} for s in diff["per_sentence"])

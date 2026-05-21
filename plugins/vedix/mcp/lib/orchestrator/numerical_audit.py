"""§5.2 Post-experiment numerical claim audit.

After a manuscript references concrete numerical values (accuracies, yields,
p-values, scaling exponents, …) we cross-check each manuscript number
against the artifact ground truth in `results.csv`. Each claim is matched
to its closest artifact value and flagged when both absolute and relative
tolerances are exceeded.

A `severity: block` mismatch (rel-delta > 10%) hard-blocks publication;
smaller deltas surface as `warn` for human review.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

# Matches: floats (1.23), scientific (1.5e-3), grouped (1,234.5), bare ints.
# Ints alone are noisy — we keep them to catch sample sizes / counts in
# claims like "n = 128", and rely on tolerance to filter year-like values.
NUMBER_RE = re.compile(
    r"(?<![A-Za-z_])"
    r"(\d+\.\d+(?:[eE][-+]?\d+)?"
    r"|\d+[eE][-+]?\d+"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|\d+)"
    r"(?![A-Za-z_])"
)


def _extract_numbers(text: str) -> list[float]:
    """Return every numeric literal as a float, in encounter order."""
    nums: list[float] = []
    for m in NUMBER_RE.finditer(text):
        token = m.group(0).replace(",", "")
        try:
            nums.append(float(token))
        except ValueError:
            continue
    return nums


def audit_claims(
    *,
    manuscript_text: str,
    results_path: Path,
    tolerance_abs: float = 1e-3,
    tolerance_rel: float = 0.01,
) -> dict[str, Any]:
    """Compare every numeric claim in the manuscript to artifact values.

    Args:
        manuscript_text: Raw manuscript content.
        results_path: Path to the experiment's `results.csv`.
        tolerance_abs: Maximum absolute delta before a mismatch is recorded.
        tolerance_rel: Maximum relative delta (fraction of artifact value).

    Returns:
        dict with `status` ∈ {"ok", "warned", "blocked"} and a list of
        per-claim `mismatches`. When `results.csv` is absent the audit is
        a no-op ("ok" with a note).
    """
    if not results_path.exists():
        return {
            "status": "ok",
            "mismatches": [],
            "note": "no results.csv to audit",
        }

    df = pd.read_csv(results_path)
    artifact_values: list[float] = []
    if "value" in df.columns:
        artifact_values = [float(v) for v in df["value"].tolist()]
    else:
        for c in df.select_dtypes("number").columns:
            artifact_values.extend(float(v) for v in df[c].tolist())

    claim_values = _extract_numbers(manuscript_text)
    mismatches: list[dict[str, Any]] = []
    for cv in claim_values:
        if not artifact_values:
            break
        closest = min(artifact_values, key=lambda a: abs(a - cv))
        abs_delta = abs(closest - cv)
        rel_delta = (
            abs_delta / abs(closest) if closest != 0 else float("inf")
        )
        if abs_delta > tolerance_abs and rel_delta > tolerance_rel:
            # `block` threshold is rel-delta > 5%; anything smaller is `warn`.
            mismatches.append(
                {
                    "claim_value": cv,
                    "closest_artifact_value": closest,
                    "abs_delta": round(abs_delta, 6),
                    "rel_delta": round(rel_delta, 6),
                    "severity": "block" if rel_delta > 0.05 else "warn",
                }
            )

    if any(m["severity"] == "block" for m in mismatches):
        status = "blocked"
    elif mismatches:
        status = "warned"
    else:
        status = "ok"
    return {"status": status, "mismatches": mismatches}

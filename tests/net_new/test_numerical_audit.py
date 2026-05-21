"""Tests for §5.2 post-experiment numerical claim audit."""
from __future__ import annotations

from plugins.vedix.mcp.lib.orchestrator.numerical_audit import audit_claims


def test_audit_passes_when_numbers_match(tmp_path):
    (tmp_path / "results.csv").write_text(
        "metric,value\naccuracy,0.853\nf1,0.792\n", encoding="utf-8"
    )
    manuscript = "Our model achieved 0.853 accuracy and 0.792 F1."
    report = audit_claims(
        manuscript_text=manuscript,
        results_path=tmp_path / "results.csv",
        tolerance_abs=1e-3,
    )
    assert report["status"] == "ok"
    assert len(report["mismatches"]) == 0


def test_audit_flags_mismatch(tmp_path):
    (tmp_path / "results.csv").write_text(
        "metric,value\naccuracy,0.853\n", encoding="utf-8"
    )
    manuscript = "Our model achieved 0.91 accuracy."
    report = audit_claims(
        manuscript_text=manuscript,
        results_path=tmp_path / "results.csv",
        tolerance_abs=1e-3,
    )
    assert report["status"] == "blocked"
    assert len(report["mismatches"]) >= 1
    assert report["mismatches"][0]["claim_value"] == 0.91


def test_audit_no_results_csv(tmp_path):
    report = audit_claims(
        manuscript_text="No numbers anywhere.",
        results_path=tmp_path / "absent.csv",
        tolerance_abs=1e-3,
    )
    assert report["status"] == "ok"
    assert "no results.csv" in report.get("note", "")

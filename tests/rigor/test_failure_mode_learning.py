"""Tests for §4.1 failure-mode learning."""
from __future__ import annotations

import pytest


def test_mark_failure_writes_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from plugins.vedix.mcp.lib.orchestrator.failure_mode_learning import (
        FailureCorpus, mark_failure,
    )
    mark_failure(job_id="abc123",
                 description="hallucinated DOI for Smith 2024 paper")
    fc = FailureCorpus()
    entries = fc.list_all()
    assert len(entries) == 1
    assert entries[0]["job_id"] == "abc123"
    assert "hallucinated" in entries[0]["description"]


def test_cluster_failures_produces_named_clusters(tmp_path, monkeypatch):
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("hdbscan")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from plugins.vedix.mcp.lib.orchestrator.failure_mode_learning import (
        cluster_failures, mark_failure,
    )
    citation_fail = ["hallucinated DOI for paper X"] * 10
    code_fail = ["ImportError on torch in experiment.py"] * 10
    method_fail = ["fabricated experimental method"] * 10
    for desc in citation_fail + code_fail + method_fail:
        mark_failure(job_id=f"j{hash(desc)}", description=desc)
    clusters = cluster_failures(min_cluster_size=5)
    assert len(clusters) >= 2

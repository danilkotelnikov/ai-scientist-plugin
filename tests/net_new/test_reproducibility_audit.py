"""Tests for §5.6 reproducibility audit.

The real audit fires `python -m venv` + `pip install` + a fresh
experiment run in a sandbox; in CI we mock `subprocess.run` so the test
exercises only the orchestrator logic (file staging, sandbox path
selection, numerical compare).
"""
from __future__ import annotations

from unittest.mock import patch

from plugins.vedix.mcp.lib.orchestrator.reproducibility_audit import (
    audit_reproducibility,
)


def test_audit_passes_when_results_match(tmp_path):
    # Stage the experiment + claimed results
    (tmp_path / "experiment.py").write_text(
        "import json, pathlib\n"
        "pathlib.Path('results.csv').write_text("
        "'metric,value\\naccuracy,0.85\\n')\n",
        encoding="utf-8",
    )
    (tmp_path / "results.csv").write_text(
        "metric,value\naccuracy,0.85\n", encoding="utf-8"
    )

    sandbox = tmp_path / "sandbox"

    def _fake_run(cmd, *args, **kwargs):
        # Plant the sandbox `results.csv` matching the claim before the
        # final comparison step runs.
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "results.csv").write_text(
            "metric,value\naccuracy,0.85\n", encoding="utf-8"
        )
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch(
        "plugins.vedix.mcp.lib.orchestrator.reproducibility_audit.subprocess.run",
        side_effect=_fake_run,
    ):
        report = audit_reproducibility(
            experiment_dir=tmp_path,
            claimed_results=tmp_path / "results.csv",
            sandbox_dir=sandbox,
        )
    assert report["status"] == "ok"


def test_audit_warns_when_results_differ(tmp_path):
    (tmp_path / "experiment.py").write_text(
        "pass\n", encoding="utf-8"
    )
    (tmp_path / "results.csv").write_text(
        "metric,value\naccuracy,0.85\n", encoding="utf-8"
    )

    sandbox = tmp_path / "sandbox"

    def _fake_run(cmd, *args, **kwargs):
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "results.csv").write_text(
            "metric,value\naccuracy,0.50\n", encoding="utf-8"
        )
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch(
        "plugins.vedix.mcp.lib.orchestrator.reproducibility_audit.subprocess.run",
        side_effect=_fake_run,
    ):
        report = audit_reproducibility(
            experiment_dir=tmp_path,
            claimed_results=tmp_path / "results.csv",
            sandbox_dir=sandbox,
        )
    assert report["status"] == "warned"
    assert len(report["mismatches"]) >= 1


def test_audit_blocks_when_sandbox_produces_no_results(tmp_path):
    (tmp_path / "experiment.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "results.csv").write_text(
        "metric,value\naccuracy,0.85\n", encoding="utf-8"
    )

    sandbox = tmp_path / "sandbox"

    def _fake_run(cmd, *args, **kwargs):
        # Sandbox runs but produces no `results.csv`.
        sandbox.mkdir(parents=True, exist_ok=True)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch(
        "plugins.vedix.mcp.lib.orchestrator.reproducibility_audit.subprocess.run",
        side_effect=_fake_run,
    ):
        report = audit_reproducibility(
            experiment_dir=tmp_path,
            claimed_results=tmp_path / "results.csv",
            sandbox_dir=sandbox,
        )
    assert report["status"] == "blocked"
    assert "results.csv" in report["reason"]

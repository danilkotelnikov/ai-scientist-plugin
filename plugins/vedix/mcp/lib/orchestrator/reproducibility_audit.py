"""§5.6 Reproducibility audit.

Given a finished experiment (an `experiment.py` + `requirements.txt` +
`results.csv` triple), spin up a *fresh* venv in an isolated sandbox,
install the declared deps, re-run the experiment, and compare the
sandbox's `results.csv` against the claimed one.

If the experiment crashes in the sandbox, exceeds the 900 s wall clock
budget, fails to produce `results.csv`, or produces numerically
inconsistent results, the audit reports `blocked` / `warned` accordingly.

CI mocks `subprocess.run` so this module's unit tests never actually
materialise a venv.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


def _venv_bin_dir(sandbox: Path) -> Path:
    """Resolve the venv `Scripts` (Windows) or `bin` (POSIX) directory."""
    if (sandbox / "venv" / "Scripts").exists():
        return sandbox / "venv" / "Scripts"
    return sandbox / "venv" / "bin"


def audit_reproducibility(
    *,
    experiment_dir: Path,
    claimed_results: Path,
    sandbox_dir: Path,
) -> dict[str, Any]:
    """Replay an experiment in a clean sandbox and compare results.

    Args:
        experiment_dir: Directory containing `experiment.py` and optionally
            `requirements.txt`.
        claimed_results: Path to the `results.csv` shipped with the
            manuscript.
        sandbox_dir: Where to materialise the fresh venv + replay. The
            directory is created (or wiped and recreated) by this call.

    Returns:
        dict with `status` ∈ {"ok", "warned", "blocked"}. `warned` and
        `blocked` payloads include a `reason` (blocked) or `mismatches`
        list (warned).
    """
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    sandbox_dir.mkdir(parents=True)

    # Stage the experiment files into the sandbox.
    for fn in ("experiment.py", "requirements.txt"):
        src = experiment_dir / fn
        if src.exists():
            shutil.copy2(src, sandbox_dir / fn)

    # Create venv + install + run. Each step is its own subprocess.run
    # call so the test can stub them independently.
    try:
        subprocess.run(
            ["python", "-m", "venv", str(sandbox_dir / "venv")],
            check=True,
        )
        bin_dir = _venv_bin_dir(sandbox_dir)
        pip = bin_dir / "pip"
        py = bin_dir / "python"
        if (sandbox_dir / "requirements.txt").exists():
            subprocess.run(
                [str(pip), "install", "-r", str(sandbox_dir / "requirements.txt")],
                check=True,
                cwd=sandbox_dir,
            )
        subprocess.run(
            [str(py), str(sandbox_dir / "experiment.py")],
            check=True,
            cwd=sandbox_dir,
            timeout=900,
        )
    except subprocess.CalledProcessError as e:
        return {
            "status": "blocked",
            "reason": "experiment crashed in sandbox",
            "stderr": str(e),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "blocked",
            "reason": "experiment exceeded 900s in sandbox",
        }

    sandbox_results = sandbox_dir / "results.csv"
    if not sandbox_results.exists():
        return {
            "status": "blocked",
            "reason": "sandbox did not produce results.csv",
        }

    df_claim = pd.read_csv(claimed_results)
    df_sandbox = pd.read_csv(sandbox_results)
    if list(df_claim.columns) != list(df_sandbox.columns):
        return {"status": "blocked", "reason": "column schemas differ"}

    mismatches: list[dict[str, Any]] = []
    for col in df_claim.select_dtypes("number").columns:
        for i, (a, b) in enumerate(zip(df_claim[col], df_sandbox[col])):
            if (
                abs(a - b) > 1e-3
                and abs(a - b) / max(abs(b), 1e-9) > 0.01
            ):
                mismatches.append(
                    {
                        "row": i,
                        "column": col,
                        "claim": float(a),
                        "sandbox": float(b),
                    }
                )
    return {
        "status": "ok" if not mismatches else "warned",
        "mismatches": mismatches,
    }

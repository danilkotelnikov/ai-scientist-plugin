"""
Experiment Runner with Dependency Management and Auto-Fix

Handles:
- Virtual environment creation
- Dependency installation from requirements.txt
- Experiment execution with timeout
- Multi-round error diagnosis and auto-fix
- Result extraction and metric collection
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class ExperimentRunner:
    """Runs Python experiments with dependency management and auto-fix."""

    def __init__(self, output_dir: str, timeout: int = 300, max_fix_rounds: int = 3):
        self.output_dir = Path(output_dir)
        self.timeout = timeout
        self.max_fix_rounds = max_fix_rounds
        self.venv_dir = self.output_dir / ".venv"
        self.fix_log = []

    def get_python(self) -> Path:
        """Get the venv Python executable."""
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"

    def get_pip(self) -> Path:
        """Get the venv pip executable."""
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "pip.exe"
        return self.venv_dir / "bin" / "pip"

    def create_venv(self) -> bool:
        """Create virtual environment if it doesn't exist."""
        if self.venv_dir.exists():
            print(f"[Runner] Venv already exists at {self.venv_dir}")
            return True
        print(f"[Runner] Creating venv at {self.venv_dir}")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(self.venv_dir)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"[Runner] Venv creation failed: {result.stderr}")
            return False
        # Upgrade pip
        subprocess.run(
            [str(self.get_pip()), "install", "--upgrade", "pip"],
            capture_output=True, timeout=120
        )
        print(f"[Runner] Venv created and pip upgraded")
        return True

    def install_dependencies(self, requirements_file: Optional[str] = None) -> bool:
        """Install dependencies from requirements.txt."""
        req_path = self.output_dir / (requirements_file or "requirements.txt")
        if not req_path.exists():
            print(f"[Runner] No requirements file found at {req_path}")
            return True

        print(f"[Runner] Installing dependencies from {req_path}")
        result = subprocess.run(
            [str(self.get_pip()), "install", "-r", str(req_path)],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            print(f"[Runner] pip install failed: {result.stderr[-500:]}")
            # Try installing packages one by one to identify failures
            return self._install_fallback(req_path)
        print(f"[Runner] Dependencies installed successfully")
        return True

    def _install_fallback(self, req_path: Path) -> bool:
        """Try installing packages one by one."""
        packages = []
        with open(req_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    packages.append(line)

        installed = 0
        failed = []
        for pkg in packages:
            result = subprocess.run(
                [str(self.get_pip()), "install", pkg],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                installed += 1
            else:
                failed.append(pkg)
                print(f"[Runner] Failed to install {pkg}")

        print(f"[Runner] Installed {installed}/{len(packages)} packages, "
              f"{len(failed)} failed: {failed}")
        return len(failed) == 0

    def run_experiment(self) -> dict:
        """Run experiment.py with auto-fix loop."""
        experiment_file = self.output_dir / "experiment.py"
        if not experiment_file.exists():
            return {"exit_code": -1, "error": "experiment.py not found"}

        fix_log = []
        final_exit_code = -1

        for attempt in range(1, self.max_fix_rounds + 1):
            print(f"[Runner] Attempt {attempt}/{self.max_fix_rounds}")

            stdout_file = self.output_dir / "experiment_stdout.txt"
            stderr_file = self.output_dir / "experiment_stderr.txt"

            start_time = time.time()
            try:
                with open(stdout_file, "w") as out, open(stderr_file, "w") as err:
                    proc = subprocess.run(
                        [str(self.get_python()), str(experiment_file)],
                        stdout=out, stderr=err,
                        timeout=self.timeout,
                        cwd=str(self.output_dir)
                    )
                    final_exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                final_exit_code = -1
                with open(stderr_file, "a") as err:
                    err.write(f"\n[TIMEOUT] Experiment exceeded {self.timeout}s limit\n")

            runtime = time.time() - start_time
            print(f"[Runner] Attempt {attempt}: exit_code={final_exit_code}, "
                  f"runtime={runtime:.1f}s")

            if final_exit_code == 0:
                break

            # Diagnose and attempt auto-fix
            if attempt < self.max_fix_rounds:
                fix_applied = self._diagnose_and_fix(
                    stderr_file, experiment_file, attempt
                )
                fix_log.append({
                    "attempt": attempt,
                    "exit_code": final_exit_code,
                    "error_snippet": self._read_tail(stderr_file, 200),
                    "fix_applied": fix_applied,
                    "runtime_seconds": round(runtime, 1)
                })
                if not fix_applied:
                    print(f"[Runner] No auto-fix available, stopping")
                    break

        # Extract results
        results = self._extract_results()

        return {
            "exit_code": final_exit_code,
            "runtime_seconds": round(runtime, 1),
            "fix_attempts": len(fix_log),
            "fix_log": fix_log,
            "results": results,
            "npy_files": len(list(self.output_dir.glob("*.npy"))),
            "figures": len(list((self.output_dir / "figures").glob("*.png")))
                       if (self.output_dir / "figures").exists() else 0
        }

    def _diagnose_and_fix(self, stderr_file: Path, experiment_file: Path,
                          attempt: int) -> str:
        """Read stderr and attempt an auto-fix."""
        if not stderr_file.exists():
            return ""

        with open(stderr_file) as f:
            stderr = f.read()

        # ImportError: missing package
        if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
            import re
            match = re.search(r"No module named ['\"](\w+)['\"]", stderr)
            if match:
                pkg = match.group(1)
                req_file = self.output_dir / "requirements.txt"
                with open(req_file, "a") as f:
                    f.write(f"\n{pkg}\n")
                self.install_dependencies()
                return f"Added '{pkg}' to requirements.txt and reinstalled"

        # SyntaxError
        if "SyntaxError" in stderr:
            import re
            match = re.search(r"File.*line (\d+)", stderr)
            if match:
                line_num = int(match.group(1))
                return f"SyntaxError at line {line_num} — requires manual fix"

        # FileNotFoundError
        if "FileNotFoundError" in stderr:
            import re
            match = re.search(r"No such file or directory: ['\"](.+?)['\"]", stderr)
            if match:
                missing_path = self.output_dir / match.group(1)
                missing_path.parent.mkdir(parents=True, exist_ok=True)
                return f"Created missing directory {missing_path.parent}"

        # Timeout
        if "TIMEOUT" in stderr:
            return "Experiment timed out — requires simplification (manual)"

        return ""  # No auto-fix available

    def _read_tail(self, file_path: Path, n_chars: int) -> str:
        """Read last n_chars of a file."""
        if not file_path.exists():
            return ""
        with open(file_path, "rb") as f:
            f.seek(max(0, os.path.getsize(file_path) - n_chars))
            return f.read().decode("utf-8", errors="replace")

    def _extract_results(self) -> dict:
        """Extract results from output files."""
        results = {}

        # Read stdout
        stdout_file = self.output_dir / "experiment_stdout.txt"
        if stdout_file.exists():
            with open(stdout_file) as f:
                results["stdout"] = f.read()[:2000]

        # Read results.csv
        csv_file = self.output_dir / "results.csv"
        if csv_file.exists():
            with open(csv_file) as f:
                lines = f.readlines()[:20]
                results["csv_preview"] = "".join(lines)

        # List npy files
        npy_files = list(self.output_dir.glob("*.npy"))
        results["npy_files"] = [f.name for f in npy_files]

        # List figures
        fig_dir = self.output_dir / "figures"
        if fig_dir.exists():
            results["figures"] = [f.name for f in fig_dir.glob("*.png")]

        return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run AI-Scientist experiment")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    parser.add_argument("--max-fix-rounds", type=int, default=3, help="Max auto-fix rounds")
    args = parser.parse_args()

    runner = ExperimentRunner(args.output_dir, args.timeout, args.max_fix_rounds)
    runner.create_venv()
    runner.install_dependencies()
    result = runner.run_experiment()
    print(json.dumps(result, indent=2))

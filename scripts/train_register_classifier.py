"""Vedix — Layer B classifier auto-dispatcher (§5.3.2.c).

Detects available hardware and dispatches to the GPU or CPU training
sibling. Either ``--force-cpu``/``--force-gpu`` overrides the detection.

Usage::

    python scripts/train_register_classifier.py --auto                     # auto-pick
    python scripts/train_register_classifier.py --force-cpu                # skip GPU
    python scripts/train_register_classifier.py --only-pair chemistry:en   # one pair

Hardware thresholds:

  • GPU path: ``torch.cuda.is_available()`` and ``total_memory ≥ 7 GB``.
  • CPU path: ``psutil.cpu_count(logical=False) ≥ 16`` and
    ``psutil.virtual_memory().total ≥ 64 GB``.
  • Neither met: raise :class:`HardwareInsufficientError`.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class HardwareInsufficientError(SystemExit):
    """Raised when neither GPU nor CPU thresholds are met."""


def detect_hardware(
    *,
    gpu_min_gb: float = 7.0,
    cpu_min_cores: int = 16,
    ram_min_gb: float = 64.0,
) -> str:
    """Return ``"gpu"`` or ``"cpu"``; raise on insufficient hardware."""
    # GPU branch
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024**3)
            if vram_gb >= gpu_min_gb:
                return "gpu"
            print(
                f"[auto] GPU detected but only {vram_gb:.1f} GB VRAM "
                f"(need ≥ {gpu_min_gb} GB); falling back to CPU"
            )
    except ImportError:
        pass

    # CPU branch
    try:
        import psutil

        cpu_cores = psutil.cpu_count(logical=False) or 0
        ram_gb = psutil.virtual_memory().total / (1024**3)
    except ImportError:
        # No psutil → no way to know the CPU is large enough. Be strict.
        raise HardwareInsufficientError(
            "psutil not installed; cannot detect CPU. "
            "Install with: pip install psutil"
        )
    if cpu_cores >= cpu_min_cores and ram_gb >= ram_min_gb:
        return "cpu"
    raise HardwareInsufficientError(
        f"hardware insufficient: cpu_cores={cpu_cores}, ram={ram_gb:.1f} GB, no GPU. "
        f"Need ≥{cpu_min_cores} cores + {ram_min_gb} GB RAM or a GPU with "
        f"≥{gpu_min_gb} GB VRAM. Or use Vedix.ai SaaS hosted training (Pro tier)."
    )


def build_command(
    *,
    target: str,
    args: argparse.Namespace,
    scripts_dir: Path,
) -> list[str]:
    """Return the subprocess command for the chosen sibling script."""
    script = scripts_dir / (
        "train_register_classifier_gpu.py"
        if target == "gpu"
        else "train_register_classifier_cpu.py"
    )
    cmd = [
        sys.executable,
        str(script),
        "--corpus-root",
        str(args.corpus_root),
        "--output-root",
        str(args.output_root),
        "--languages",
        args.languages,
        "--disciplines",
        args.disciplines,
    ]
    if args.only_pair:
        cmd += ["--only-pair", args.only_pair]
    return cmd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-root", required=True, type=Path)
    ap.add_argument("--output-root", required=True, type=Path)
    ap.add_argument("--languages", default="en,ru,es,de,fr,zh,ja")
    ap.add_argument(
        "--disciplines",
        default="chemistry,biology,medicine,physics,mathematics,geology,"
        "computer_science,humanities",
    )
    ap.add_argument("--only-pair", default=None)
    ap.add_argument("--auto", action="store_true", default=True)
    ap.add_argument("--force-cpu", action="store_true")
    ap.add_argument("--force-gpu", action="store_true")
    args = ap.parse_args()

    if args.force_cpu:
        target = "cpu"
    elif args.force_gpu:
        target = "gpu"
    else:
        target = detect_hardware()

    scripts_dir = Path(__file__).resolve().parent
    cmd = build_command(target=target, args=args, scripts_dir=scripts_dir)
    print(f"[auto] dispatching to {cmd[1]}")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":  # pragma: no cover
    main()

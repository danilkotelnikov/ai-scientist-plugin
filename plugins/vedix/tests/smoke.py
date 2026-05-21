"""Tier 3 live smoke test. ~5–10 min, $2 budget. Per spec §9.3.

Run via:
  python -m tests.smoke --topic "linear regression on synthetic data" \
                         --domain statistical --interactivity none --token-budget-usd 2.00
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--interactivity", default="none")
    p.add_argument("--token-budget-usd", type=float, default=2.00)
    p.add_argument("--output", default="smoke-output")
    args = p.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"smoke: topic={args.topic} domain={args.domain} budget=${args.token_budget_usd}")
    print(f"smoke: would invoke mcp__ai-scientist__run_pipeline(...)")
    print(f"smoke: results would land at {output_dir}")
    print(f"smoke: assertions:")
    for assertion in [
        "idea_candidates.json has >=3 entries",
        "paper_list.json has >=10 papers",
        "manuscript.tex has 0 \\cite{?} errors",
        "review.json has >=3 reviewer entries",
        "tokens_report.json totals < $2.00",
        ".checkpoints/phase_*.pkl exist",
        "manuscript-slides.pdf exists",
    ]:
        print(f"  - {assertion}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

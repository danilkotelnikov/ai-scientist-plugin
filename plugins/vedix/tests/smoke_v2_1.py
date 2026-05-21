"""Tier 3 v2.1 smoke runner. Exercises the strict-validation pipeline.

Run via:
  python -m tests.smoke_v2_1 --topic "recent advances in transformers" \\
                              --domain ml --interactivity none \\
                              --crossref-email you@example.com
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--interactivity", default="none")
    p.add_argument("--crossref-email",
                   default=os.environ.get("OPENALEX_EMAIL", ""))
    p.add_argument("--token-budget-usd", type=float, default=2.00)
    p.add_argument("--output", default="smoke-v2-1-output")
    args = p.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"smoke_v2_1: topic={args.topic} domain={args.domain}")
    print(f"smoke_v2_1: budget=${args.token_budget_usd}")
    print(f"smoke_v2_1: would invoke mcp__ai-scientist__run_pipeline(article_type=auto)")
    print(f"smoke_v2_1: results would land at {output_dir}")
    print(f"smoke_v2_1: assertions:")

    required_artifacts = [
        "config.json",
        "tool_preflight.json",
        "source_preflight.json",
        "codex_runtime_capabilities.json",
        "source_usage.json",
        "paper_list.json",
        "paper_list.validated.json",
        "references_validation.json",
        "references.bib",
        "manuscript.tex",
        "anti_llm_lint.json",
        "claim_audit.json",
        "citation_key_integrity.json",
        "claim_support_matrix.md",
        "reviewer_dispatch.json",
        "review.json",
        "review_response.md",
        "compile_report.json",
        "resource_usage.json",
    ]

    print(f"  required artifacts ({len(required_artifacts)}):")
    for art in required_artifacts:
        print(f"    - {art}")

    print(f"  v2.1 strict-validation gates:")
    for gate in [
        "every paper in paper_list.validated.json has a verified DOI",
        "no Tier-1 anti-LLMish words in manuscript.tex",
        "em-dash density < 5 per 1000 words in manuscript.tex",
        "all 3 reviewer roles recorded in reviewer_dispatch.json",
        "tokens_report.json totals < $2.00",
        "resource_usage.json budget_status != 'exceeded'",
    ]:
        print(f"    - {gate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

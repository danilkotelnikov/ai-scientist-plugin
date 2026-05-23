"""Linguistic audit orchestrator module.

Runs the per-locale rule set across a manuscript paragraph (or whole
text), emits ``linguistic_audit.json`` to the job's output directory,
and returns the structured verdict the pipeline uses to decide whether
to re-dispatch a paragraph back to the writer.

The pipeline calls this from two integration points:

1. **Per-paragraph, in-flight, during manuscript-writer fan-out.**
   Each section writer's draft paragraph is validated before being
   concatenated into the section. ``severity="block"`` violations
   cause a re-write (up to ``writing_style.max_clarification_redispatches``).

2. **Once-over, post-LaTeX-compile, before stage-gate exit.**
   Final pass over ``manuscript.tex`` after the citator finishes its
   enrichment pass. Produces the audit JSON the reviewer reads as
   part of its own ledger.

The audit is also called by the reviewer agent's review_locale.json
step, which makes it a publicly observable artifact (the reviewer's
ledger references the same JSON).
"""
from __future__ import annotations

import json
from pathlib import Path

from .locale.linguistic_rules import (
    Violation,
    has_blocking,
    system_prompt_fragment,
    validate,
)
from .locale.router import get_locale
from .locale.rules.router import get_rules, has_rules_for


def audit_text(
    text: str,
    *,
    language: str,
) -> dict[str, object]:
    """Validate ``text`` against all rules for the given language.

    Returns a dict with the schema:

    .. code-block:: json

       {
         "language": "ru",
         "violations": [Violation.as_dict(), ...],
         "violation_count": 7,
         "blocking_count": 2,
         "has_blocking": true,
         "rule_summary": {"ru.decimal_comma": 3, "ru.guillemets": 1, ...}
       }

    Unknown languages return an empty violation list and
    ``has_blocking=False``.
    """
    if not has_rules_for(language):
        return {
            "language": language,
            "violations": [],
            "violation_count": 0,
            "blocking_count": 0,
            "has_blocking": False,
            "rule_summary": {},
        }

    rules = get_rules(language)
    violations: list[Violation] = validate(text, rules)
    summary: dict[str, int] = {}
    for v in violations:
        summary[v.rule_id] = summary.get(v.rule_id, 0) + 1

    blocking = sum(1 for v in violations if v.severity == "block")
    return {
        "language": language,
        "violations": [v.as_dict() for v in violations],
        "violation_count": len(violations),
        "blocking_count": blocking,
        "has_blocking": blocking > 0,
        "rule_summary": summary,
    }


def audit_manuscript_file(
    manuscript_path: Path,
    *,
    language: str,
    output_path: Path | None = None,
) -> dict[str, object]:
    """Audit a ``manuscript.tex`` (or ``.md``) and write the JSON report.

    Args:
        manuscript_path: Path to the manuscript source file.
        language: ISO 639-1 code of the manuscript's language.
        output_path: Where to write ``linguistic_audit.json``.
            Defaults to ``manuscript_path.parent / "linguistic_audit.json"``.

    Returns:
        The audit dict (also written to disk).
    """
    text = manuscript_path.read_text(encoding="utf-8")
    audit = audit_text(text, language=language)

    out = output_path or (manuscript_path.parent / "linguistic_audit.json")
    out.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return audit


def build_system_prompt_fragment(language: str) -> str:
    """Return the system-prompt fragment a writer/reviewer should inject.

    The fragment is structured by category (typography, orthography,
    citation_style, register) and lists every blocking + warning rule
    with imperative phrasing and a bad → good example.

    The same rule set is then enforced by :func:`audit_text` after the
    paragraph is written. This double-coverage — prompt + post-hoc
    validator — is what makes the behavior reproducible across model
    versions: the model is briefed before, audited after, and any
    blocking violation triggers a re-dispatch with the rule and the
    specific bad span inlined as feedback.

    Returns an empty string for unsupported languages — callers
    should treat that as "no locale-specific guidance needed".
    """
    if not has_rules_for(language):
        return ""

    rules = get_rules(language)
    cfg = get_locale(language)
    return system_prompt_fragment(
        locale_code=language,
        locale_name=cfg.name,
        rules=rules,
    )


def format_violations_for_redispatch(violations: list[Violation]) -> str:
    """Format a violation list as natural-language feedback for the writer.

    Emitted as part of the re-dispatch prompt when a paragraph fails
    the audit. Each violation is rendered as:

       - [rule_id, severity] description
         Observed: "<bad substring>" at line N column M

    The model sees this verbatim and is asked to rewrite the offending
    sentences. Empty violation list → empty string.
    """
    if not violations:
        return ""

    lines = ["The previous draft violated the following linguistic rules:", ""]
    for v in violations:
        lines.append(f"- [{v.rule_id}, {v.severity}] {v.description}")
        lines.append(f'  Observed: "{v.observed}" at line {v.line}, column {v.column}.')
    lines.append("")
    lines.append(
        "Rewrite the offending sentences so they comply. "
        "Preserve the original meaning and the original citation references."
    )
    return "\n".join(lines)


__all__ = [
    "audit_text",
    "audit_manuscript_file",
    "build_system_prompt_fragment",
    "format_violations_for_redispatch",
    "has_blocking",
]

"""Classical linguistic and terminological correctness rules per locale.

The shallow ``register_lints`` blacklists in each ``LocaleConfig`` catch
LLM register slips. This module is the heavyweight companion: it encodes
the classical typesetting + terminology + register rules each academic
locale demands. Russian gets the GOST 7.0.5-2008 + Rosenthal handbook
treatment (guillemets, decimal comma, ё preservation, gendered participle
agreement, ...); English gets the Strunk & White + Chicago Manual
scientific register (decimal point, oxford-comma consistency, hedge
calibration, ...). Spanish, German, French, Chinese, Japanese get the
typesetting essentials.

Public surface
--------------

:class:`Rule`
    One named rule (id, severity, description, validator callable).

:class:`Violation`
    A specific span in text that breaks a rule.

:func:`validate`
    Run every rule for a locale across a piece of text, return all
    violations.

:func:`system_prompt_fragment`
    Render the locale's rules as a natural-language fragment suitable
    for splicing into a manuscript-writer or reviewer system prompt.
    This is what makes the behavior **reproducible** rather than
    prompt-dependent: the prompt fragment is generated mechanically
    from the same rule set the validator runs, so the model is told
    exactly what the post-hoc validator will check.

The pipeline calls :func:`validate` on every generated paragraph; any
``severity="block"`` violation triggers a re-dispatch with the
violations inlined as feedback. ``severity="warn"`` violations are
logged to ``linguistic_audit.json`` but don't block stage-gate exit.

This module imports zero third-party deps. Pure ``re`` + stdlib.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable


# A validator returns the list of bad spans it found, each as
# (start, end, observed_substring). The harness wraps each into a
# Violation with the rule's metadata.
ValidatorResult = list[tuple[int, int, str]]
Validator = Callable[[str], ValidatorResult]


@dataclass(frozen=True)
class Rule:
    """One named rule.

    Attributes:
        id: Stable identifier (``ru.decimal_comma``, ``en.oxford_comma``, ...).
            Used in ``linguistic_audit.json`` and in error messages back to
            the model on re-dispatch.
        severity: ``"block"`` — manuscript fails stage-gate exit; the
            sentence is re-dispatched with the violation inlined.
            ``"warn"`` — logged, but doesn't block.
            ``"info"`` — surfaced as advisory only, no action.
        category: Free-text taxonomy (``"typography"``, ``"terminology"``,
            ``"citation_style"``, ``"register"``, ``"orthography"``).
        description: Short natural-language statement of the rule. Used
            both in error messages and in the system-prompt fragment.
            Must be present-tense imperative ("Use guillemets …").
        prompt_directive: Optional override for the system-prompt
            fragment. If omitted, ``description`` is used. Use this when
            the validator's wording is awkward as an instruction
            (e.g. machine-friendly "decimal comma" → prompt-friendly
            "Write decimal numbers with a comma, not a period").
        validator: Callable from text to a list of bad spans. Pure
            function — no I/O, no state.
        example_bad: Canonical example string that triggers the rule.
            Used in tests and in the prompt fragment as a "don't do
            this" demonstration.
        example_good: Canonical fixed version. Used in tests + prompt.
        ignore_inside: Regex patterns whose interior is exempt from the
            rule. Default exempts LaTeX math (``$...$``, ``\\(...\\)``,
            ``\\begin{equation}...\\end{equation}``) and verbatim
            blocks (``\\begin{verbatim}...\\end{verbatim}``) since
            those are intentionally not natural-language prose.
    """

    id: str
    severity: str  # "block" | "warn" | "info"
    category: str
    description: str
    validator: Validator
    example_bad: str = ""
    example_good: str = ""
    prompt_directive: str = ""
    ignore_inside: tuple[str, ...] = (
        r"\$[^$]+\$",
        r"\\\([^)]+\\\)",
        r"\\begin\{equation\}.*?\\end\{equation\}",
        r"\\begin\{verbatim\}.*?\\end\{verbatim\}",
        r"\\cite[a-z]*\{[^}]+\}",  # citation commands carry their own format
        r"\\ref\{[^}]+\}",
        r"\\label\{[^}]+\}",
    )


@dataclass(frozen=True)
class Violation:
    """One concrete bad span found in text."""

    rule_id: str
    severity: str
    category: str
    description: str
    start: int
    end: int
    observed: str
    line: int = 0  # 1-indexed line number
    column: int = 0  # 1-indexed column

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "start": self.start,
            "end": self.end,
            "observed": self.observed,
            "line": self.line,
            "column": self.column,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _build_ignore_mask(text: str, ignore_patterns: Iterable[str]) -> list[bool]:
    """Return a per-character mask; True means 'inside an ignore region'.

    Validators consult this mask to skip math/verbatim/citation spans.
    """
    mask = [False] * len(text)
    for pat in ignore_patterns:
        for m in re.finditer(pat, text, flags=re.DOTALL):
            for i in range(m.start(), m.end()):
                if i < len(mask):
                    mask[i] = True
    return mask


def _line_col(text: str, offset: int) -> tuple[int, int]:
    """Convert a 0-indexed character offset to a 1-indexed (line, column)."""
    if offset <= 0:
        return 1, 1
    prefix = text[:offset]
    line = prefix.count("\n") + 1
    last_nl = prefix.rfind("\n")
    column = offset - last_nl if last_nl >= 0 else offset + 1
    return line, column


def validate(text: str, rules: Iterable[Rule]) -> list[Violation]:
    """Run every rule across ``text`` and return all violations.

    Violations from rule's validator that fall inside any of the rule's
    ``ignore_inside`` patterns are dropped before being wrapped.
    """
    violations: list[Violation] = []
    for rule in rules:
        mask = _build_ignore_mask(text, rule.ignore_inside)
        for (start, end, observed) in rule.validator(text):
            # Skip violations that lie entirely inside an ignored span.
            if all(mask[i] for i in range(start, min(end, len(mask)))):
                continue
            line, col = _line_col(text, start)
            violations.append(
                Violation(
                    rule_id=rule.id,
                    severity=rule.severity,
                    category=rule.category,
                    description=rule.description,
                    start=start,
                    end=end,
                    observed=observed,
                    line=line,
                    column=col,
                )
            )
    return violations


def has_blocking(violations: Iterable[Violation]) -> bool:
    """Return True if any violation has severity 'block'."""
    return any(v.severity == "block" for v in violations)


# ---------------------------------------------------------------------------
# System-prompt fragment renderer
# ---------------------------------------------------------------------------


def system_prompt_fragment(
    locale_code: str,
    locale_name: str,
    rules: Iterable[Rule],
    *,
    include_examples: bool = True,
    severity_filter: tuple[str, ...] | None = ("block", "warn"),
) -> str:
    """Render the locale's rules into a natural-language prompt fragment.

    The fragment is structured by category so the model can group
    related rules. Each rule appears as an imperative bullet drawing on
    ``prompt_directive`` (fallback ``description``) plus, optionally, a
    'bad → good' example.

    The exact same rule set is then enforced by :func:`validate` after
    generation. This double-coverage — prompt + validator — is what
    delivers reproducible behavior: the model is briefed before, audited
    after. Drift is caught by the validator and re-dispatched with the
    specific violation inlined.

    Args:
        locale_code: ISO 639-1 code (used in section headers).
        locale_name: Human-readable name (``"Russian"``).
        rules: The rule set for the locale.
        include_examples: Append bad → good demonstrations.
        severity_filter: Only render rules whose severity is in this
            tuple. Default skips ``"info"`` to keep the prompt compact.
    """
    rules_filtered = [
        r for r in rules
        if severity_filter is None or r.severity in severity_filter
    ]
    if not rules_filtered:
        return ""

    by_category: dict[str, list[Rule]] = {}
    for r in rules_filtered:
        by_category.setdefault(r.category, []).append(r)

    lines: list[str] = []
    lines.append(f"## Linguistic rules for {locale_name} ({locale_code})")
    lines.append("")
    lines.append(
        "These rules are validated automatically after every paragraph"
        + " you write. Violations trigger a re-write with the specific"
        + " violation inlined as feedback. Internalize them before drafting."
    )
    lines.append("")

    for category in sorted(by_category):
        cat_display = category.replace("_", " ").capitalize()
        lines.append(f"### {cat_display}")
        lines.append("")
        for r in by_category[category]:
            directive = r.prompt_directive or r.description
            sev_tag = "(block)" if r.severity == "block" else "(warn)"
            lines.append(f"- {sev_tag} {directive}")
            if include_examples and r.example_bad and r.example_good:
                lines.append(f"  - Avoid: `{r.example_bad}`")
                lines.append(f"  - Use:   `{r.example_good}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Validator factories — common patterns reused across locales
# ---------------------------------------------------------------------------


def regex_validator(pattern: str, flags: int = 0) -> Validator:
    """A validator that flags every match of ``pattern`` as a violation.

    The matched substring becomes the ``observed`` field of the
    Violation. Use this for "this character/sequence is forbidden" rules
    (straight ASCII quotes, decimal point in Russian, ...).
    """
    compiled = re.compile(pattern, flags)

    def _check(text: str) -> ValidatorResult:
        return [(m.start(), m.end(), m.group(0)) for m in compiled.finditer(text)]

    return _check


def regex_pair_validator(
    forbidden: str, allowed: str, flags: int = 0,
) -> Validator:
    """Flag matches of ``forbidden`` only when ``allowed`` doesn't overlap.

    Useful for rules like "decimal point in scientific text is bad, but
    decimal point inside a DOI / URL / version string is fine". The
    ``allowed`` pattern carves out exemptions: matches of ``forbidden``
    that lie entirely inside a match of ``allowed`` are skipped.
    """
    forbidden_re = re.compile(forbidden, flags)
    allowed_re = re.compile(allowed, flags)

    def _check(text: str) -> ValidatorResult:
        allowed_spans = [(m.start(), m.end()) for m in allowed_re.finditer(text)]
        out: ValidatorResult = []
        for m in forbidden_re.finditer(text):
            inside_allowed = any(
                a_start <= m.start() and m.end() <= a_end
                for (a_start, a_end) in allowed_spans
            )
            if not inside_allowed:
                out.append((m.start(), m.end(), m.group(0)))
        return out

    return _check


def word_list_validator(words: Iterable[str], case_sensitive: bool = False) -> Validator:
    """Flag occurrences of any word in ``words`` (whole-word match).

    Used for anglicism blacklists, banned LLMishms, etc.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b"
    return regex_validator(pattern, flags)


__all__ = [
    "Rule",
    "Validator",
    "ValidatorResult",
    "Violation",
    "validate",
    "has_blocking",
    "system_prompt_fragment",
    "regex_validator",
    "regex_pair_validator",
    "word_list_validator",
]

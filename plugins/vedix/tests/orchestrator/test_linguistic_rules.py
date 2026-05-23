"""Reproducibility tests for the linguistic rules engine.

For every rule across every locale, we run the rule's ``example_bad``
through the validator and assert it fires; we run the ``example_good``
through and assert it doesn't. This is the canonical proof that the
behavior is reproducible — any future change that breaks a rule's
detection or starts a false positive on a canonical good example will
break a named test.

Plus a handful of end-to-end tests that exercise the orchestrator
helpers (``audit_text``, ``build_system_prompt_fragment``,
``format_violations_for_redispatch``).
"""
from __future__ import annotations

import pytest

# This tests/orchestrator/ directory has a conftest.py that injects the
# plugin's local `mcp/` as a namespace package. That lets us import via
# the canonical `mcp.lib.orchestrator.*` paths the runtime uses.
from mcp.lib.orchestrator.linguistic_audit import (
    audit_text,
    build_system_prompt_fragment,
    format_violations_for_redispatch,
)
from mcp.lib.orchestrator.locale.linguistic_rules import (  # noqa: E402
    Violation,
    validate,
)
from mcp.lib.orchestrator.locale.rules.router import (  # noqa: E402
    get_rules,
    has_rules_for,
)


# ---------------------------------------------------------------------------
# Parametrized canonical-example coverage
# ---------------------------------------------------------------------------

ALL_LOCALES = ["ru", "en", "es", "de", "fr", "zh", "ja"]


def _enumerate_rules_with_examples():
    """Yield (locale, rule) for every rule that ships canonical examples.

    Rules without ``example_bad`` + ``example_good`` are advisory only
    (e.g. ``en.citation_format``, ``en.first_person_overuse``); we don't
    test those since their validators return [] by design.
    """
    for locale in ALL_LOCALES:
        for rule in get_rules(locale):
            if rule.example_bad and rule.example_good:
                yield locale, rule


@pytest.mark.parametrize(
    "locale,rule",
    list(_enumerate_rules_with_examples()),
    ids=lambda v: v.id if hasattr(v, "id") else str(v),
)
def test_rule_fires_on_bad_example(locale: str, rule) -> None:
    """Every rule's ``example_bad`` must trigger at least one violation
    from that specific rule.
    """
    violations = validate(rule.example_bad, [rule])
    assert any(v.rule_id == rule.id for v in violations), (
        f"Rule {rule.id} did not fire on its own example_bad: {rule.example_bad!r}"
    )


@pytest.mark.parametrize(
    "locale,rule",
    list(_enumerate_rules_with_examples()),
    ids=lambda v: v.id if hasattr(v, "id") else str(v),
)
def test_rule_passes_good_example(locale: str, rule) -> None:
    """Every rule's ``example_good`` must produce zero violations from
    that specific rule.
    """
    violations = validate(rule.example_good, [rule])
    same_rule_violations = [v for v in violations if v.rule_id == rule.id]
    assert not same_rule_violations, (
        f"Rule {rule.id} fired on its own example_good "
        f"{rule.example_good!r}: {same_rule_violations}"
    )


# ---------------------------------------------------------------------------
# Russian — focused integration tests
# ---------------------------------------------------------------------------


def test_ru_clean_paragraph_passes() -> None:
    """A canonical clean Russian paragraph should produce zero blocking
    violations.
    """
    clean = (
        "Концентрация катализатора составила 0,45 мМ. "
        "Полученный результат «значительно превышает» ожидаемый. "
        "Эксперимент был проведён в марте 2026 года."
    )
    audit = audit_text(clean, language="ru")
    assert audit["has_blocking"] is False, (
        f"Clean paragraph triggered blocking violations: "
        f"{audit['rule_summary']}"
    )


def test_ru_dirty_paragraph_triggers_multiple_rules() -> None:
    """A canonical dirty paragraph hits at least 5 distinct rule_ids."""
    dirty = (
        'Концентрация составила 0.45 мМ. '
        'Этот пайплайн "значительно превышает" ожидаемый результат. '
        'В Марте мы провели контент-анализ. '
        'Метод DFT - наиболее распространённый подход. '
        'Этот эффект был ранее описан (Иванов, 2024).'
    )
    audit = audit_text(dirty, language="ru")
    assert audit["violation_count"] >= 7, audit
    assert audit["has_blocking"] is True, "decimal_comma and guillemets are blocking"
    triggered = set(audit["rule_summary"].keys())
    expected_subset = {
        "ru.guillemets",
        "ru.decimal_comma",
        "ru.anglicism_guard",
        "ru.em_dash_spacing",
        "ru.citation_brackets",
    }
    missing = expected_subset - triggered
    assert not missing, (
        f"Expected these rules to fire on the dirty paragraph but "
        f"they didn't: {missing}. Triggered: {triggered}"
    )


def test_ru_decimal_comma_ignores_doi() -> None:
    """A DOI like ``10.1038/s41586-024-07930-y`` must NOT trigger
    decimal_comma even though it contains '10.1038' which matches the
    raw regex.
    """
    text = "См. публикацию по DOI 10.1038/s41586-024-07930-y."
    audit = audit_text(text, language="ru")
    decimal_violations = [
        v for v in audit["violations"]
        if v["rule_id"] == "ru.decimal_comma"
    ]
    assert not decimal_violations, (
        f"DOI triggered decimal_comma rule (regression): {decimal_violations}"
    )


def test_ru_decimal_comma_ignores_inline_math() -> None:
    """LaTeX inline math ``$0.45$`` should not trigger decimal_comma
    because numerals inside math mode are typeset via LaTeX, which
    handles locale conversion separately.
    """
    text = "Константа диссоциации равна $K_d = 0.45$ нМ."
    audit = audit_text(text, language="ru")
    decimal_violations = [
        v for v in audit["violations"]
        if v["rule_id"] == "ru.decimal_comma"
    ]
    assert not decimal_violations, decimal_violations


def test_ru_guillemets_blocks_ascii_quotes() -> None:
    """ASCII double quotes around Cyrillic text must trigger
    ru.guillemets with severity='block'.
    """
    text = 'Эффект был назван "аномальным".'
    audit = audit_text(text, language="ru")
    assert audit["has_blocking"] is True
    quote_violations = [
        v for v in audit["violations"]
        if v["rule_id"] == "ru.guillemets"
    ]
    assert len(quote_violations) >= 1


# ---------------------------------------------------------------------------
# English — focused integration tests
# ---------------------------------------------------------------------------


def test_en_clean_paragraph_passes() -> None:
    clean = (
        "The catalyst concentration was 0.45 mM. The activity exceeded "
        "the control by 12%. The mechanism is consistent with prior work."
    )
    audit = audit_text(clean, language="en")
    assert audit["has_blocking"] is False, audit["rule_summary"]


def test_en_llm_openers_block() -> None:
    """The hard-blocking 'Furthermore, it is important to note' opener
    must fire en.llm_openers with severity='block'.
    """
    text = (
        "Furthermore, it is important to note that the catalyst "
        "demonstrates remarkable activity."
    )
    audit = audit_text(text, language="en")
    assert audit["has_blocking"] is True
    opener_violations = [
        v for v in audit["violations"]
        if v["rule_id"] == "en.llm_openers"
    ]
    assert len(opener_violations) >= 1


def test_en_thousands_separator_catches_russian_drift() -> None:
    """If a Russian-trained model produces '1 234 patients' in English
    output, the rule should fire as a locale-drift catch.
    """
    text = "The cohort included 1 234 patients across three sites."
    audit = audit_text(text, language="en")
    drift = [
        v for v in audit["violations"]
        if v["rule_id"] == "en.thousands_separator"
    ]
    assert len(drift) >= 1


# ---------------------------------------------------------------------------
# Other locales — minimum-acceptance smoke
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["es", "de", "fr"])
def test_european_decimal_comma_blocks(locale: str) -> None:
    """Spanish, German, French all require decimal comma."""
    text = "Sample 0.45"
    audit = audit_text(text, language=locale)
    assert audit["has_blocking"] is True, audit


def test_zh_fullwidth_punctuation_blocks() -> None:
    """Chinese with half-width punctuation between CJK chars must block."""
    text = "该结果显著优于对照组, 表明反应路径存在差异."
    audit = audit_text(text, language="zh")
    assert audit["has_blocking"] is True
    relevant = [
        v for v in audit["violations"]
        if v["rule_id"] == "zh.fullwidth_punctuation"
    ]
    assert relevant


def test_ja_fullwidth_punctuation_blocks() -> None:
    """Japanese with half-width punctuation between CJK chars must block."""
    text = "結果は対照群より有意に高く, 効果が確認された."
    audit = audit_text(text, language="ja")
    assert audit["has_blocking"] is True
    relevant = [
        v for v in audit["violations"]
        if v["rule_id"] == "ja.fullwidth_punctuation"
    ]
    assert relevant


# ---------------------------------------------------------------------------
# Orchestrator helpers
# ---------------------------------------------------------------------------


def test_unknown_language_returns_empty_audit() -> None:
    """An unsupported language code (e.g. 'pl') yields zero violations
    instead of raising. The pipeline treats this as 'skip the audit'.
    """
    assert has_rules_for("pl") is False
    audit = audit_text("Dowolny tekst.", language="pl")
    assert audit["violation_count"] == 0
    assert audit["has_blocking"] is False
    assert audit["language"] == "pl"


def test_system_prompt_fragment_lists_rules() -> None:
    """The Russian prompt fragment must mention guillemets, decimal
    comma, and the anglicism guard — the three most-impactful rules.
    The fragment is the model-facing brief; if it's missing a critical
    rule, the model can't comply.
    """
    fragment = build_system_prompt_fragment("ru")
    assert "Russian" in fragment
    assert "«" in fragment, "guillemet rule must appear in the prompt"
    assert "0,5" in fragment, "decimal comma rule must show the canonical example"
    assert "пайплайн" in fragment, "anglicism guard must surface a sample anglicism"


def test_system_prompt_fragment_empty_for_unknown_language() -> None:
    """No prompt fragment for unsupported languages — the caller
    should treat empty as 'no locale-specific guidance'.
    """
    assert build_system_prompt_fragment("xx") == ""


def test_format_violations_for_redispatch_includes_rule_and_observed() -> None:
    """The re-dispatch feedback must include the rule_id, severity,
    description, and the observed bad substring — that's the model's
    full context for the rewrite.
    """
    text = 'Концентрация 0.45 мМ "значительная".'
    audit = audit_text(text, language="ru")
    violations_dicts = audit["violations"]
    # Re-hydrate to Violation objects for the formatter
    violations = [Violation(**v) for v in violations_dicts]
    feedback = format_violations_for_redispatch(violations)
    assert "ru.decimal_comma" in feedback
    assert "0.45" in feedback
    assert "Rewrite" in feedback

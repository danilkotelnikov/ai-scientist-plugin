"""English (en) — Strunk & White + Chicago Manual scientific register.

References
----------
- Strunk & White, "The Elements of Style" (4th ed.) — concision rules.
- Chicago Manual of Style 17e §6.18, §9.2 — numerals, abbreviations.
- ACS Style Guide, IEEE Editorial Style Manual — citation conventions
  most major scientific publishers converge on.

The rules below catch the LLM register slips most common in English
manuscripts: smart-quote inconsistency, double spaces after periods,
oxford-comma drift, hedge-density ("might potentially be considered to
suggest"), and the four-word LLM-isms that mark generated prose
("Furthermore, it is important to note that…").
"""
from __future__ import annotations

from ..linguistic_rules import (
    Rule,
    regex_validator,
    word_list_validator,
)


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

_RULE_DOUBLE_SPACE = Rule(
    id="en.double_space",
    severity="warn",
    category="typography",
    description=(
        "Use a single space after a period, not two. Modern typesetting "
        "handles the wider full-stop space automatically; the old "
        "typewriter convention of two spaces is no longer expected."
    ),
    prompt_directive="One space after a period.",
    validator=regex_validator(r"\.\s\s+"),
    example_bad="The result was significant.  The effect persisted.",
    example_good="The result was significant. The effect persisted.",
)

_RULE_STRAIGHT_QUOTES = Rule(
    id="en.smart_quotes",
    severity="warn",
    category="typography",
    description=(
        "Use curly quotes “thus” and ‘thus’ — not "
        "straight ASCII \" or '. LaTeX converts `` and '' to curly quotes "
        "automatically, so that pair is fine; ASCII quotes are not."
    ),
    prompt_directive=(
        "Use curly “…” for outer quotes (or LaTeX `` ’’). Avoid ASCII \"…\"."
    ),
    validator=regex_validator(r'"[^"]*"'),
    example_bad='The authors describe the effect as "anomalous".',
    example_good="The authors describe the effect as “anomalous”.",
)

_RULE_THOUSANDS_COMMA = Rule(
    id="en.thousands_separator",
    severity="info",
    category="typography",
    description=(
        "Group digits with a comma in English: 1,234,567 — not a space "
        "or a period. This is the inverse of the Russian convention; "
        "switching locales requires rewriting numerals."
    ),
    prompt_directive="In English, use commas as thousands separators: 1,234.",
    # Catch space-separated thousands which signal a Russian → English
    # locale-drift bug: '1 234 patients' should become '1,234 patients'.
    validator=regex_validator(r"\b\d{1,3}(?: \d{3})+\b"),
    example_bad="The cohort included 1 234 patients.",
    example_good="The cohort included 1,234 patients.",
)


# ---------------------------------------------------------------------------
# Citation style
# ---------------------------------------------------------------------------

_RULE_CITATION_FORMAT = Rule(
    id="en.citation_format",
    severity="info",
    category="citation_style",
    description=(
        "Cite with the venue's required style. Default to numbered "
        "[1] for ACS / IEEE / Nature; author-year (Smith, 2024) for "
        "APA / Chicago. Don't mix styles in the same manuscript."
    ),
    prompt_directive="Pick one citation style per manuscript and stay with it.",
    # No automatic validator — citation-style consistency is enforced
    # by the citator agent, not by this lint pass. Listed here so the
    # rule appears in the prompt fragment.
    validator=lambda _text: [],
)


# ---------------------------------------------------------------------------
# Register / lexical — anti-LLMish
# ---------------------------------------------------------------------------

_LLM_OPENERS_EN = [
    "Furthermore, it is important to note",
    "Moreover, it is worth mentioning",
    "It is important to note that",
    "It is worth noting that",
    "It should be noted that",
    "It is important to highlight",
    "In conclusion, this study",
    "In summary, this work",
]

_RULE_LLM_OPENERS_EN = Rule(
    id="en.llm_openers",
    severity="block",
    category="register",
    description=(
        "Avoid LLM-style openers: 'Furthermore, it is important to "
        "note', 'It is worth noting that', 'In conclusion, this study'. "
        "Open paragraphs with the substantive claim, not the meta-comment."
    ),
    prompt_directive=(
        "Don't open paragraphs with 'Furthermore, it is important to note', "
        "'It is worth noting that', 'In conclusion this study'. Open with "
        "the claim itself."
    ),
    validator=word_list_validator(_LLM_OPENERS_EN, case_sensitive=False),
    example_bad="It is important to note that the catalyst exhibits activity.",
    example_good="The catalyst exhibits activity in the 0.1–1 mM range.",
)

_LLM_HEDGE_WORDS = [
    "potentially",
    "arguably",
    "ostensibly",
    "purportedly",
    "delve into",
    "tapestry",
    "navigate the complexities",
    "in the realm of",
    "robust framework",
    "comprehensive analysis",
    "novel approach",
    "cutting-edge",
    "state-of-the-art",  # only as filler; OK when actually substantiated
]

_RULE_LLM_HEDGES = Rule(
    id="en.llm_hedges",
    severity="warn",
    category="register",
    description=(
        "Don't stack hedge words and LLM register cues: 'potentially', "
        "'arguably', 'delve into', 'tapestry of', 'navigate the "
        "complexities', 'cutting-edge', 'state-of-the-art', 'robust "
        "framework'. They signal generated prose."
    ),
    prompt_directive=(
        "Skip 'potentially', 'arguably', 'delve into', 'tapestry', "
        "'navigate the complexities', 'cutting-edge', 'robust framework' "
        "unless you mean them literally and can substantiate."
    ),
    validator=word_list_validator(_LLM_HEDGE_WORDS, case_sensitive=False),
    example_bad="This robust framework delves into the tapestry of mechanisms.",
    example_good="The model resolves the mechanism into three steps.",
)

_RULE_FIRST_PERSON_PLURAL_OVERUSE = Rule(
    id="en.first_person_overuse",
    severity="info",
    category="register",
    description=(
        "Heavy use of 'we' is fine in modern scientific English but "
        "becomes monotone if every sentence starts with it. Vary the "
        "subject: passive ('The mechanism was inferred'), an "
        "experimental setup ('Two replicates yielded …'), or a result "
        "('Activity dropped 12% after …')."
    ),
    prompt_directive=(
        "Vary the subject. Don't open every sentence with 'We'."
    ),
    # Heuristic: only an advisory rule. Detection is best done by the
    # reviewer agent over a whole section, not by per-paragraph regex.
    validator=lambda _text: [],
)


# ---------------------------------------------------------------------------
# Methods-section tense
# ---------------------------------------------------------------------------

_RULE_METHODS_TENSE = Rule(
    id="en.methods_past_tense",
    severity="info",
    category="register",
    description=(
        "Methods and Results sections use the past tense ('was "
        "measured', 'showed', 'observed'). Present tense is reserved "
        "for established knowledge in the introduction and for "
        "interpretation in the discussion."
    ),
    prompt_directive=(
        "Methods and Results in past tense; Introduction and Discussion "
        "in present tense for established facts."
    ),
    validator=lambda _text: [],
)


RULES: list[Rule] = [
    _RULE_DOUBLE_SPACE,
    _RULE_STRAIGHT_QUOTES,
    _RULE_THOUSANDS_COMMA,
    _RULE_CITATION_FORMAT,
    _RULE_LLM_OPENERS_EN,
    _RULE_LLM_HEDGES,
    _RULE_FIRST_PERSON_PLURAL_OVERUSE,
    _RULE_METHODS_TENSE,
]

LLM_OPENERS = _LLM_OPENERS_EN
LLM_HEDGES = _LLM_HEDGE_WORDS

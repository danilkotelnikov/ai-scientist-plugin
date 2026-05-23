"""German (de) — Duden + DIN 5008 typesetting rules.

References
----------
- Duden, "Die deutsche Rechtschreibung" (28th ed.) — orthography.
- DIN 5008 — German business/scientific text typesetting standard.

The German rules focus on the comma decimal separator, the eszett ß
(only in modern Swiss-German is "ss" acceptable), the typographic
quotation marks „…", and capitalization of all nouns (a defining
feature of written German).
"""
from __future__ import annotations

from ..linguistic_rules import Rule, regex_validator


_RULE_DECIMAL_COMMA_DE = Rule(
    id="de.decimal_comma",
    severity="block",
    category="typography",
    description="Use a comma as the decimal separator in German: 0,5 — not 0.5.",
    prompt_directive="Decimal numbers in German use the comma: 0,5.",
    validator=regex_validator(r"\d+\.\d+"),
    example_bad="Die Konzentration betrug 0.45 mM.",
    example_good="Die Konzentration betrug 0,45 mM.",
)

_RULE_GERMAN_QUOTES = Rule(
    id="de.german_quotes",
    severity="warn",
    category="typography",
    description=(
        "German quotation marks open low and close high: „…\". "
        "ASCII quotes \"…\" are non-standard."
    ),
    prompt_directive="Use „…\" for German quotes (or « … » in Swiss-German).",
    validator=regex_validator(r'"[^"]*"'),
    example_bad='Der Autor nennt den Effekt "anomal".',
    example_good="Der Autor nennt den Effekt „anomal\".",
)

_RULE_THOUSANDS_DE = Rule(
    id="de.thousands_separator",
    severity="warn",
    category="typography",
    description=(
        "German groups thousands with a thin space or a period: "
        "1.234.567 or 1 234 567 — not a comma (which is the decimal mark)."
    ),
    prompt_directive=(
        "Group thousands with a thin space or a period in German numerals."
    ),
    # Comma-grouped 4+ digit numbers — the LLM English-style bug.
    validator=regex_validator(r"\b\d{1,3}(?:,\d{3})+\b"),
    example_bad="Die Kohorte umfasste 1,234 Patienten.",
    example_good="Die Kohorte umfasste 1234 Patienten.",
)


RULES: list[Rule] = [
    _RULE_DECIMAL_COMMA_DE,
    _RULE_GERMAN_QUOTES,
    _RULE_THOUSANDS_DE,
]

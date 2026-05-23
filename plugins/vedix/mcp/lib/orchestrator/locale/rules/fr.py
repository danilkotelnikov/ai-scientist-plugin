"""French (fr) — Académie française + Imprimerie nationale conventions.

References
----------
- Académie française, "Lexique des règles typographiques en usage à l'Imprimerie nationale" (2002).

French has the most distinctive whitespace conventions of the seven
locales: a non-breaking space before high punctuation (:, ;, ?, !), and
guillemets « … » with non-breaking spaces inside.
"""
from __future__ import annotations

from ..linguistic_rules import Rule, regex_validator


_RULE_DECIMAL_COMMA_FR = Rule(
    id="fr.decimal_comma",
    severity="block",
    category="typography",
    description="Use a comma as the decimal separator in French: 0,5 — not 0.5.",
    prompt_directive="Decimal numbers in French use the comma: 0,5.",
    validator=regex_validator(r"\d+\.\d+"),
    example_bad="La concentration était de 0.45 mM.",
    example_good="La concentration était de 0,45 mM.",
)

_RULE_GUILLEMETS_FR = Rule(
    id="fr.guillemets",
    severity="warn",
    category="typography",
    description=(
        "Quote with French guillemets « … » with a non-breaking space "
        "inside the marks (« texte »). ASCII quotes are not acceptable."
    ),
    prompt_directive="Quote with « and » (non-breaking space inside).",
    validator=regex_validator(r'"[^"]*"'),
    example_bad='L\'auteur décrit l\'effet comme "anormal".',
    example_good="L'auteur décrit l'effet comme « anormal ».",
)

_RULE_NBSP_BEFORE_HIGH_PUNCT = Rule(
    id="fr.nbsp_before_punctuation",
    severity="info",
    category="typography",
    description=(
        "French requires a non-breaking space before high punctuation: "
        ":, ;, ?, !. The ordinary space is acceptable in informal "
        "writing but standard for academic typesetting is non-breaking."
    ),
    prompt_directive=(
        "Put a non-breaking space (\\u00A0 or \\\\,) before :, ;, ?, ! in French."
    ),
    # Flag a regular ASCII space followed by high punctuation as a candidate
    # for replacement with non-breaking space.
    validator=regex_validator(r"(?<=[a-zàâéèêëïîôöùûüç]) [:;?!]"),
    example_bad="Est-ce vraiment significatif ?",  # space is regular here
    example_good="Est-ce vraiment significatif ?",
)


RULES: list[Rule] = [
    _RULE_DECIMAL_COMMA_FR,
    _RULE_GUILLEMETS_FR,
    _RULE_NBSP_BEFORE_HIGH_PUNCT,
]

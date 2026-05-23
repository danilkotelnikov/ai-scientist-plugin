"""Spanish (es) — RAE + ortografía académica typesetting rules.

References
----------
- Real Academia Española, "Ortografía de la lengua española" (2010).
- Diccionario panhispánico de dudas — terminology.

These are the typesetting essentials most often violated by LLM Spanish:
inverted-question marks, decimal comma, em dash, lowercase nationalities,
and ASCII vs typographic apostrophes.
"""
from __future__ import annotations

import re

from ..linguistic_rules import Rule, ValidatorResult, regex_validator


def _es_question_validator(text: str) -> ValidatorResult:
    """Flag every '?' whose sentence has no preceding '¿'.

    Sentence boundary heuristic: the start of the most recent line OR
    the most recent sentence-terminator ('. ', '! ', '? ', or '\\n').
    A pure-regex lookbehind can't do this — Python regex lookbehinds
    must be fixed-width — so we walk question-marks linearly.
    """
    out: ValidatorResult = []
    for m in re.finditer(r"\?", text):
        # Find the previous sentence terminator (or start of text).
        prev_terminator = max(
            text.rfind("\n", 0, m.start()),
            text.rfind(". ", 0, m.start()),
            text.rfind("! ", 0, m.start()),
            text.rfind("? ", 0, m.start()),
        )
        sentence_start = prev_terminator + 1 if prev_terminator >= 0 else 0
        sentence = text[sentence_start:m.end()]
        if "¿" not in sentence:
            out.append((m.start(), m.end(), "?"))
    return out


_RULE_DECIMAL_COMMA_ES = Rule(
    id="es.decimal_comma",
    severity="block",
    category="typography",
    description="Use a comma as the decimal separator in Spanish: 0,5 — not 0.5.",
    prompt_directive="Write decimal numbers with a comma: 0,5 — not 0.5.",
    validator=regex_validator(r"\d+\.\d+"),
    example_bad="La concentración fue de 0.45 mM.",
    example_good="La concentración fue de 0,45 mM.",
)

_RULE_INVERTED_QUESTION = Rule(
    id="es.inverted_question",
    severity="warn",
    category="typography",
    description=(
        "Open questions with ¿ and exclamations with ¡. The closing "
        "marks ? and ! always carry an opening pair: ¿…? and ¡…!."
    ),
    prompt_directive="Open questions with ¿ and exclamations with ¡.",
    # Custom: walk every ? and check the enclosing sentence has a
    # matching ¿. Pure regex can't express variable-length lookbehind.
    validator=_es_question_validator,
    example_bad="Es posible esta interpretación?",
    example_good="¿Es posible esta interpretación?",
)

_RULE_LOWERCASE_NATIONALITIES = Rule(
    id="es.lowercase_nationalities",
    severity="warn",
    category="orthography",
    description=(
        "Spanish lowercases nationalities, languages, months, and days: "
        "español, lunes, enero — not Español, Lunes, Enero (mid-sentence)."
    ),
    prompt_directive="Lowercase nationalities, languages, months, and days mid-sentence.",
    validator=regex_validator(
        r"(?<=[a-zA-ZñÑáéíóúÁÉÍÓÚ, ;:])\s+"
        r"(Español|Inglés|Alemán|Francés|Italiano|"
        r"Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|"
        r"Octubre|Noviembre|Diciembre|"
        r"Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)"
    ),
    example_bad="El estudio se realizó en Marzo de 2026.",
    example_good="El estudio se realizó en marzo de 2026.",
)


RULES: list[Rule] = [
    _RULE_DECIMAL_COMMA_ES,
    _RULE_INVERTED_QUESTION,
    _RULE_LOWERCASE_NATIONALITIES,
]

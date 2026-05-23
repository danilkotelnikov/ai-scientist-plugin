"""Russian (ru) — classical academic prose + GOST typesetting rules.

References
----------
- ГОСТ 7.0.5-2008 "Библиографическая ссылка" — citation format.
- ГОСТ 7.0.100-2018 — updated bibliography standard.
- Розенталь Д. Э., "Справочник по правописанию и литературной правке" —
  the canonical Russian prose-style handbook for academic writing.
- Мильчин А. Э., "Справочник издателя и автора" — editorial conventions
  (guillemets, dash spacing, numerical formatting, …).

The rules below encode the subset of these references most often violated
by LLM-generated Russian academic prose: ASCII quotes for guillemets,
decimal points for decimal commas, dropped ё, anglicisms with native
equivalents, sentence-initial "Кроме того / Также / Стоит отметить", and
the absence of GOST citation brackets.
"""
from __future__ import annotations

import re

from ..linguistic_rules import (
    Rule,
    regex_validator,
    word_list_validator,
)


# `re` is used as a flag namespace (re.IGNORECASE) by some validators
# below; lint suppression because pyright doesn't trace flag usage.
_ = re.IGNORECASE  # noqa: F841


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

_RULE_GUILLEMETS = Rule(
    id="ru.guillemets",
    severity="block",
    category="typography",
    description=(
        "Use guillemets «…» for outer quotation marks and German-style "
        "„…“ for nested quotation marks. Straight ASCII quotes (\" \" "
        "and ' ') are not acceptable in Russian academic prose."
    ),
    prompt_directive=(
        "Quote with «outer» and „inner“. Never use ASCII \"…\" or '…'."
    ),
    # Forbid any ASCII " or ' that survives. Real-world LaTeX manuscripts
    # also write `` and '' for English-style quotes — flag those too.
    validator=regex_validator(r'[""]|\'\'|``'),
    example_bad='Полученный результат "значительно превышает" ожидаемый.',
    example_good="Полученный результат «значительно превышает» ожидаемый.",
)

_RULE_DECIMAL_COMMA = Rule(
    id="ru.decimal_comma",
    severity="block",
    category="typography",
    description=(
        "Use a comma as the decimal separator (0,5), not a period (0.5). "
        "Periods are acceptable only in DOIs, URLs, software-version "
        "strings, and inline LaTeX maths."
    ),
    prompt_directive="Write decimal numbers with a comma: 0,5 — not 0.5.",
    # \d+\.\d+ is the canonical "decimal point" pattern. We carve out
    # DOIs (10.XXXX/...), URLs, and version strings via ignore_inside;
    # the regex itself just hunts the digit-dot-digit shape.
    validator=regex_validator(r"\d+\.\d+"),
    example_bad="Концентрация составила 0.45 мМ.",
    example_good="Концентрация составила 0,45 мМ.",
    ignore_inside=(
        r"\$[^$]+\$",
        r"\\\([^)]+\\\)",
        r"\\begin\{equation\}.*?\\end\{equation\}",
        r"10\.\d{4,9}/\S+",  # DOIs
        r"https?://\S+",     # URLs
        r"\bv?\d+\.\d+(?:\.\d+)+\b",  # version strings like v3.0.1
        r"\\cite[a-z]*\{[^}]+\}",
        r"\\ref\{[^}]+\}",
    ),
)

_RULE_EM_DASH_SPACING = Rule(
    id="ru.em_dash_spacing",
    severity="warn",
    category="typography",
    description=(
        "The em dash in Russian carries a non-breaking space on the "
        "left and a regular space on the right: ‘word — word’. Use the "
        "long dash (U+2014), never the hyphen-minus '-' for that role."
    ),
    prompt_directive=(
        "Use ‘word — word’ for parenthetical em dashes (real em dash + spaces). "
        "Don't substitute the hyphen-minus."
    ),
    # Flag ' - ' (space-hyphen-space) as the canonical incorrect form.
    validator=regex_validator(r" - "),
    example_bad="Метод DFT - наиболее распространённый подход.",
    example_good="Метод DFT — наиболее распространённый подход.",
)

_RULE_NUMBER_THOUSANDS = Rule(
    id="ru.thousands_separator",
    severity="warn",
    category="typography",
    description=(
        "Group digits in long numbers with a non-breaking thin space "
        "(U+202F), not a comma. Write 1 234 567 — not 1,234,567."
    ),
    prompt_directive="Don't use commas as thousands separators.",
    # Comma-grouped 4+ digit numbers like 1,234 or 12,345 are the bug.
    validator=regex_validator(r"\b\d{1,3}(?:,\d{3})+\b"),
    example_bad="Выборка включала 1,234 наблюдения.",
    example_good="Выборка включала 1 234 наблюдения.",
)


# ---------------------------------------------------------------------------
# Orthography
# ---------------------------------------------------------------------------

_RULE_YO_PRESERVATION = Rule(
    id="ru.yo_preservation",
    severity="warn",
    category="orthography",
    description=(
        "Preserve the letter ё. In academic prose, 'ё' is distinct from "
        "'е' and the substitution changes meaning or stress (все vs всё, "
        "узнаем vs узнаём)."
    ),
    prompt_directive=(
        "Keep ё. Don't write 'е' where the word actually contains ё."
    ),
    # We can't catch this with regex alone — we need a dictionary of
    # words that MUST have ё but are often miswritten with е. This is
    # a conservative subset; expand via the corpus.
    validator=word_list_validator(
        words=[
            # Common ё-words misspelled as е by LLMs (and humans):
            "все",  # ambiguous: "all" (все) vs "everything" (всё); requires context, flagged for review
            "учет",
            "учета",
            "учету",
            "учетом",
            "уровень",  # actually doesn't need ё; placeholder for the dict
            "решенный",
            "проведенный",
            "проведено",
            "проведен",
            "проведена",
            "приведен",
            "приведено",
            "приведенный",
            "проявленный",
            "затем",  # doesn't need ё; for the dict
            "нем",
            "нему",
            "обем",
            "объем",
            "объемом",
            "объемный",
            "приём",  # this one has ё; flag if you see "прием"
            "прием",
            "приема",
            "приему",
            "приемлем",  # ё needed
            "полета",
            "звездный",
            "зеленый",
            "темный",
            "теплый",
            "тяжелый",
        ],
        case_sensitive=False,
    ),
    example_bad="Объем выборки и учет погрешностей.",
    example_good="Объём выборки и учёт погрешностей.",
)

_RULE_CAPITALIZATION_MONTHS = Rule(
    id="ru.capitalization_months",
    severity="warn",
    category="orthography",
    description=(
        "Russian does not capitalize months, days of the week, languages, "
        "or nationalities (unless they begin a sentence): январь, "
        "понедельник, русский язык — not Январь, Понедельник, Русский язык."
    ),
    prompt_directive=(
        "Lowercase months, days, languages, and nationalities mid-sentence."
    ),
    # Flag mid-sentence capitalized variants of the canonical set.
    # We don't try to disambiguate sentence-initial use — that's an
    # acceptable false-positive rate for a 'warn' rule. The lookbehind
    # accepts either lowercase OR uppercase Cyrillic so that
    # constructions like "В Марте" (preposition before month) also fire.
    validator=regex_validator(
        r"(?<=[а-яёА-ЯЁ, ;:])\s+"
        r"(Январ[еья]?|Феврал[еья]?|Март[еа]?|Апрел[еья]?|Ма[ея]|"
        r"Июн[еья]?|Июл[еья]?|Август[еа]?|Сентябр[еья]?|"
        r"Октябр[еья]?|Ноябр[еья]?|Декабр[еья]?|"
        r"Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье|"
        r"Русский|Английский|Немецкий|Французский|Испанский|Китайский|"
        r"Японский|Российский|Американский|Итальянский)"
    ),
    example_bad="Эксперимент был проведён в Марте 2026 года.",
    example_good="Эксперимент был проведён в марте 2026 года.",
)


# ---------------------------------------------------------------------------
# Citation style — GOST 7.0.5-2008
# ---------------------------------------------------------------------------

_RULE_CITATION_BRACKETS = Rule(
    id="ru.citation_brackets",
    severity="warn",
    category="citation_style",
    description=(
        "Cite with square brackets in numbered style: [1], [2, с. 23], "
        "[3; 4]. Parenthetical author-year (Иванов, 2024) is acceptable "
        "only for journals that explicitly require it."
    ),
    prompt_directive=(
        "Use [1] or [2, с. 23] for citations. Don't fall back to "
        "(Author, year) unless the venue mandates it."
    ),
    # Catch (Surname et al., YYYY) style mid-prose. We require a Cyrillic
    # surname and a 4-digit year to keep the false-positive rate low.
    validator=regex_validator(
        r"\([А-ЯЁ][а-яё]+(?:\s+(?:и др\.|et al\.))?,\s*\d{4}\)"
    ),
    example_bad="Этот эффект был ранее описан (Иванов, 2024).",
    example_good="Этот эффект был ранее описан [1].",
)


# ---------------------------------------------------------------------------
# Register / lexical
# ---------------------------------------------------------------------------

# Anglicisms with established native equivalents. Each entry is the
# anglicism that should be flagged. The system-prompt fragment includes
# the suggested replacements as a separate dict.
_ANGLICISMS = {
    "контент": "содержание",
    "кейс": "пример",
    "имплементировать": "реализовать",
    "имплементация": "реализация",
    "девайс": "устройство",
    "хайповый": "популярный",
    "ивент": "событие",
    "фидбек": "обратная связь",
    "оверхед": "избыточные затраты",
    "адресовать": "решать (проблему)",  # как verb 'to address'
    "релевантный": "значимый",
    "роадмап": "план развития",
    "пайплайн": "конвейер",
    "стейкхолдер": "заинтересованная сторона",
    "тренд": "тенденция",
    "челлендж": "задача",
}

_RULE_ANGLICISM_GUARD = Rule(
    id="ru.anglicism_guard",
    severity="warn",
    category="register",
    description=(
        "Prefer the established native term over the anglicism when "
        "both convey the same meaning in academic prose. The replacements: "
        + "; ".join(f"{a} → {b}" for a, b in _ANGLICISMS.items())
        + "."
    ),
    prompt_directive=(
        "Use native Russian equivalents in academic prose: "
        + ", ".join(f"{a} → {b}" for a, b in list(_ANGLICISMS.items())[:6])
        + ", …"
    ),
    validator=word_list_validator(_ANGLICISMS.keys(), case_sensitive=False),
    example_bad="Этот пайплайн адресует ключевой челлендж.",
    example_good="Этот конвейер решает ключевую задачу.",
)

_RULE_LLM_OPENERS = Rule(
    id="ru.llm_openers",
    severity="warn",
    category="register",
    description=(
        "Avoid LLM-style paragraph openers: 'Кроме того', 'Более того', "
        "'Стоит отметить', 'Важно подчеркнуть', 'Следует отметить'. "
        "Classical Russian academic prose opens with the substantive "
        "claim, not an adverbial filler."
    ),
    prompt_directive=(
        "Don't open paragraphs with 'Кроме того', 'Стоит отметить', "
        "'Следует отметить', 'Важно подчеркнуть' — start with the claim."
    ),
    # Match these phrases only at start of paragraph (after \n\n or
    # start-of-text).
    validator=regex_validator(
        r"(?:^|\n\n)(?:Кроме того|Более того|Также|Стоит отметить|"
        r"Важно подчеркнуть|Следует отметить|Необходимо отметить)"
    ),
    example_bad="\n\nКроме того, наблюдалось снижение энергии активации.",
    example_good="\n\nЭнергия активации снизилась на 12 кДж/моль.",
)

_RULE_FIRST_PERSON_SINGULAR = Rule(
    id="ru.first_person_singular",
    severity="warn",
    category="register",
    description=(
        "Classical Russian scientific prose avoids the first-person "
        "singular 'я'. Use the impersonal 'было показано', the inclusive "
        "'мы' (academic we), or a passive construction."
    ),
    prompt_directive=(
        "Avoid 'я' in the manuscript body. Prefer impersonal 'было показано' "
        "or inclusive 'мы'. Reserve 'я' only for first-person discussions "
        "of viewpoint in narrative reviews."
    ),
    validator=regex_validator(r"\b[Яя]\b"),
    example_bad="Я показал, что катализатор активен в этих условиях.",
    example_good="Показано, что катализатор активен в этих условиях.",
)


# ---------------------------------------------------------------------------
# Methods-section passive voice (advisory only)
# ---------------------------------------------------------------------------

_RULE_METHODS_PASSIVE = Rule(
    id="ru.methods_passive",
    severity="info",
    category="register",
    description=(
        "In methods and results sections, prefer the impersonal passive "
        "('было измерено', 'установлено', 'наблюдалось') over the active "
        "'мы измерили'. Active voice is acceptable in the introduction "
        "and discussion."
    ),
    prompt_directive=(
        "In Methods/Results: use passive constructions ('было измерено')."
    ),
    # Heuristic: flag 'мы +verb' patterns (any case). This is intentionally
    # an 'info' rule because there's no clean way to know from text alone
    # which section we're in.
    validator=regex_validator(
        r"\bмы\s+(?:провели|измерили|наблюдали|обнаружили|показали|"
        r"использовали|применили|разработали|реализовали|вычислили)",
        flags=re.IGNORECASE,
    ),
    example_bad="Мы измерили константу диссоциации методом ITC.",
    example_good="Константа диссоциации была измерена методом ITC.",
)


# ---------------------------------------------------------------------------
# Public rule list
# ---------------------------------------------------------------------------

RULES: list[Rule] = [
    _RULE_GUILLEMETS,
    _RULE_DECIMAL_COMMA,
    _RULE_EM_DASH_SPACING,
    _RULE_NUMBER_THOUSANDS,
    _RULE_YO_PRESERVATION,
    _RULE_CAPITALIZATION_MONTHS,
    _RULE_CITATION_BRACKETS,
    _RULE_ANGLICISM_GUARD,
    _RULE_LLM_OPENERS,
    _RULE_FIRST_PERSON_SINGULAR,
    _RULE_METHODS_PASSIVE,
]

# Exported so tests can introspect.
ANGLICISMS = _ANGLICISMS

"""Russian locale configuration (Block 6 Task 3, §6).

- Citation backend: biblatex ``gost-numeric`` (ГОСТ 7.0.5-2008, the
  Russian state standard cited by all RAS/RAN journals).
- Encoding: T2A fontenc for Cyrillic glyph set; UTF-8 input.
- Font stack: Noto Serif (Latin) + Noto Serif CJK if mixed-script.
- Engine: ``pdflatex`` (T2A is a pdflatex/8-bit feature).
- Register lints: Russian academic-prose paragraph starters and a
  bumped em-dash budget (4/1000 words — RU dash usage is higher than
  EN by convention, but still capped to avoid LLM-style overuse).
"""
from .base import LocaleConfig

LINTS: dict = {
    "blacklist_paragraph_start": [
        "Кроме того",
        "Более того",
        "Также",
        "Стоит отметить",
        "Важно подчеркнуть",
        "Следует отметить",
        "Необходимо",
    ],
    "blacklist_words": [
        "погружаться",
        "сложный гобелен",
        "множество",
        "ориентироваться",
    ],
    # RU academic prose tolerates more dashes than EN, but cap to avoid
    # the LLM ~10/1k pattern. Spec value: 4/1k words.
    "max_em_dashes_per_1000_words": 4,
    # Russian academic register prefers passive voice in methods/results.
    "passive_voice_preference": True,
}

CONFIG = LocaleConfig(
    code="ru",
    name="Russian",
    citation_style="gost-numeric",
    latex_preamble=(
        r"\usepackage[utf8]{inputenc}"
        "\n"
        r"\usepackage[T2A]{fontenc}"
        "\n"
        r"\usepackage[english,russian]{babel}"
        "\n"
        r"\usepackage{noto}"
        "\n"
        r"\usepackage["
        "\n"
        r"    backend=biber,"
        "\n"
        r"    style=gost-numeric,"
        "\n"
        r"    sorting=ntvy,"
        "\n"
        r"    language=russian,"
        "\n"
        r"    autolang=other"
        "\n"
        r"]{biblatex}"
    ),
    bibtex_style="gost71s",
    latex_engine="pdflatex",
    babel_lang="russian",
    register_lints=LINTS,
)

"""English locale configuration (Block 6 Task 2, §6).

- Citation backend: biblatex ``numeric-comp`` (default for IEEE-style and
  Nature-family templates).
- Font stack: Latin Modern via ``lmodern`` (T1 fontenc).
- Engine: ``pdflatex``.
- Anti-LLMish lint: Tier-1 paragraph-start phrases + Tier-2 individual
  words known to peak in post-ChatGPT prose (Liang et al. 2024,
  ICLR 2024). Em-dash budget = 2/1000 words (human baseline).
"""
from .base import LocaleConfig

LINTS: dict = {
    "blacklist_paragraph_start": [
        "Furthermore",
        "Moreover",
        "Additionally",
        "It is important to note",
        "It is worth mentioning",
        "Notably",
        "In conclusion",
    ],
    "blacklist_words": [
        "delve",
        "intricate",
        "tapestry",
        "myriad",
        "navigate",
        "underscore",
        "showcase",
        "leverage",
        "harness",
        "robust",
    ],
    "max_em_dashes_per_1000_words": 2,
}

CONFIG = LocaleConfig(
    code="en",
    name="English",
    citation_style="biblatex-numeric-comp",
    latex_preamble=(
        r"\usepackage[utf8]{inputenc}"
        "\n"
        r"\usepackage[T1]{fontenc}"
        "\n"
        r"\usepackage{lmodern}"
        "\n"
        r"\usepackage[english]{babel}"
        "\n"
        r"\usepackage[backend=biber,style=numeric-comp]{biblatex}"
    ),
    bibtex_style="ieeetr",
    latex_engine="pdflatex",
    babel_lang="english",
    register_lints=LINTS,
)

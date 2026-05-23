"""Chinese (zh) — GB/T 15834-2011 punctuation + GB 3102 numerical typesetting.

References
----------
- GB/T 15834-2011 (中华人民共和国国家标准《标点符号用法》).
- GB 3102 — numerals and units in scientific Chinese.

Chinese academic prose uses full-width punctuation (，。！？；：) and
distinctive quote marks (""''). Mixing in half-width Latin punctuation
is the most common LLM register slip.
"""
from __future__ import annotations

from ..linguistic_rules import Rule, regex_validator


_RULE_FULLWIDTH_PUNCT = Rule(
    id="zh.fullwidth_punctuation",
    severity="block",
    category="typography",
    description=(
        "Chinese uses full-width punctuation: 。 ， ； ： ！ ？ … 「」 「『』. "
        "Half-width Latin punctuation (. , ; : ! ? \" ' ()) is incorrect "
        "in pure-Chinese prose."
    ),
    prompt_directive="Use full-width punctuation (。，；：！？「」) in Chinese.",
    # Flag half-width comma, period, semicolon between Chinese characters.
    validator=regex_validator(r"[一-鿿][,.;!?]"),
    example_bad="该结果显著优于对照组, 表明反应路径差异。",
    example_good="该结果显著优于对照组，表明反应路径差异。",
)

_RULE_DECIMAL_POINT_ZH = Rule(
    id="zh.decimal_point",
    severity="info",
    category="typography",
    description=(
        "Chinese uses the period (.) as the decimal separator, "
        "matching English. The full-width period 。is reserved for "
        "end-of-sentence punctuation only."
    ),
    prompt_directive="Decimal numbers in Chinese use . (half-width period).",
    validator=regex_validator(r"\d+。\d+"),
    example_bad="浓度为0。45 mM。",
    example_good="浓度为0.45 mM。",
)


RULES: list[Rule] = [
    _RULE_FULLWIDTH_PUNCT,
    _RULE_DECIMAL_POINT_ZH,
]

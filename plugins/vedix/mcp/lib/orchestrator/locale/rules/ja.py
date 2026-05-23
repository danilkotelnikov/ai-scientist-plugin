"""Japanese (ja) — JIS X 4051 line composition + scientific style.

References
----------
- JIS X 4051:2004 — Japanese text composition.
- 文部科学省「公用文の書き表し方の基準」(MEXT public-document conventions).

Japanese academic prose uses full-width punctuation (。、) and
distinctive quote marks 「」 『』. Mixing in half-width Latin
punctuation between Japanese characters is the most common LLM slip,
followed by ASCII commas where 、(touten) is required.
"""
from __future__ import annotations

from ..linguistic_rules import Rule, regex_validator


_RULE_FULLWIDTH_PUNCT_JA = Rule(
    id="ja.fullwidth_punctuation",
    severity="block",
    category="typography",
    description=(
        "Japanese uses full-width punctuation: 。(kuten — period), "
        "、(touten — comma), 「」 (quotation), 『』(nested quotation). "
        "Half-width Latin punctuation between Japanese characters is "
        "non-standard."
    ),
    prompt_directive="Use 。 and 、(full-width) between Japanese characters.",
    # Half-width comma/period between Hiragana/Katakana/CJK ideographs.
    validator=regex_validator(
        r"[぀-ゟ゠-ヿ一-鿿][,.;]"
    ),
    example_bad="結果は対照群より有意に高く, 効果が確認された.",
    example_good="結果は対照群より有意に高く、効果が確認された。",
)

_RULE_QUOTE_MARKS_JA = Rule(
    id="ja.quotation_marks",
    severity="warn",
    category="typography",
    description=(
        "Quote with 「…」 in Japanese; nested quotes use 『…』. "
        "ASCII \"…\" is reserved for embedded English."
    ),
    prompt_directive="Quote with 「…」 in Japanese.",
    validator=regex_validator(r'"[^"]*"'),
    example_bad='著者はこれを "異常" と述べている。',
    example_good="著者はこれを「異常」と述べている。",
)


RULES: list[Rule] = [
    _RULE_FULLWIDTH_PUNCT_JA,
    _RULE_QUOTE_MARKS_JA,
]

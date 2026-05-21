"""article_type classifier — auto-detect review/experimental/benchmark.

Closes review-doc finding #8 (review-article mode is first-class).
"""
from __future__ import annotations
import re

REVIEW_KEYWORDS = [
    r"\breview\b", r"\bsurvey\b", r"\bstate[\s-]of[\s-]the[\s-]art\b",
    r"\brecent advances\b", r"\bliterature review\b",
    r"\bmeta[\s-]?analysis\b", r"\boverview of\b",
]
BENCHMARK_KEYWORDS = [
    r"\bbenchmark\b", r"\bleaderboard\b", r"\bevaluation suite\b",
    r"\bcompare\b.*\bvs\b", r"\bversus\b",
]


def classify_article_type(*, topic: str, explicit: str = "auto") -> str:
    """explicit ∈ {auto, review, experimental, benchmark}."""
    if explicit in ("review", "experimental", "benchmark"):
        return explicit
    t = (topic or "").lower()
    if any(re.search(p, t) for p in REVIEW_KEYWORDS):
        return "review"
    if any(re.search(p, t) for p in BENCHMARK_KEYWORDS):
        return "benchmark"
    return "experimental"


PHASE_ORDER = {
    "experimental": [
        "-1", "0", "0.5", "0.75", "1", "2", "3", "4", "5.5", "5",
        "6", "7", "8", "8.25", "8.5", "9", "10", "11",
    ],
    "review": [
        "-1", "0", "0.5", "1", "1.5", "2R", "5R", "6R", "7R",
        "8", "8.25", "8.5", "9", "10",
    ],
    "benchmark": [
        "-1", "0", "0.5", "0.75", "1", "2", "3", "4", "4B", "5.5",
        "5", "6", "7", "8", "8.25", "8.5", "9", "10", "11",
    ],
}

NON_APPLICABLE_PHASES = {
    "experimental": ["1.5", "2R", "5R", "6R", "7R", "4B"],
    "review": ["0.75", "3", "4", "4B", "5.5", "2", "5", "6", "7", "11"],
    "benchmark": ["1.5", "2R", "5R", "6R", "7R"],
}


def phase_order_for(article_type: str) -> list:
    return list(PHASE_ORDER[article_type])

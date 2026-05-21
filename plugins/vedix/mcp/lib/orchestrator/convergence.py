"""Semantic-signal convergence detection. Per spec §4.5.

Loops terminate on LLM signal, not fixed round count. Per Sakana
perform_writeup.py:693-707.
"""
from __future__ import annotations
import re
from typing import Optional

DEFAULT_SIGNALS = [
    "I am done",
    '"action": "FinalizeIdea"',
    "no further changes needed",
    "no further refinement",
    '"converged": true',
]


def _make_pattern(signal: str) -> re.Pattern:
    """Word-boundary regex for natural-language signals; substring for JSON-ish."""
    if signal.startswith('"') or signal.startswith("{"):
        return re.compile(re.escape(signal), re.IGNORECASE)
    # Natural language: require word boundaries to avoid false positives
    # like "not done yet"
    pattern = r"(?<![a-zA-Z])" + re.escape(signal) + r"(?![a-zA-Z])"
    return re.compile(pattern, re.IGNORECASE)


class SemanticConvergence:
    def __init__(self, signals: Optional[list] = None):
        self.signals = signals or list(DEFAULT_SIGNALS)
        self._patterns = [_make_pattern(s) for s in self.signals]

    def is_converged(self, llm_response: str) -> bool:
        """True if any signal phrase appears in the response, with negation guard."""
        if not llm_response:
            return False
        # Negation guard: "not done", "won't finalize", "I'm not done"
        negation_window = 30
        for pat in self._patterns:
            for m in pat.finditer(llm_response):
                start = max(0, m.start() - negation_window)
                preceding = llm_response[start:m.start()].lower()
                if any(neg in preceding for neg in [" not ", " no ", "n't ", "without "]):
                    continue
                return True
        return False

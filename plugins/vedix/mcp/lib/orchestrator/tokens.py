"""TokenTracker — per-phase + per-agent + USD cost. Singleton instance per
pipeline run. Per spec §4.2.

Pricing table is approximate (Apr 2026); user can override via settings.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Optional

# USD per 1M tokens (input, output). Approximate Apr 2026 pricing.
PRICING = {
    "opus":     {"input": 15.0, "output": 75.0},
    "sonnet":   {"input": 3.0,  "output": 15.0},
    "haiku":    {"input": 0.80, "output": 4.0},
    "gpt-5.5":      {"input": 10.0, "output": 50.0},
    "gpt-5.4":      {"input": 3.0,  "output": 15.0},
    "gpt-5.4-mini": {"input": 0.50, "output": 2.50},
    "gemini-3.1-pro-preview":  {"input": 5.0, "output": 20.0},
    "gemini-3-flash-preview":  {"input": 0.30, "output": 1.20},
}


class TokenTracker:
    def __init__(self, model: str = "opus", pricing: Optional[dict] = None):
        self.model = model
        self.pricing = pricing or PRICING
        self._by_phase: dict = defaultdict(lambda: {"prompt": 0, "completion": 0, "thinking": 0})
        self._by_agent: dict = defaultdict(lambda: {"prompt": 0, "completion": 0, "thinking": 0})
        self._totals = {"prompt": 0, "completion": 0, "thinking": 0}
        self._warned_at_pct = 0.0

    def reset(self):
        self.__init__(model=self.model, pricing=self.pricing)

    def add(self, *, phase: str, agent: str, prompt_tok: int, completion_tok: int, thinking_tok: int = 0):
        for d in (self._by_phase[phase], self._by_agent[agent], self._totals):
            d["prompt"] += prompt_tok
            d["completion"] += completion_tok
            d["thinking"] += thinking_tok

    def total_cost_usd(self) -> float:
        rates = self.pricing.get(self.model, {"input": 0, "output": 0})
        cost_in = self._totals["prompt"] / 1_000_000 * rates["input"]
        # Thinking tokens billed as output for Anthropic; as separate rate elsewhere.
        cost_out = (self._totals["completion"] + self._totals["thinking"]) / 1_000_000 * rates["output"]
        return cost_in + cost_out

    def warn_if_over_budget(self, *, budget_usd: float) -> bool:
        """Return True the FIRST time we cross 80%; False otherwise."""
        if budget_usd <= 0:
            return False
        spent = self.total_cost_usd()
        pct = spent / budget_usd
        if pct >= 0.80 and self._warned_at_pct < 0.80:
            self._warned_at_pct = pct
            return True
        return False

    def report(self) -> dict:
        return {
            "model": self.model,
            "totals": dict(self._totals),
            "by_phase": {k: dict(v) for k, v in self._by_phase.items()},
            "by_agent": {k: dict(v) for k, v in self._by_agent.items()},
            "total_cost_usd": round(self.total_cost_usd(), 4),
        }


# Singleton used by @track_tokens decorator
_GLOBAL_TRACKER = TokenTracker()

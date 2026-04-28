"""ResourceLedger — request/spawn/long-call accounting + budget enforcement.

Closes review-doc findings #5, #6, #23. Emits resource_usage.json.
"""
from __future__ import annotations
from typing import Optional


class ResourceLedger:
    def __init__(self, *, max_external_requests: int = 1000,
                 policy: str = "gentle",
                 stop_at_pct: float = 0.80,
                 long_call_warn_seconds: int = 300):
        self.max_external = int(max_external_requests)
        self.policy = policy
        self.stop_at_pct = float(stop_at_pct)
        self.long_call_warn_seconds = int(long_call_warn_seconds)
        self._external = 0
        self._429 = 0
        self._spawned = 0
        self._closed = 0
        self._compile_attempts = 0
        self._long_calls: list = []

    def record_external_request(self, *, http_status: Optional[int] = None) -> None:
        self._external += 1
        if http_status == 429:
            self._429 += 1

    def record_subagent_spawned(self) -> None:
        self._spawned += 1

    def record_subagent_closed(self) -> None:
        self._closed += 1

    def record_compile_attempt(self) -> None:
        self._compile_attempts += 1

    def record_long_call(self, name: str, *, duration_seconds: float) -> None:
        if duration_seconds >= self.long_call_warn_seconds:
            self._long_calls.append({
                "name": name,
                "duration_seconds": float(duration_seconds),
            })

    def should_stop_external(self) -> bool:
        return self._external >= self.max_external * self.stop_at_pct

    def _budget_status(self) -> str:
        if self._external >= self.max_external:
            return "exceeded"
        if self._external >= self.max_external * self.stop_at_pct:
            return "warning"
        return "under"

    def report(self) -> dict:
        return {
            "external_requests": self._external,
            "rate_limit_429_count": self._429,
            "subagents_spawned": self._spawned,
            "subagents_closed": self._closed,
            "compile_attempts": self._compile_attempts,
            "long_running_calls": list(self._long_calls),
            "budget_policy": self.policy,
            "budget_status": self._budget_status(),
        }

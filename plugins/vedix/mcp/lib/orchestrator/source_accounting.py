"""SourceLedger — per-source provenance for paper_list.json.

Closes review-doc finding #1, #2, #3, #13. Emits source_usage.json that
distinguishes configured / tool_discovered / attempted / successful /
failed / rate_limited / skipped / selected.
"""
from __future__ import annotations
from typing import Optional


class SourceLedger:
    def __init__(self, configured: list):
        self.configured = list(configured)
        self._per_source = {
            src: {
                "configured": True,
                "tool_discovered": False,
                "attempted": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "rate_limit_hits": 0,
                "selected_records": 0,
                "status": "skipped",
                "skipped_reason": None,
            } for src in configured
        }

    def mark_tool_discovered(self, source: str) -> None:
        if source not in self._per_source:
            return
        self._per_source[source]["tool_discovered"] = True
        if self._per_source[source]["status"] == "skipped":
            self._per_source[source]["status"] = "ok"
            self._per_source[source]["skipped_reason"] = None

    def mark_skipped(self, source: str, reason: str) -> None:
        if source not in self._per_source:
            return
        self._per_source[source]["status"] = "skipped"
        self._per_source[source]["skipped_reason"] = reason

    def record_call(self, source: str, *, success: bool,
                    records_added: int = 0,
                    http_status: Optional[int] = None) -> None:
        if source not in self._per_source:
            return
        rec = self._per_source[source]
        rec["attempted"] += 1
        if success:
            rec["successful_calls"] += 1
            rec["selected_records"] += int(records_added)
        else:
            rec["failed_calls"] += 1
            if http_status == 429:
                rec["rate_limit_hits"] += 1
        # Promote status
        if rec["rate_limit_hits"] >= 3 and rec["successful_calls"] < rec["rate_limit_hits"]:
            rec["status"] = "rate_limited"
        elif rec["failed_calls"] > rec["successful_calls"] > 0:
            rec["status"] = "degraded"
        elif rec["successful_calls"] > 0:
            rec["status"] = "ok"

    def report(self) -> dict:
        return {
            "configured_sources": list(self.configured),
            "per_source": {
                src: {k: v for k, v in rec.items() if k != "rate_limit_hits"}
                for src, rec in self._per_source.items()
            },
        }

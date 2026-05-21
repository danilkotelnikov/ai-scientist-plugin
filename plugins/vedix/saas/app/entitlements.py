"""Tier entitlements (Block 8, spec §8.1).

Source of truth for what a tier can do. Every tier sees every MCP,
every classifier, every template, every language, every BYOK provider.
Paid tiers buy throughput (hosted jobs / concurrency / MCP rate /
audit retention / shared palace / SSO).
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class Tier(str, Enum):
    FREE = "free"
    SOLO = "solo"
    LAB = "lab"
    INSTITUTION = "institution"


# Shared feature surface — same for every tier.
_ALL_FEATURES: dict[str, Any] = {
    "mcps": "all",
    "rigor_tracks": "all",
    "publisher_templates": "all",
    "languages": "all",
    "byok_providers": "all",
    "classifier_layer_b": True,
}

ENTITLEMENT_MATRIX: dict[Tier, dict[str, Any]] = {
    Tier.FREE: {
        **_ALL_FEATURES,
        "hosted_jobs_per_month": 2,
        "concurrent_jobs": 1,
        "mcp_rate_limit_per_min": 30,
        "job_time_limit_min": 30,
        "audit_log_retention_days": 7,
        "shared_palace": False,
        "palace_seats": 1,
        "sso": False,
        "sla": "best-effort",
    },
    Tier.SOLO: {
        **_ALL_FEATURES,
        "hosted_jobs_per_month": 20,
        "concurrent_jobs": 2,
        "mcp_rate_limit_per_min": 120,
        "job_time_limit_min": 90,
        "audit_log_retention_days": 30,
        "shared_palace": False,
        "palace_seats": 1,
        "sso": False,
        "sla": "99.0%",
    },
    Tier.LAB: {
        **_ALL_FEATURES,
        "hosted_jobs_per_month": 200,
        "concurrent_jobs": 8,
        "mcp_rate_limit_per_min": 600,
        "job_time_limit_min": 240,
        "audit_log_retention_days": 90,
        "shared_palace": True,
        "palace_seats": 5,
        "sso": False,
        "sla": "99.5%",
    },
    Tier.INSTITUTION: {
        **_ALL_FEATURES,
        "hosted_jobs_per_month": "unlimited",
        "concurrent_jobs": "per-contract",
        "mcp_rate_limit_per_min": "per-contract",
        "job_time_limit_min": "per-contract",
        "audit_log_retention_days": 365,
        "shared_palace": True,
        "palace_seats": "unlimited",
        "sso": True,
        "sla": "99.9%",
    },
}


def compute_entitlements(tier: Tier) -> dict[str, Any]:
    """Return a fresh copy of the entitlement dict for `tier`.

    A fresh dict is returned so the caller can't mutate the matrix.
    """
    return dict(ENTITLEMENT_MATRIX[tier])

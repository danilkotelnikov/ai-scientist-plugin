"""Entitlement matrix tests (Block 8 Task 1, spec §8.1)."""
from __future__ import annotations

import pytest

from app.entitlements import ENTITLEMENT_MATRIX, Tier, compute_entitlements


def test_free_tier_gets_all_mcps_and_features() -> None:
    e = compute_entitlements(tier=Tier.FREE)
    # Every feature open
    assert e["mcps"] == "all"
    assert e["rigor_tracks"] == "all"
    assert e["publisher_templates"] == "all"
    assert e["languages"] == "all"
    assert e["byok_providers"] == "all"
    assert e["classifier_layer_b"] is True
    # But limited throughput
    assert e["hosted_jobs_per_month"] == 2
    assert e["concurrent_jobs"] == 1
    assert e["mcp_rate_limit_per_min"] == 30
    assert e["job_time_limit_min"] == 30
    assert e["audit_log_retention_days"] == 7
    assert e["shared_palace"] is False
    assert e["sso"] is False


def test_solo_tier_gets_more_throughput() -> None:
    e = compute_entitlements(tier=Tier.SOLO)
    assert e["mcps"] == "all"
    assert e["hosted_jobs_per_month"] == 20
    assert e["concurrent_jobs"] == 2
    assert e["mcp_rate_limit_per_min"] == 120
    assert e["job_time_limit_min"] == 90
    assert e["audit_log_retention_days"] == 30
    assert e["shared_palace"] is False
    assert e["sso"] is False


def test_lab_tier_gets_more_throughput_and_shared_palace() -> None:
    e = compute_entitlements(tier=Tier.LAB)
    assert e["mcps"] == "all"
    assert e["hosted_jobs_per_month"] == 200
    assert e["concurrent_jobs"] == 8
    assert e["mcp_rate_limit_per_min"] == 600
    assert e["job_time_limit_min"] == 240
    assert e["audit_log_retention_days"] == 90
    assert e["shared_palace"] is True
    assert e["palace_seats"] == 5
    assert e["sso"] is False


def test_institution_tier_is_unlimited() -> None:
    e = compute_entitlements(tier=Tier.INSTITUTION)
    assert e["mcps"] == "all"
    assert e["hosted_jobs_per_month"] == "unlimited"
    assert e["concurrent_jobs"] == "per-contract"
    assert e["mcp_rate_limit_per_min"] == "per-contract"
    assert e["job_time_limit_min"] == "per-contract"
    assert e["audit_log_retention_days"] == 365
    assert e["shared_palace"] is True
    assert e["palace_seats"] == "unlimited"
    assert e["sso"] is True


def test_all_tiers_share_feature_surface() -> None:
    """Sanity: every tier exposes every MCP / classifier / template / lang."""
    for tier in Tier:
        e = compute_entitlements(tier=tier)
        assert e["mcps"] == "all", f"{tier} missing MCPs"
        assert e["rigor_tracks"] == "all", f"{tier} missing rigor tracks"
        assert e["publisher_templates"] == "all", f"{tier} missing templates"
        assert e["languages"] == "all", f"{tier} missing languages"
        assert e["byok_providers"] == "all", f"{tier} missing BYOK providers"
        assert e["classifier_layer_b"] is True, f"{tier} missing layer B"


def test_compute_entitlements_returns_fresh_copy() -> None:
    e1 = compute_entitlements(tier=Tier.FREE)
    e1["hosted_jobs_per_month"] = 999
    e2 = compute_entitlements(tier=Tier.FREE)
    assert e2["hosted_jobs_per_month"] == 2  # original untouched


def test_matrix_keys_cover_every_tier() -> None:
    assert set(ENTITLEMENT_MATRIX.keys()) == set(Tier)

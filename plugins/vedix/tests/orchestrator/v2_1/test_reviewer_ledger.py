# tests/orchestrator/v2_1/test_reviewer_ledger.py
from mcp.lib.orchestrator.reviewer_ledger import build_reviewer_dispatch


def test_native_subagent_mode():
    spawned = [
        {"role": "positive", "agent_id": "a1", "agent_type": "worker",
         "model": "gpt-5.5", "status": "completed"},
        {"role": "negative", "agent_id": "a2", "agent_type": "worker",
         "model": "gpt-5.5", "status": "completed"},
        {"role": "neutral", "agent_id": "a3", "agent_type": "worker",
         "model": "gpt-5.5", "status": "completed"},
    ]
    out = build_reviewer_dispatch(spawned, mode="native_subagents",
                                  max_threads=6, fallback_reason=None)
    assert out["mode"] == "native_subagents"
    assert out["max_threads"] == 6
    assert len(out["reviewers"]) == 3
    assert all(r["status"] == "completed" for r in out["reviewers"])


def test_inline_fallback_records_reason():
    out = build_reviewer_dispatch([
        {"role": "positive", "status": "inline"},
        {"role": "negative", "status": "inline"},
        {"role": "neutral", "status": "inline"},
    ], mode="inline_fallback", max_threads=6,
       fallback_reason="features.multi_agent=false in this Codex session")
    assert out["mode"] == "inline_fallback"
    assert "features.multi_agent" in out["fallback_reason"]


def test_validates_against_schema():
    from mcp.lib.orchestrator.schemas import (
        REVIEWER_DISPATCH_SCHEMA, validate_against)
    out = build_reviewer_dispatch([
        {"role": "r1", "agent_id": "a1", "agent_type": "worker",
         "model": "gpt-5.5", "status": "completed"},
    ], mode="native_subagents", max_threads=6, fallback_reason=None)
    validate_against(out, REVIEWER_DISPATCH_SCHEMA)

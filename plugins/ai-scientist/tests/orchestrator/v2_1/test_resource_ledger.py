# tests/orchestrator/v2_1/test_resource_ledger.py
from mcp.lib.orchestrator.resource_ledger import ResourceLedger


def test_starts_under_budget():
    led = ResourceLedger(max_external_requests=100, policy="gentle")
    assert led.report()["budget_status"] == "under"


def test_warns_at_80_percent():
    led = ResourceLedger(max_external_requests=10, policy="gentle")
    for _ in range(8):
        led.record_external_request()
    assert led.report()["budget_status"] == "warning"
    assert led.should_stop_external() is True


def test_records_subagent_lifecycle():
    led = ResourceLedger(max_external_requests=100, policy="gentle")
    led.record_subagent_spawned()
    led.record_subagent_spawned()
    led.record_subagent_closed()
    rep = led.report()
    assert rep["subagents_spawned"] == 2
    assert rep["subagents_closed"] == 1


def test_records_long_call():
    led = ResourceLedger(max_external_requests=100, policy="gentle")
    led.record_long_call("run_meta_analysis", duration_seconds=700)
    rep = led.report()
    assert len(rep["long_running_calls"]) == 1
    assert rep["long_running_calls"][0]["name"] == "run_meta_analysis"


def test_429_increments_rate_limit_counter():
    led = ResourceLedger(max_external_requests=100, policy="gentle")
    led.record_external_request(http_status=429)
    led.record_external_request(http_status=429)
    led.record_external_request(http_status=200)
    assert led.report()["rate_limit_429_count"] == 2


def test_validates_against_schema():
    from mcp.lib.orchestrator.schemas import RESOURCE_USAGE_SCHEMA, validate_against
    led = ResourceLedger(max_external_requests=100, policy="gentle")
    led.record_external_request()
    led.record_subagent_spawned()
    led.record_subagent_closed()
    validate_against(led.report(), RESOURCE_USAGE_SCHEMA)

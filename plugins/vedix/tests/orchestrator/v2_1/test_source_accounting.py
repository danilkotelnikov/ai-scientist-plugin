# tests/orchestrator/v2_1/test_source_accounting.py
from mcp.lib.orchestrator.source_accounting import SourceLedger


def test_ledger_starts_empty():
    led = SourceLedger(configured=["openalex", "pubmed", "annas_archive"])
    rep = led.report()
    assert sorted(rep["configured_sources"]) == ["annas_archive", "openalex", "pubmed"]
    for src in rep["per_source"].values():
        assert src["attempted"] == 0
        assert src["status"] == "skipped"


def test_record_call_increments_counters():
    led = SourceLedger(configured=["openalex"])
    led.mark_tool_discovered("openalex")
    led.record_call("openalex", success=True, records_added=42)
    led.record_call("openalex", success=True, records_added=58)
    led.record_call("openalex", success=False)
    rep = led.report()
    assert rep["per_source"]["openalex"]["attempted"] == 3
    assert rep["per_source"]["openalex"]["successful_calls"] == 2
    assert rep["per_source"]["openalex"]["failed_calls"] == 1
    assert rep["per_source"]["openalex"]["selected_records"] == 100
    assert rep["per_source"]["openalex"]["status"] == "ok"


def test_skipped_source_records_reason():
    led = SourceLedger(configured=["pubmed"])
    led.mark_skipped("pubmed", "No active PubMed MCP exposed in this session.")
    rep = led.report()
    assert rep["per_source"]["pubmed"]["status"] == "skipped"
    assert rep["per_source"]["pubmed"]["skipped_reason"].startswith("No active PubMed")


def test_rate_limited_source_status():
    led = SourceLedger(configured=["semantic_scholar"])
    led.mark_tool_discovered("semantic_scholar")
    for _ in range(8):
        led.record_call("semantic_scholar", success=False, http_status=429)
    led.record_call("semantic_scholar", success=True, records_added=12)
    rep = led.report()
    assert rep["per_source"]["semantic_scholar"]["status"] == "rate_limited"


def test_validates_against_schema():
    from mcp.lib.orchestrator.schemas import SOURCE_USAGE_SCHEMA, validate_against
    led = SourceLedger(configured=["openalex", "pubmed"])
    led.mark_tool_discovered("openalex")
    led.record_call("openalex", success=True, records_added=100)
    led.mark_skipped("pubmed", "Not exposed.")
    validate_against(led.report(), SOURCE_USAGE_SCHEMA)

# tests/orchestrator/v2_1/test_schemas_v2_1.py
import pytest
import jsonschema
from mcp.lib.orchestrator.schemas import (
    SOURCE_USAGE_SCHEMA, REFERENCES_VALIDATION_SCHEMA,
    REVIEWER_DISPATCH_SCHEMA, RESOURCE_USAGE_SCHEMA,
    validate_against,
)


def test_source_usage_schema_passes_valid():
    valid = {
        "configured_sources": ["openalex", "pubmed"],
        "per_source": {
            "openalex": {"configured": True, "tool_discovered": True,
                         "attempted": 13, "successful_calls": 13,
                         "failed_calls": 0, "selected_records": 100,
                         "status": "ok", "skipped_reason": None},
            "pubmed": {"configured": True, "tool_discovered": False,
                       "attempted": 0, "successful_calls": 0, "failed_calls": 0,
                       "selected_records": 0, "status": "skipped",
                       "skipped_reason": "No active PubMed MCP exposed."},
        }
    }
    validate_against(valid, SOURCE_USAGE_SCHEMA)


def test_source_usage_schema_rejects_missing_status():
    invalid = {"configured_sources": ["openalex"],
               "per_source": {"openalex": {"configured": True}}}
    with pytest.raises(jsonschema.ValidationError):
        validate_against(invalid, SOURCE_USAGE_SCHEMA)


def test_references_validation_schema_passes_valid():
    valid = {
        "total_papers": 200,
        "doi_gate_passed": 187,
        "dropped": [{"key": "Smith2025", "reason": "no_doi"}],
        "validated": [{
            "key": "Doe2024",
            "doi": "10.1038/example",
            "title_score": 0.94,
            "year_match": "pass",
            "first_author_match": "pass",
            "venue_match": "warning",
            "source_checked": ["crossref", "openalex"],
            "status": "validated",
        }],
    }
    validate_against(valid, REFERENCES_VALIDATION_SCHEMA)


def test_reviewer_dispatch_schema_passes_native():
    valid = {
        "mode": "native_subagents",
        "max_threads": 6,
        "reviewers": [
            {"role": "positive", "agent_id": "ag_a1", "agent_type": "worker",
             "model": "gpt-5.5", "status": "completed"},
        ],
        "fallback_reason": None,
    }
    validate_against(valid, REVIEWER_DISPATCH_SCHEMA)


def test_resource_usage_schema_passes_valid():
    valid = {
        "external_requests": 23,
        "rate_limit_429_count": 9,
        "subagents_spawned": 3,
        "subagents_closed": 3,
        "compile_attempts": 2,
        "long_running_calls": [{"name": "run_meta_analysis", "duration_seconds": 700}],
        "budget_policy": "gentle",
        "budget_status": "warning",
    }
    validate_against(valid, RESOURCE_USAGE_SCHEMA)

"""Strict JSON schemas per phase output. Per spec §4.3.

Two enforcement points:
  1. `strict: true` on the agent's tool-use schema (where the host supports it)
  2. validate_against() called on the parsed output before commit
On schema violation: re-prompt with the validator error inlined, max 2 retries.
"""
from __future__ import annotations
import jsonschema


def validate_against(obj, schema):
    """Raise jsonschema.ValidationError if obj fails the schema."""
    jsonschema.validate(obj, schema)


IDEATION_SCHEMA = {
    "type": "object",
    "required": ["Name", "Title", "Short_Hypothesis", "Related_Work",
                 "Abstract", "Experiments", "Risks"],
    "properties": {
        "Name":             {"type": "string", "minLength": 1},
        "Title":            {"type": "string", "minLength": 1},
        "Short_Hypothesis": {"type": "string", "minLength": 1},
        "Related_Work":     {"type": "string"},
        "Abstract":         {"type": "string", "minLength": 50},
        "Experiments":      {"type": "array", "minItems": 1,
                             "items": {"type": "object", "required": ["name", "metric"]}},
        "Risks":            {"type": "array"},
    },
}

HYPOTHESIS_SCHEMA = {
    "type": "object",
    "required": ["hypothesis", "math_models", "statistical_framework",
                 "methodology", "dependencies"],
    "properties": {
        "hypothesis":            {"type": "string", "minLength": 10},
        "math_models":           {"type": "string"},
        "statistical_framework": {"type": "object"},
        "methodology":           {"type": "string"},
        "dependencies":          {"type": "array", "items": {"type": "string"}},
    },
}

REVIEW_SCHEMA = {
    "type": "object",
    "required": ["Summary", "Strengths", "Weaknesses",
                 "Originality", "Quality", "Clarity", "Significance",
                 "Soundness", "Presentation", "Contribution",
                 "Overall", "Confidence", "Decision",
                 "Questions", "Limitations", "Actionable_Fixes"],
    "properties": {
        "Summary":     {"type": "string"},
        "Strengths":   {"type": "array", "items": {"type": "string"}},
        "Weaknesses":  {"type": "array", "items": {"type": "string"}},
        "Originality": {"type": "integer", "minimum": 1, "maximum": 4},
        "Quality":     {"type": "integer", "minimum": 1, "maximum": 4},
        "Clarity":     {"type": "integer", "minimum": 1, "maximum": 4},
        "Significance":{"type": "integer", "minimum": 1, "maximum": 4},
        "Soundness":   {"type": "integer", "minimum": 1, "maximum": 4},
        "Presentation":{"type": "integer", "minimum": 1, "maximum": 4},
        "Contribution":{"type": "integer", "minimum": 1, "maximum": 4},
        "Overall":     {"type": "integer", "minimum": 1, "maximum": 10},
        "Confidence":  {"type": "integer", "minimum": 1, "maximum": 5},
        "Decision":    {"type": "string"},
        "Questions":   {"type": "array"},
        "Limitations": {"type": "array"},
        "Actionable_Fixes": {"type": "array", "items": {"type": "string"}},
    },
}

EXPERIMENT_RESULT_SCHEMA = {
    "type": "object",
    "required": ["exit_code", "results_csv_present", "npy_files", "figures",
                 "fix_attempts", "stdout_summary", "stderr_summary"],
    "properties": {
        "exit_code":           {"type": "integer"},
        "results_csv_present": {"type": "boolean"},
        "npy_files":           {"type": "array", "items": {"type": "string"}},
        "figures":             {"type": "array", "items": {"type": "string"}},
        "fix_attempts":        {"type": "integer", "minimum": 0},
        "stdout_summary":      {"type": "string"},
        "stderr_summary":      {"type": "string"},
    },
}

SOURCE_USAGE_SCHEMA = {
    "type": "object",
    "required": ["configured_sources", "per_source"],
    "properties": {
        "configured_sources": {"type": "array", "items": {"type": "string"}},
        "per_source": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["configured", "tool_discovered", "attempted",
                             "successful_calls", "failed_calls",
                             "selected_records", "status"],
                "properties": {
                    "configured": {"type": "boolean"},
                    "tool_discovered": {"type": "boolean"},
                    "attempted": {"type": "integer", "minimum": 0},
                    "successful_calls": {"type": "integer", "minimum": 0},
                    "failed_calls": {"type": "integer", "minimum": 0},
                    "selected_records": {"type": "integer", "minimum": 0},
                    "status": {"type": "string",
                               "enum": ["ok", "degraded", "skipped",
                                        "rate_limited", "error"]},
                    "skipped_reason": {"type": ["string", "null"]},
                },
            },
        },
    },
}

REFERENCES_VALIDATION_SCHEMA = {
    "type": "object",
    "required": ["total_papers", "doi_gate_passed", "dropped", "validated"],
    "properties": {
        "total_papers": {"type": "integer", "minimum": 0},
        "doi_gate_passed": {"type": "integer", "minimum": 0},
        "dropped": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "reason"],
                "properties": {
                    "key": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "validated": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "doi", "title_score", "status"],
                "properties": {
                    "key": {"type": "string"},
                    "doi": {"type": "string"},
                    "title_score": {"type": "number", "minimum": 0,
                                    "maximum": 1},
                    "year_match": {"type": "string",
                                   "enum": ["pass", "warning", "fail",
                                            "unknown"]},
                    "first_author_match": {"type": "string",
                                           "enum": ["pass", "warning",
                                                    "fail", "unknown"]},
                    "venue_match": {"type": "string",
                                    "enum": ["pass", "warning", "fail",
                                             "unknown"]},
                    "source_checked": {"type": "array",
                                       "items": {"type": "string"}},
                    "status": {"type": "string",
                               "enum": ["validated", "unverified",
                                        "human_review_needed"]},
                },
            },
        },
    },
}

REVIEWER_DISPATCH_SCHEMA = {
    "type": "object",
    "required": ["mode", "reviewers"],
    "properties": {
        "mode": {"type": "string",
                 "enum": ["native_subagents", "inline_fallback"]},
        "max_threads": {"type": "integer", "minimum": 1},
        "reviewers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["role", "status"],
                "properties": {
                    "role": {"type": "string"},
                    "agent_id": {"type": ["string", "null"]},
                    "agent_type": {"type": ["string", "null"]},
                    "model": {"type": ["string", "null"]},
                    "status": {"type": "string",
                               "enum": ["completed", "failed", "timeout",
                                        "inline"]},
                },
            },
        },
        "fallback_reason": {"type": ["string", "null"]},
    },
}

RESOURCE_USAGE_SCHEMA = {
    "type": "object",
    "required": ["external_requests", "subagents_spawned", "budget_status"],
    "properties": {
        "external_requests": {"type": "integer", "minimum": 0},
        "rate_limit_429_count": {"type": "integer", "minimum": 0},
        "subagents_spawned": {"type": "integer", "minimum": 0},
        "subagents_closed": {"type": "integer", "minimum": 0},
        "compile_attempts": {"type": "integer", "minimum": 0},
        "long_running_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "duration_seconds"],
                "properties": {
                    "name": {"type": "string"},
                    "duration_seconds": {"type": "number", "minimum": 0},
                },
            },
        },
        "budget_policy": {"type": "string",
                          "enum": ["gentle", "normal", "aggressive"]},
        "budget_status": {"type": "string",
                          "enum": ["under", "warning", "exceeded"]},
    },
}

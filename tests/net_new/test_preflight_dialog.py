"""Tests for §5.1 form-driven pre-experimental dialog."""
from __future__ import annotations

import pytest

from plugins.vedix.mcp.lib.orchestrator.preflight_dialog import (
    ExperimentSetup,
    get_setup_schema,
    validate_setup,
)


def test_setup_validates_required_fields():
    setup = ExperimentSetup(
        topic="solvent polarity on Diels-Alder",
        discipline="chemistry",
        language="en",
        venue="preprint",
        hypothesis_style="exploratory",
        experiment_type="computational",
        primary_metric="reaction yield",
        expected_direction="increase",
        tolerance=0.05,
    )
    validate_setup(setup)  # no raise


def test_setup_rejects_invalid_discipline():
    with pytest.raises(ValueError, match="discipline"):
        ExperimentSetup(
            topic="x" * 12,
            discipline="invented-field",  # pyright: ignore[reportArgumentType]
            language="en",
            venue="preprint",
            hypothesis_style="confirmatory",
            experiment_type="empirical",
            primary_metric="x",
            expected_direction="increase",
            tolerance=0.01,
        )


def test_schema_exposed_for_webui():
    schema = get_setup_schema()
    assert "properties" in schema
    assert "topic" in schema["properties"]

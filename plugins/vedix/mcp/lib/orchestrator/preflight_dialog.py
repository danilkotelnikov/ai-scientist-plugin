"""§5.1 Form-driven pre-experimental dialog.

Captures the structured up-front configuration that the orchestrator needs
before any agent fires: topic, discipline, language, target venue,
hypothesis style, experiment type, primary metric, expected direction,
and numeric tolerance.

The `ExperimentSetup` Pydantic v2 model double-duties as:

* a CLI argparse target (one field per `--<name>` flag), and
* a JSON Schema served to the future web UI (Block 9) and IDE plugins
  (Block 10) via `get_setup_schema()`.

`validate_setup` is the cross-field hook for soft-warn rules that do not
belong on individual `field_validator`s.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

VALID_DISCIPLINES: set[str] = {
    "chemistry",
    "biology",
    "medicine",
    "physics",
    "mathematics",
    "geology",
    "computer_science",
    "humanities",
}

VALID_LANGUAGES: set[str] = {"en", "ru", "es", "de", "fr", "zh", "ja"}

VALID_VENUES: set[str] = {
    "preprint",
    "nature",
    "elsevier",
    "springer-nature",
    "taylor-francis",
    "frontiers",
    "wiley",
    "sage",
    "plos",
    "cell",
    "ieee",
    "acm",
    "acs",
    "mdpi",
    "revtex42",
    "rsc",
    "cambridge",
    "oup",
    "bmj",
    "jama",
    "gost-generic",
    "dan-ras",
    "uspekhi",
}


class ExperimentSetup(BaseModel):
    """Structured pre-experimental form.

    Field constraints are enforced by Pydantic at construction. Cross-field
    or soft-warn rules live in `validate_setup`.
    """

    topic: str = Field(min_length=10, max_length=500)
    discipline: Literal[
        "chemistry",
        "biology",
        "medicine",
        "physics",
        "mathematics",
        "geology",
        "computer_science",
        "humanities",
    ]
    language: Literal["en", "ru", "es", "de", "fr", "zh", "ja"]
    venue: str
    hypothesis_style: Literal[
        "confirmatory", "exploratory", "comparative", "descriptive"
    ]
    experiment_type: Literal["empirical", "computational", "review", "theoretical"]
    primary_metric: str
    expected_direction: Literal["increase", "decrease", "no-change", "comparison"]
    tolerance: float = Field(gt=0, lt=1)
    codebase_path: str | None = None

    @field_validator("venue")
    @classmethod
    def _venue_known(cls, v: str) -> str:
        # Accept venue or "venue:journal"
        base = v.split(":", 1)[0]
        if base not in VALID_VENUES:
            raise ValueError(
                f"venue must be one of {sorted(VALID_VENUES)} (got {base!r})"
            )
        return v


def validate_setup(setup: ExperimentSetup) -> None:
    """Cross-field validation hook.

    Pydantic field validators already cover required + typed constraints.
    This function is the place to add soft-warn rules that cannot be
    expressed declaratively (e.g. discipline / experiment_type pairings).
    Raise `ValueError` for hard rejections.
    """
    # Empirical experiments without a codebase pointer are common (lab work);
    # we don't hard-block. Keep the hook so callers have a stable entry.
    if setup.experiment_type == "empirical" and setup.codebase_path is None:
        return


def get_setup_schema() -> dict:
    """Return the JSON Schema for the web UI / IDE plugins."""
    return ExperimentSetup.model_json_schema()

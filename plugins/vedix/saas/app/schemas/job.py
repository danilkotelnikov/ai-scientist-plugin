"""Job request/response shapes.

``JobCreateRequest`` is the same Pydantic model the plugin uses for the
preflight dialog (``orchestrator.preflight_dialog.ExperimentSetup``) so
there is exactly one source of truth for the structured experiment form.
The plugin tree is added to ``sys.path`` lazily; if that path is missing
(e.g. the SaaS is deployed standalone in a slim container), a
self-contained fallback model is used.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# Make the orchestrator module importable.
_PLUGIN_LIB = Path(__file__).resolve().parents[3] / "mcp" / "lib"
if str(_PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_LIB))

try:
    from orchestrator.preflight_dialog import ExperimentSetup as JobCreateRequest
except Exception:  # pragma: no cover - standalone-deployment fallback
    class JobCreateRequest(BaseModel):  # type: ignore[no-redef]
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
        experiment_type: Literal[
            "empirical", "computational", "review", "theoretical"
        ]
        primary_metric: str
        expected_direction: Literal[
            "increase", "decrease", "no-change", "comparison"
        ]
        tolerance: float = Field(gt=0, lt=1)
        codebase_path: str | None = None


class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    state: str


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    state: str
    phase: str | None = None
    progress: int = 0
    artifact_root: str | None = None
    error: str | None = None


__all__ = [
    "JobCreateRequest",
    "JobCreateResponse",
    "JobStatusResponse",
]

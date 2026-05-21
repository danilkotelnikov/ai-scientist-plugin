"""StageGate — structured eval specs between phases. Per spec §4.11.

Per Sakana AgentManager.stage_progress_eval_spec. Block phase advancement on
ready=False. Closes the 'writing manuscripts on incomplete experiments'
failure mode.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class StageGateResult:
    phase: str
    ready: bool
    missing: list


# Default criteria per phase — documented for the evaluator's reference
DEFAULT_CRITERIA = {
    "ideation":   ["≥3 candidates schema-valid", "all have testable hypothesis"],
    "hypothesis": ["math present", "stat framework present", "dependencies listed"],
    "codegen":    ["parses (AST valid)", "all imports resolve", "smoke fixture runs"],
    "experiment": ["exit_code == 0", "results.csv exists", "≥1 figure"],
    "manuscript": ["compiles", r"no \cite{?}", "all figs referenced", "no placeholders"],
    "review":     ["median score recorded", "all 3 reviewers ran"],
}


class StageGate:
    def __init__(self, *, evaluator: Callable, enabled: bool = True, criteria: Optional[dict] = None):
        self.evaluator = evaluator
        self.enabled = enabled
        self.criteria = criteria or DEFAULT_CRITERIA

    def gate(self, *, phase: str, artifacts: dict) -> StageGateResult:
        if not self.enabled:
            return StageGateResult(phase=phase, ready=True, missing=[])
        criteria_for_phase = self.criteria.get(phase, [])
        eval_result = self.evaluator(
            phase=phase,
            artifacts=artifacts,
            expected_criteria=criteria_for_phase,
        )
        return StageGateResult(
            phase=phase,
            ready=bool(eval_result.get("ready_for_next_stage", False)),
            missing=list(eval_result.get("missing_criteria", [])),
        )

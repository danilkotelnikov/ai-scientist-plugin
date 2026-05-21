"""ReflectionLoop — multi-round refinement with error injection. Per spec §4.6.

Used by Phases 0.5, 2, 3, 5, 7. Closes:
  - 'no multi-round refinement' (loop exists)
  - 'no error injection' (history fed into next round)
  - 'no semantic consistency check' (evaluator verdict gates)
  - 'weak schema enforcement' (re-prompt on jsonschema fail)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
import jsonschema

from .convergence import SemanticConvergence


@dataclass
class EvaluatorVerdict:
    verdict: str  # 'PASS' | 'NEEDS_IMPROVEMENT' | 'FAIL'
    reason: str


class ReflectionLoop:
    def __init__(
        self,
        *,
        dispatcher: Callable,           # (agent_name, inputs) -> raw response
        evaluator: Callable,            # (parsed_output) -> EvaluatorVerdict
        schema: dict,                   # jsonschema for parsed_output
        extractor: Callable,            # (raw_response) -> parsed dict
        convergence: Optional[SemanticConvergence] = None,
    ):
        self.dispatcher = dispatcher
        self.evaluator = evaluator
        self.schema = schema
        self.extractor = extractor
        self.convergence = convergence or SemanticConvergence()

    def run(
        self,
        *,
        agent_name: str,
        inputs: dict,
        max_rounds: int = 5,
        error_injection: bool = True,
    ) -> dict:
        history = []
        last_parsed = None
        for round_n in range(max_rounds):
            round_inputs = dict(inputs)
            if error_injection and history:
                round_inputs["prior_attempts"] = history
            response = self.dispatcher(agent_name=agent_name, inputs=round_inputs)
            raw = response.get("raw", "") if isinstance(response, dict) else str(response)
            # Try to extract + validate
            try:
                parsed = self.extractor(response)
                jsonschema.validate(parsed, self.schema)
            except Exception as e:
                history.append({
                    "round": round_n,
                    "raw": raw[:1000],
                    "error": f"schema/extract failed: {e}",
                })
                continue
            last_parsed = parsed
            # Semantic convergence check on raw text
            if self.convergence.is_converged(raw):
                return parsed
            # Evaluator gate
            verdict = self.evaluator(parsed)
            if verdict.verdict == "PASS":
                return parsed
            history.append({
                "round": round_n,
                "raw": raw[:1000],
                "critique": verdict.reason,
            })
        # Exhausted max_rounds; accept best (last parsed) per spec §4.6
        if last_parsed is None:
            raise RuntimeError(
                f"ReflectionLoop({agent_name}): no valid output after {max_rounds} rounds"
            )
        return last_parsed

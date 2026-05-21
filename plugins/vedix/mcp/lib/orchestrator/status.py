"""AgentStatus enum + BLOCKED decision tree per spec §4.9 and §6.3."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class AgentStatus(str, Enum):
    DONE = "done"
    DONE_WITH_CONCERNS = "done_with_concerns"
    BLOCKED = "blocked"
    NEEDS_CONTEXT = "needs_context"


@dataclass
class AgentResponse:
    status: AgentStatus
    reason: str
    payload: Any = None


@dataclass
class NextAction:
    action: str  # 'proceed' | 'proceed_with_logging' | 'extract_context_and_redispatch' | 'redispatch' | 'ask_user_question'
    model: Optional[str] = None
    notes: str = ""


_MODEL_ESCALATION = {"sonnet": "opus", "opus": "opus"}  # opus stays opus (caller bumps thinking)


def decide_next_action(
    response: AgentResponse,
    *,
    current_model: str,
    escalation_count: int,
    max_escalations: int = 2,
) -> NextAction:
    """Decision tree per spec §6.3.

    Never silently retry the same model on the same prompt.
    """
    if response.status == AgentStatus.DONE:
        return NextAction(action="proceed")
    if response.status == AgentStatus.DONE_WITH_CONCERNS:
        return NextAction(action="proceed_with_logging", notes=response.reason)
    if response.status == AgentStatus.NEEDS_CONTEXT:
        return NextAction(
            action="extract_context_and_redispatch",
            model=current_model,
            notes=response.reason,
        )
    # BLOCKED
    if escalation_count >= max_escalations:
        return NextAction(action="ask_user_question", notes=response.reason)
    reason_lc = response.reason.lower()
    if "needs more context" in reason_lc or "missing" in reason_lc:
        return NextAction(
            action="extract_context_and_redispatch",
            model=current_model,
            notes=response.reason,
        )
    if "needs harder reasoning" in reason_lc or "non-trivial" in reason_lc:
        # `.get(..., current_model)` keeps non-Anthropic models (Codex, Gemini) usable.
        # Caller may swap to a stronger Codex/Gemini variant by other means.
        return NextAction(
            action="redispatch",
            model=_MODEL_ESCALATION.get(current_model, current_model),
        )
    if "task too large" in reason_lc:
        return NextAction(action="redispatch", model=current_model, notes="break into sub-tasks")
    return NextAction(action="ask_user_question", notes=response.reason)

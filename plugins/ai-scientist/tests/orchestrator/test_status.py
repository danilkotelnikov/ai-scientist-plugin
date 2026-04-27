import pytest
from mcp.lib.orchestrator.status import AgentStatus, AgentResponse, decide_next_action


def test_agent_status_enum_values():
    assert AgentStatus.DONE.value == "done"
    assert AgentStatus.DONE_WITH_CONCERNS.value == "done_with_concerns"
    assert AgentStatus.BLOCKED.value == "blocked"
    assert AgentStatus.NEEDS_CONTEXT.value == "needs_context"


def test_blocked_needs_more_context_re_dispatches_same_model():
    response = AgentResponse(
        status=AgentStatus.BLOCKED,
        reason="needs more context: missing paper_list.json",
        payload=None,
    )
    decision = decide_next_action(response, current_model="opus", escalation_count=0)
    assert decision.action == "extract_context_and_redispatch"
    assert decision.model == "opus"


def test_blocked_needs_harder_reasoning_escalates_model():
    response = AgentResponse(
        status=AgentStatus.BLOCKED,
        reason="needs harder reasoning: synthesis is non-trivial",
        payload=None,
    )
    decision = decide_next_action(response, current_model="sonnet", escalation_count=0)
    assert decision.action == "redispatch"
    assert decision.model == "opus"


def test_blocked_after_2_escalations_asks_user():
    response = AgentResponse(
        status=AgentStatus.BLOCKED,
        reason="fundamentally stuck",
        payload=None,
    )
    decision = decide_next_action(response, current_model="opus", escalation_count=2)
    assert decision.action == "ask_user_question"


def test_done_with_concerns_proceeds():
    response = AgentResponse(
        status=AgentStatus.DONE_WITH_CONCERNS,
        reason="abstract is short",
        payload={"abstract": "..."},
    )
    decision = decide_next_action(response, current_model="opus", escalation_count=0)
    assert decision.action == "proceed_with_logging"


def test_needs_context_extracts_and_redispatches():
    response = AgentResponse(
        status=AgentStatus.NEEDS_CONTEXT,
        reason="needs paper_list.json",
        payload=None,
    )
    decision = decide_next_action(response, current_model="sonnet", escalation_count=0)
    assert decision.action == "extract_context_and_redispatch"

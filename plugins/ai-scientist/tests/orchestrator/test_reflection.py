from unittest.mock import MagicMock
from mcp.lib.orchestrator.reflection import ReflectionLoop, EvaluatorVerdict


def test_loop_returns_on_first_pass():
    dispatcher = MagicMock(return_value={"raw": '{"k":"v"}'})
    evaluator = MagicMock(return_value=EvaluatorVerdict(verdict="PASS", reason=""))
    loop = ReflectionLoop(
        dispatcher=dispatcher,
        evaluator=evaluator,
        schema={"type": "object", "required": ["k"]},
        extractor=lambda r: __import__("json").loads(r["raw"]),
    )
    result = loop.run(agent_name="ideator", inputs={"x": 1}, max_rounds=5)
    assert result == {"k": "v"}
    assert dispatcher.call_count == 1


def test_loop_re_dispatches_on_needs_improvement():
    responses = [
        {"raw": '{"k":"bad"}'},
        {"raw": '{"k":"better"}'},
        {"raw": '{"k":"best"}'},
    ]
    dispatcher = MagicMock(side_effect=responses)
    verdicts = [
        EvaluatorVerdict(verdict="NEEDS_IMPROVEMENT", reason="bad value"),
        EvaluatorVerdict(verdict="NEEDS_IMPROVEMENT", reason="still bad"),
        EvaluatorVerdict(verdict="PASS", reason=""),
    ]
    evaluator = MagicMock(side_effect=verdicts)
    loop = ReflectionLoop(
        dispatcher=dispatcher,
        evaluator=evaluator,
        schema={"type": "object"},
        extractor=lambda r: __import__("json").loads(r["raw"]),
    )
    result = loop.run(agent_name="ideator", inputs={"x": 1}, max_rounds=5)
    assert result == {"k": "best"}
    assert dispatcher.call_count == 3


def test_loop_injects_history_on_re_dispatch():
    responses = [
        {"raw": '{"k":"v1"}'},
        {"raw": '{"k":"v2"}'},
    ]
    captured_inputs = []

    def fake_dispatcher(*, agent_name, inputs):
        captured_inputs.append(inputs)
        return responses[len(captured_inputs) - 1]

    verdicts = [
        EvaluatorVerdict(verdict="NEEDS_IMPROVEMENT", reason="too short"),
        EvaluatorVerdict(verdict="PASS", reason=""),
    ]
    evaluator = MagicMock(side_effect=verdicts)
    loop = ReflectionLoop(
        dispatcher=fake_dispatcher,
        evaluator=evaluator,
        schema={"type": "object"},
        extractor=lambda r: __import__("json").loads(r["raw"]),
    )
    loop.run(agent_name="ideator", inputs={"x": 1}, max_rounds=5, error_injection=True)
    # Round 2 should have prior_attempts in its inputs
    assert "prior_attempts" in captured_inputs[1]
    assert len(captured_inputs[1]["prior_attempts"]) == 1
    assert "too short" in str(captured_inputs[1]["prior_attempts"])


def test_loop_returns_best_after_max_rounds():
    dispatcher = MagicMock(return_value={"raw": '{"k":"v"}'})
    evaluator = MagicMock(return_value=EvaluatorVerdict(verdict="NEEDS_IMPROVEMENT", reason="never good"))
    loop = ReflectionLoop(
        dispatcher=dispatcher,
        evaluator=evaluator,
        schema={"type": "object"},
        extractor=lambda r: __import__("json").loads(r["raw"]),
    )
    result = loop.run(agent_name="x", inputs={}, max_rounds=3)
    assert result == {"k": "v"}
    assert dispatcher.call_count == 3


def test_loop_re_prompts_on_schema_failure():
    responses = [
        {"raw": '{"wrong":"schema"}'},
        {"raw": '{"required":"present"}'},
    ]
    dispatcher = MagicMock(side_effect=responses)
    evaluator = MagicMock(return_value=EvaluatorVerdict(verdict="PASS", reason=""))
    loop = ReflectionLoop(
        dispatcher=dispatcher,
        evaluator=evaluator,
        schema={"type": "object", "required": ["required"]},
        extractor=lambda r: __import__("json").loads(r["raw"]),
    )
    result = loop.run(agent_name="x", inputs={}, max_rounds=5)
    assert result == {"required": "present"}
    assert dispatcher.call_count == 2

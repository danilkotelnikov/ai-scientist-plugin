from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.pipeline import Pipeline


def test_phase_0_init_creates_dirs_and_config(tmp_path):
    pipeline = Pipeline(
        dispatcher=MagicMock(),
        evaluator=MagicMock(),
        host="claude_code",
        plugin_palace=None,
        project_palace=None,
    )
    pipeline.phase_0_init(
        topic="ridge regression",
        domain="statistical",
        output_dir=tmp_path,
    )
    assert (tmp_path / "config.json").is_file()
    assert (tmp_path / ".checkpoints").is_dir()
    assert (tmp_path / ".palace").is_dir()


def test_phase_0_5_ideation_produces_3_candidates(tmp_path):
    fake_dispatcher = MagicMock(side_effect=[
        {"raw": '{"Name":"a","Title":"A","Short_Hypothesis":"h","Related_Work":"rw","Abstract":"' + "x"*80 + '","Experiments":[{"name":"e","metric":"m"}],"Risks":["r"]}'},
        {"raw": '{"Name":"b","Title":"B","Short_Hypothesis":"h","Related_Work":"rw","Abstract":"' + "x"*80 + '","Experiments":[{"name":"e","metric":"m"}],"Risks":["r"]}'},
        {"raw": '{"Name":"c","Title":"C","Short_Hypothesis":"h","Related_Work":"rw","Abstract":"' + "x"*80 + '","Experiments":[{"name":"e","metric":"m"}],"Risks":["r"]}'},
    ])
    fake_evaluator = MagicMock(return_value={"verdict": "PASS", "reason": ""})
    pipeline = Pipeline(
        dispatcher=fake_dispatcher,
        evaluator=fake_evaluator,
        host="claude_code",
    )
    pipeline.phase_0_init(topic="t", domain="statistical", output_dir=tmp_path)
    candidates = pipeline.phase_0_5_ideation(topic="t", domain="statistical", num_candidates=3)
    assert len(candidates) == 3
    assert (tmp_path / "idea_candidates.json").is_file()


def test_phase_1_dedups_papers(tmp_path):
    fake_dispatcher = MagicMock(return_value={"raw": '[{"title":"A","doi":"10.1/x"},{"title":"A","doi":"10.1/x"}]'})
    pipeline = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(), host="claude_code")
    pipeline.phase_0_init(topic="t", domain="statistical", output_dir=tmp_path)
    papers = pipeline.phase_1_literature(idea={"Title": "ridge"}, sources=["openalex"])
    assert len(papers) == 1


def test_phase_3_codegen_writes_files(tmp_path):
    fake_dispatcher = MagicMock(return_value={"raw": '```python\nprint("ok")\n```'})
    pipeline = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(), host="claude_code")
    pipeline.phase_0_init(topic="t", domain="statistical", output_dir=tmp_path)
    result = pipeline.phase_3_codegen(hypothesis={"hypothesis": "h"}, max_rounds=1)
    assert (tmp_path / "experiment.py").is_file()
    assert (tmp_path / "requirements.txt").is_file()


def test_phase_4_routes_to_bfts_when_use_bfts(tmp_path):
    fake_dispatcher = MagicMock(return_value={"raw": '{"final_exit_code":0,"results_csv_present":true,"npy_files":[],"figures":[],"fix_attempts":0,"stdout_summary":"","stderr_summary":""}'})
    pipeline = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(), host="claude_code")
    pipeline.phase_0_init(topic="t", domain="statistical", output_dir=tmp_path)
    pipeline.phase_4_experiment(code_artifacts={}, use_bfts=True)
    call = fake_dispatcher.call_args.kwargs
    assert call["agent_name"] == "tree-search-runner"


def test_run_full_pipeline_returns_summary(tmp_path, monkeypatch):
    """Smoke test the call chain — heavy mock, just verify no errors."""
    fake_dispatcher = MagicMock(return_value={"raw": '{"k":"v"}'})
    fake_evaluator = MagicMock(return_value={"verdict": "PASS", "reason": ""})
    pipeline = Pipeline(dispatcher=fake_dispatcher, evaluator=fake_evaluator, host="claude_code")

    # Stub heavy phases — we just verify the chain doesn't error
    monkeypatch.setattr(
        pipeline, "phase_0_5_ideation",
        lambda **kw: [{"Name": "candidate1", "Title": "A"}, {"Name": "c2", "Title": "B"}],
    )
    monkeypatch.setattr(pipeline, "phase_1_literature", lambda **kw: [])
    monkeypatch.setattr(pipeline, "phase_2_hypothesis", lambda **kw: {"hypothesis": "h"})
    monkeypatch.setattr(pipeline, "phase_3_codegen", lambda **kw: {"code": "x", "requirements": "r"})
    monkeypatch.setattr(pipeline, "phase_4_experiment", lambda **kw: {"stdout_summary": "ok"})
    monkeypatch.setattr(pipeline, "phase_5_5_plotting", lambda **kw: {"figures": []})
    monkeypatch.setattr(pipeline, "phase_5_manuscript", lambda **kw: "TEX")
    monkeypatch.setattr(pipeline, "phase_6_citations", lambda **kw: {"is_clean": True})
    monkeypatch.setattr(pipeline, "phase_7_review", lambda **kw: {"median_overall": 6})
    monkeypatch.setattr(pipeline, "phase_8_compile", lambda **kw: None)
    monkeypatch.setattr(pipeline, "phase_8_25_word", lambda **kw: None)
    monkeypatch.setattr(pipeline, "phase_8_5_vlm", lambda **kw: {"skipped": "no pdf"})
    monkeypatch.setattr(pipeline, "phase_9_index", lambda **kw: None)
    monkeypatch.setattr(pipeline, "phase_10_meta", lambda **kw: {})
    monkeypatch.setattr(pipeline, "phase_11_slides", lambda **kw: None)

    summary = pipeline.run_full_pipeline(
        topic="t", domain="statistical", output_dir=tmp_path,
        interactivity="none",  # skip gates
    )
    assert "job_id" in summary
    assert summary["output_dir"] == str(tmp_path)
    assert "tokens" in summary
    assert "review" in summary


def test_gate_or_default_skips_in_none_interactivity():
    pipeline = Pipeline(dispatcher=MagicMock(), evaluator=MagicMock(), host="claude_code")
    result = pipeline._gate_or_default(
        gate_id=1, default="default_value", question="?",
        options=["a", "b"], callback=None, interactivity="none", critical=True,
    )
    assert result == "default_value"


def test_gate_or_default_skips_non_critical_in_checkpoints_mode():
    pipeline = Pipeline(dispatcher=MagicMock(), evaluator=MagicMock(), host="claude_code")
    callback = MagicMock(return_value="user_choice")
    result = pipeline._gate_or_default(
        gate_id=1, default="default_value", question="?",
        options=["a"], callback=callback, interactivity="checkpoints", critical=False,
    )
    assert result == "default_value"
    callback.assert_not_called()


def test_gate_or_default_calls_callback_when_critical_in_checkpoints_mode():
    pipeline = Pipeline(dispatcher=MagicMock(), evaluator=MagicMock(), host="claude_code")
    callback = MagicMock(return_value="user_choice")
    result = pipeline._gate_or_default(
        gate_id=1, default="default_value", question="?",
        options=["a"], callback=callback, interactivity="checkpoints", critical=True,
    )
    assert result == "user_choice"
    callback.assert_called_once()


def test_run_full_pipeline_smoke(tmp_path, monkeypatch):
    """Smoke test — verify the call chain doesn't error.
    Each phase is stubbed to return a minimal valid response so we don't
    require real LaTeX/pandoc/python/etc. installations.
    """
    fake_dispatcher = MagicMock(return_value={"raw": '{"k":"v"}'})
    pipeline = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(return_value={"verdict": "PASS", "reason": ""}), host="claude_code")

    # Stub heavy phases to keep this a smoke test
    monkeypatch.setattr(pipeline, "phase_0_5_ideation",
        lambda **kw: [{"Name": "a", "Title": "T", "Short_Hypothesis": "h"},
                       {"Name": "b", "Title": "T2", "Short_Hypothesis": "h2"}])
    monkeypatch.setattr(pipeline, "phase_1_literature", lambda **kw: [{"title": "P1", "year": 2025}])
    monkeypatch.setattr(pipeline, "phase_2_hypothesis", lambda **kw: {"hypothesis": "H", "math_models": "M"})
    monkeypatch.setattr(pipeline, "phase_3_codegen", lambda **kw: {"code": "print(1)", "requirements": ""})
    monkeypatch.setattr(pipeline, "phase_4_experiment", lambda **kw: {"exit_code": 0, "stdout_summary": "ok"})
    monkeypatch.setattr(pipeline, "phase_5_5_plotting", lambda **kw: {"figures": []})
    monkeypatch.setattr(pipeline, "phase_5_manuscript", lambda **kw: "TEX")
    monkeypatch.setattr(pipeline, "phase_6_citations", lambda **kw: {"is_clean": True})
    monkeypatch.setattr(pipeline, "phase_7_review", lambda **kw: {"median_overall": 6, "score_iqr": 1, "consensus_high": True, "has_outliers": False, "individual_reviews": []})
    monkeypatch.setattr(pipeline, "phase_8_compile", lambda **kw: None)
    monkeypatch.setattr(pipeline, "phase_8_25_word", lambda **kw: None)
    monkeypatch.setattr(pipeline, "phase_8_5_vlm", lambda **kw: {})
    monkeypatch.setattr(pipeline, "phase_9_index", lambda **kw: None)
    monkeypatch.setattr(pipeline, "phase_10_meta", lambda **kw: {})
    monkeypatch.setattr(pipeline, "phase_11_slides", lambda **kw: None)

    summary = pipeline.run_full_pipeline(
        topic="t", domain="statistical", output_dir=tmp_path,
        interactivity="none", use_bfts=False,
    )
    assert "job_id" in summary
    assert summary["output_dir"] == str(tmp_path)


def test_gate_or_default_returns_default_when_interactivity_none():
    pipeline = Pipeline(dispatcher=MagicMock(), evaluator=MagicMock(), host="claude_code")
    result = pipeline._gate_or_default(
        gate_id=1, default="A", question="?", options=["A", "B"],
        callback=None, interactivity="none", critical=True,
    )
    assert result == "A"


def test_gate_or_default_calls_callback_when_critical_and_full():
    pipeline = Pipeline(dispatcher=MagicMock(), evaluator=MagicMock(), host="claude_code")
    callback_called = {"n": 0}

    def cb(gate_req):
        callback_called["n"] += 1
        return "B"

    result = pipeline._gate_or_default(
        gate_id=1, default="A", question="?", options=["A", "B"],
        callback=cb, interactivity="full", critical=True,
    )
    assert result == "B"
    assert callback_called["n"] == 1

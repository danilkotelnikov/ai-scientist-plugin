# tests/orchestrator/v2_1/test_pipeline_phase_7r.py
import json, tempfile
from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.pipeline import Pipeline


def test_phase_7r_writes_reviewer_dispatch_inline_when_no_native():
    p = Pipeline(dispatcher=MagicMock(return_value={"Overall": 6}),
                 evaluator=MagicMock(), host="claude_code")
    with tempfile.TemporaryDirectory() as td:
        p.phase_0_init(topic="t", domain="ml", output_dir=Path(td))
        review = p.phase_7r_review(manuscript_tex="\\documentclass{article}",
                                   codex_native_dispatcher=None)
        rd = json.loads(
            (Path(td) / "reviewer_dispatch.json").read_text())
        assert rd["mode"] == "inline_fallback"
        assert len(rd["reviewers"]) == 3
        assert (Path(td) / "review.json").is_file()


def test_phase_7r_writes_reviewer_dispatch_native_when_provided():
    fake_dispatcher = MagicMock(return_value={"Overall": 6})
    fake_native = MagicMock()
    fake_native.dispatch_wave = MagicMock(return_value=[
        {"Overall": 5}, {"Overall": 6}, {"Overall": 7},
    ])
    p = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(),
                 host="codex")
    with tempfile.TemporaryDirectory() as td:
        p.phase_0_init(topic="t", domain="ml", output_dir=Path(td))
        p.phase_7r_review(manuscript_tex="\\documentclass{article}",
                          codex_native_dispatcher=fake_native)
        rd = json.loads(
            (Path(td) / "reviewer_dispatch.json").read_text())
        assert rd["mode"] == "native_subagents"
        assert len(rd["reviewers"]) == 3
        assert all(r["status"] == "completed" for r in rd["reviewers"])

# tests/orchestrator/v2_1/test_run_review_article.py
import json, tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from mcp.lib.orchestrator.pipeline import Pipeline


def test_run_review_article_emits_all_required_artifacts(monkeypatch):
    fake_dispatcher = MagicMock(return_value={"raw": '{"k":"v"}'})
    p = Pipeline(dispatcher=fake_dispatcher,
                 evaluator=MagicMock(return_value={"verdict": "PASS",
                                                   "reason": ""}),
                 host="claude_code")

    # Stub heavy phases
    monkeypatch.setattr(p, "phase_0_5_ideation",
        lambda **kw: [{"Name": "a", "Title": "T",
                       "Short_Hypothesis": "h", "Abstract": "a"*60,
                       "Experiments": [{"name": "e", "metric": "m"}],
                       "Risks": ["r"], "Related_Work": "rw"}])
    monkeypatch.setattr(p, "phase_1_literature",
        lambda **kw: [{"key": "A", "title": "P", "doi": "10.1/x",
                       "source": "openalex"}])
    monkeypatch.setattr(p, "phase_2_hypothesis",
        lambda **kw: {"hypothesis": "H", "math_models": "M"})
    monkeypatch.setattr(p, "phase_5r_manuscript_review_article",
        lambda **kw: r"\documentclass{article}\begin{document}body\end{document}")
    monkeypatch.setattr(p, "phase_6_citations",
        lambda: {"is_clean": True})
    monkeypatch.setattr(p, "phase_7r_review",
        lambda **kw: {"median_overall": 6})
    monkeypatch.setattr(p, "phase_8_compile", lambda: None)
    monkeypatch.setattr(p, "phase_8_25_word", lambda: None)
    monkeypatch.setattr(p, "phase_8_5_vlm", lambda: {})
    monkeypatch.setattr(p, "phase_9_index", lambda **kw: None)
    monkeypatch.setattr(p, "phase_10_meta", lambda: {})
    monkeypatch.setattr(p, "phase_11_slides", lambda: None)

    with tempfile.TemporaryDirectory() as td:
        with patch("mcp.lib.orchestrator.pipeline.validate_corpus") as vc:
            vc.return_value = {"total_papers": 1, "doi_gate_passed": 1,
                               "dropped": [], "validated": [
                {"key": "A", "doi": "10.1/x", "title_score": 0.95,
                 "year_match": "pass", "first_author_match": "pass",
                 "venue_match": "pass", "source_checked": ["crossref"],
                 "status": "validated"}]}
            summary = p.run_review_article_pipeline(
                topic="recent advances in transformers",
                domain="ml",
                output_dir=Path(td),
                crossref_email="t@e.com",
                interactivity="none",
            )
        # Required artifacts (subset of the 12 acceptance criteria)
        assert (Path(td) / "config.json").is_file()
        assert (Path(td) / "references_validation.json").is_file()
        assert (Path(td) / "reviewer_dispatch.json").is_file()
        assert summary["article_type"] == "review"

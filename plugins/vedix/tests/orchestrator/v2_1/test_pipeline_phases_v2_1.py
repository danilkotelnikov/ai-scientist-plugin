# tests/orchestrator/v2_1/test_pipeline_phases_v2_1.py
import json, tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from mcp.lib.orchestrator.pipeline import Pipeline


def test_phase_minus_1_classifies_review():
    p = Pipeline(dispatcher=MagicMock(), evaluator=MagicMock(),
                 host="claude_code")
    with tempfile.TemporaryDirectory() as td:
        p.phase_0_init(topic="recent advances in transformers",
                       domain="ml", output_dir=Path(td))
        result = p.phase_minus_1_intent()
        assert result["article_type"] == "review"
        assert "phase_order" in result
        assert "1.5" in result["phase_order"]


def test_phase_1_5_writes_references_validation():
    p = Pipeline(dispatcher=MagicMock(), evaluator=MagicMock(),
                 host="claude_code")
    with tempfile.TemporaryDirectory() as td:
        p.phase_0_init(topic="t", domain="ml", output_dir=Path(td))
        # Stub paper_list.json
        papers = [{"key": "A", "doi": "10.1/x", "title": "A paper",
                   "source": "openalex"}]
        (Path(td) / "paper_list.json").write_text(json.dumps(papers))
        with patch("mcp.lib.orchestrator.pipeline.validate_corpus") as vc:
            vc.return_value = {
                "total_papers": 1, "doi_gate_passed": 1,
                "dropped": [], "validated": [
                    {"key": "A", "doi": "10.1/x", "title_score": 0.95,
                     "year_match": "pass", "first_author_match": "pass",
                     "venue_match": "pass", "source_checked": ["crossref"],
                     "status": "validated"}]}
            out = p.phase_1_5_metadata_validation(crossref_email="t@e.com")
        rv = json.loads((Path(td) / "references_validation.json").read_text())
        assert rv["doi_gate_passed"] == 1

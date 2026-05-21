# tests/orchestrator/v2_1/test_pipeline_phase_5r.py
import json, tempfile
from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.pipeline import Pipeline


def test_phase_5r_writes_manuscript_with_anti_llm_lint():
    fake_dispatcher = MagicMock(return_value={
        "raw": r"```latex\n\\documentclass{article}\\begin{document}This text is robust and innovative.\\end{document}\n```"
    })
    p = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(),
                 host="claude_code")
    with tempfile.TemporaryDirectory() as td:
        p.phase_0_init(topic="t", domain="ml", output_dir=Path(td))
        out = p.phase_5r_manuscript_review_article(
            papers=[{"key": "A", "title": "A", "doi": "10.1/x"}],
            hypothesis={"hypothesis": "h", "math_models": "m"},
            max_rounds=1,
        )
        assert (Path(td) / "manuscript.tex").is_file()
        # anti_llm_lint output should exist
        assert (Path(td) / "anti_llm_lint.json").is_file()
        lint = json.loads(
            (Path(td) / "anti_llm_lint.json").read_text())
        # 'robust' and 'innovative' are tier-2; 'innovative' on its own won't fire (>=2 needed)
        # but 'robust' + 'innovative' total 2 -> both flagged
        assert lint["paragraph_count"] >= 1

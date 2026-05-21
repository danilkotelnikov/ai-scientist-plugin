# tests/orchestrator/v2_1/test_plotter_cycle2.py
import json, tempfile
from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.plotter_loop import PlotterLoop, PlotSpec, VLM_RUBRIC


def test_rubric_has_10_items():
    assert len(VLM_RUBRIC) == 10
    for item in VLM_RUBRIC:
        assert "id" in item and "question" in item


def test_cycle2_calls_vlm_per_figure_and_aggregates_scores():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        (outdir / "figures_draft1").mkdir()
        (outdir / "figures_draft1" / "fig1.txt").write_text("x")
        (outdir / "figures_draft1" / "fig2.txt").write_text("y")
        # Manifest from cycle 1
        (outdir / "figures_draft1" / "manifest.json").write_text(json.dumps({
            "cycle": 1, "figures": [
                {"figure_id": "fig1", "draft_path": "figures_draft1/fig1.txt",
                 "title": "T1", "kind": "bar"},
                {"figure_id": "fig2", "draft_path": "figures_draft1/fig2.txt",
                 "title": "T2", "kind": "scatter"},
            ]
        }))
        # Mock VLM that scores 4/4 on every rubric item
        vlm = MagicMock(return_value={
            "scores": {item["id"]: 4 for item in VLM_RUBRIC},
            "edits": [],
        })
        loop = PlotterLoop(output_dir=outdir)
        out = loop.cycle2_vlm_critique(vlm_callable=vlm)
        assert vlm.call_count == 2  # 1 call per figure
        rubric_path = outdir / "figures_draft2" / "vlm_rubric.json"
        assert rubric_path.is_file()
        rubric = json.loads(rubric_path.read_text())
        assert len(rubric["figures"]) == 2
        assert rubric["figures"][0]["aggregate_score"] == 40  # 10 × 4

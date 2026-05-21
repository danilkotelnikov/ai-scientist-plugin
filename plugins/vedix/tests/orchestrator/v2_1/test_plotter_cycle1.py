# tests/orchestrator/v2_1/test_plotter_cycle1.py
import json, tempfile
from pathlib import Path
from mcp.lib.orchestrator.plotter_loop import PlotterLoop, PlotSpec


def test_cycle1_emits_manifest():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        # Write a minimal results.csv
        (outdir / "results.csv").write_text(
            "method,accuracy,n\nA,0.82,5\nB,0.79,5\n", encoding="utf-8")
        loop = PlotterLoop(output_dir=outdir, article_type="experimental")
        specs = [PlotSpec(figure_id="fig1", kind="bar",
                          x="method", y="accuracy", title="Accuracy by method")]
        out = loop.cycle1_inspect_and_draft(specs)
        assert (outdir / "figures_draft1" / "manifest.json").is_file()
        manifest = json.loads(
            (outdir / "figures_draft1" / "manifest.json").read_text())
        assert manifest["cycle"] == 1
        assert len(manifest["figures"]) == 1
        assert manifest["figures"][0]["figure_id"] == "fig1"
        assert manifest["figures"][0]["plot_type_rationale"]


def test_cycle1_records_data_schema():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        (outdir / "results.csv").write_text(
            "method,score\nA,0.5\nB,0.7\n", encoding="utf-8")
        loop = PlotterLoop(output_dir=outdir, article_type="experimental")
        specs = [PlotSpec(figure_id="f", kind="bar",
                          x="method", y="score", title="t")]
        loop.cycle1_inspect_and_draft(specs)
        manifest = json.loads(
            (outdir / "figures_draft1" / "manifest.json").read_text())
        schema = manifest["figures"][0]["data_schema"]
        assert "method" in schema["columns"]
        assert "score" in schema["columns"]
        assert schema["row_count"] == 2

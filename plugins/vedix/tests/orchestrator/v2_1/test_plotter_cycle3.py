# tests/orchestrator/v2_1/test_plotter_cycle3.py
import json, tempfile
from pathlib import Path
from mcp.lib.orchestrator.plotter_loop import PlotterLoop, JOURNAL_STYLES


def test_cycle3_emits_metadata_csv_and_includegraphics_tex():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        (outdir / "figures_draft2").mkdir()
        (outdir / "figures_draft2" / "vlm_rubric.json").write_text(json.dumps({
            "cycle": 2,
            "figures": [{"figure_id": "fig1", "scores": {}, "edits": [],
                         "aggregate_score": 38}]
        }))
        # Need draft from cycle 1 too
        (outdir / "figures_draft1").mkdir(exist_ok=True)
        (outdir / "figures_draft1" / "fig1.txt").write_text("draft")
        (outdir / "figures_draft1" / "manifest.json").write_text(json.dumps({
            "cycle": 1,
            "figures": [{"figure_id": "fig1",
                         "draft_path": "figures_draft1/fig1.txt",
                         "title": "T", "kind": "bar"}]
        }))
        loop = PlotterLoop(output_dir=outdir, journal_style="nature")
        out = loop.cycle3_polish_export(mode="scripting")
        assert (outdir / "figures_final" / "figure_metadata.csv").is_file()
        assert (outdir / "figures_final" / "figures.tex").is_file()
        tex = (outdir / "figures_final" / "figures.tex").read_text()
        assert "\\includegraphics" in tex
        assert "fig1" in tex


def test_cycle3_latex_native_emits_tikz_snippets():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        (outdir / "figures_draft1").mkdir()
        (outdir / "figures_draft1" / "manifest.json").write_text(json.dumps({
            "cycle": 1,
            "figures": [{"figure_id": "fig1",
                         "draft_path": "figures_draft1/fig1.txt",
                         "title": "T", "kind": "bar"}]
        }))
        (outdir / "figures_draft2").mkdir()
        (outdir / "figures_draft2" / "vlm_rubric.json").write_text(json.dumps({
            "cycle": 2,
            "figures": [{"figure_id": "fig1", "aggregate_score": 38}]
        }))
        loop = PlotterLoop(output_dir=outdir, journal_style="nature")
        loop.cycle3_polish_export(mode="latex_native")
        tex = (outdir / "figures_final" / "fig1.tex").read_text()
        assert "tikzpicture" in tex


def test_journal_styles_have_expected_keys():
    for jname, j in JOURNAL_STYLES.items():
        assert "single_column_mm" in j
        assert "double_column_mm" in j
        assert "raster_dpi" in j
        assert "font_family" in j

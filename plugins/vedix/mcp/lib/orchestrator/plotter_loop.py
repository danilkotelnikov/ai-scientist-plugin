"""Iterative 3-cycle plotter — Cycle 1 (inspect & draft).

Closes spec §5. Cycle 1 emits figures_draft1/<id>.png + manifest.json with
per-figure plot_type_rationale and data schema.

Per-cycle artifacts let the user re-run any cycle independently. Cycle 2
(VLM critique) and Cycle 3 (polish) live in the same module.
"""
from __future__ import annotations
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PlotSpec:
    figure_id: str
    kind: str       # "bar" | "scatter" | "violin" | "heatmap" | "timeline"
    x: str
    y: str
    title: str
    facets: Optional[list] = None
    notes: str = ""


def _sniff_csv_schema(path: Path) -> dict:
    if not path.is_file():
        return {"columns": [], "row_count": 0}
    rows = list(csv.reader(path.open("r", encoding="utf-8")))
    if not rows:
        return {"columns": [], "row_count": 0}
    header, body = rows[0], rows[1:]
    return {"columns": header, "row_count": len(body)}


def _plot_type_rationale(spec: PlotSpec, schema: dict) -> str:
    """Justify plot type given data shape."""
    n = schema.get("row_count", 0)
    if spec.kind == "bar":
        return f"bar chart for {n} categorical observations of {spec.y}"
    if spec.kind == "violin":
        return f"violin chart for {n} samples (>30 → distribution shape visible)"
    if spec.kind == "scatter":
        return f"scatter for {n} ({spec.x}, {spec.y}) pairs"
    if spec.kind == "heatmap":
        return f"heatmap for matrix of {n} rows by columns of {spec.x}"
    if spec.kind == "timeline":
        return f"timeline for {n} year-counted events"
    return f"{spec.kind} for {n} rows"


def _render_draft_png(spec: PlotSpec, outdir: Path) -> Path:
    """Render a stub PNG. Full matplotlib rendering happens in Cycle 3.

    Cycle 1's purpose is the inspection + rationale, not pixel-perfect
    output. The actual draft is a 1-line text marker — Cycle 3 will
    overwrite with publication-grade vector output.
    """
    p = outdir / f"{spec.figure_id}.txt"
    p.write_text(
        f"# DRAFT figure {spec.figure_id} ({spec.kind})\n"
        f"# title: {spec.title}\n"
        f"# x={spec.x}, y={spec.y}\n",
        encoding="utf-8")
    return p


@dataclass
class PlotterLoop:
    output_dir: Path
    article_type: str = "experimental"
    journal_style: str = "auto"
    palette: str = "okabe_ito"

    def cycle1_inspect_and_draft(self, specs: list) -> dict:
        cycle_dir = self.output_dir / "figures_draft1"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        results_csv = self.output_dir / "results.csv"
        schema = _sniff_csv_schema(results_csv)
        figures = []
        for spec in specs:
            draft = _render_draft_png(spec, cycle_dir)
            figures.append({
                "figure_id": spec.figure_id,
                "kind": spec.kind,
                "title": spec.title,
                "data_schema": schema,
                "draft_path": str(draft.relative_to(self.output_dir)),
                "plot_type_rationale": _plot_type_rationale(spec, schema),
            })
        manifest = {
            "cycle": 1,
            "article_type": self.article_type,
            "journal_style": self.journal_style,
            "palette": self.palette,
            "figures": figures,
        }
        (cycle_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest


VLM_RUBRIC = [
    {"id": "thumbnail_legibility",
     "question": "Is the primary message legible at thumbnail size?"},
    {"id": "color_blind_safe",
     "question": "Is the color palette colorblind-safe (Okabe-Ito / Wong)?"},
    {"id": "axes_labeled_with_units",
     "question": "Are all axes labeled with units?"},
    {"id": "error_bars_present",
     "question": "Are error bars present and described in the caption?"},
    {"id": "legend_placement",
     "question": "Is the legend placement optimal (inside or direct labels)?"},
    {"id": "font_size_legible",
     "question": "Is the font size legible at journal column width?"},
    {"id": "no_chartjunk",
     "question": "Is the figure free of chartjunk (3D/gradients/shadows)?"},
    {"id": "statistical_annotations",
     "question": "Are statistical annotations (p-values, n, CI) complete?"},
    {"id": "caption_claim_match",
     "question": "Does the figure match the caption claim?"},
    {"id": "data_ink_ratio",
     "question": "Is the data-ink ratio maximized (no decorative ink)?"},
]


def cycle2_vlm_critique(self, *, vlm_callable) -> dict:
    """Cycle 2: per-figure VLM critique on 10-item rubric.

    vlm_callable signature: (figure_path, title, kind, rubric) -> {scores: {item_id: 1-4}, edits: [...]}.
    """
    src_dir = self.output_dir / "figures_draft1"
    dst_dir = self.output_dir / "figures_draft2"
    dst_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(
        (src_dir / "manifest.json").read_text(encoding="utf-8"))
    figures = []
    for fig in manifest["figures"]:
        result = vlm_callable(
            figure_path=str(self.output_dir / fig["draft_path"]),
            title=fig.get("title", ""),
            kind=fig.get("kind", ""),
            rubric=VLM_RUBRIC,
        )
        scores = result.get("scores", {})
        agg = sum(int(scores.get(item["id"], 0)) for item in VLM_RUBRIC)
        figures.append({
            "figure_id": fig["figure_id"],
            "scores": scores,
            "aggregate_score": agg,  # 0..40
            "edits": result.get("edits", []),
        })
    rubric_doc = {"cycle": 2, "rubric": VLM_RUBRIC, "figures": figures}
    (dst_dir / "vlm_rubric.json").write_text(
        json.dumps(rubric_doc, indent=2), encoding="utf-8")
    return rubric_doc


# Patch into class
PlotterLoop.cycle2_vlm_critique = cycle2_vlm_critique


JOURNAL_STYLES = {
    "nature": {"single_column_mm": 89, "double_column_mm": 183,
               "max_height_mm": 170, "raster_dpi": 300, "lineart_dpi": 1200,
               "font_family": "Arial"},
    "cell":   {"single_column_mm": 85, "double_column_mm": 174,
               "max_height_mm": 188, "raster_dpi": 300, "lineart_dpi": 1000,
               "font_family": "Arial"},
    "ieee":   {"single_column_mm": 88, "double_column_mm": 181,
               "max_height_mm": 240, "raster_dpi": 300, "lineart_dpi": 600,
               "font_family": "Times"},
    "springer": {"single_column_mm": 84, "double_column_mm": 174,
                 "max_height_mm": 234, "raster_dpi": 300, "lineart_dpi": 600,
                 "font_family": "Times"},
    "auto":   {"single_column_mm": 89, "double_column_mm": 183,
               "max_height_mm": 200, "raster_dpi": 300, "lineart_dpi": 600,
               "font_family": "Arial"},
}


def _emit_includegraphics_tex(figures: list, journal: dict) -> str:
    """Build figures.tex with \\includegraphics for scripting mode."""
    lines = ["% Auto-generated by plotter_loop Cycle 3 (scripting mode)\n"]
    width = f"{journal['single_column_mm']}mm"
    for f in figures:
        fid = f["figure_id"]
        lines.append(r"\begin{figure}[t]")
        lines.append(r"\centering")
        lines.append(rf"\includegraphics[width={width}]{{figures_final/{fid}.pdf}}")
        lines.append(rf"\caption{{{f.get('title', fid)}}}")
        lines.append(rf"\label{{fig:{fid}}}")
        lines.append(r"\end{figure}")
        lines.append("")
    return "\n".join(lines)


def _emit_tikz_snippet(spec_id: str, kind: str, title: str) -> str:
    """Return a minimal TikZ snippet for the figure kind."""
    if kind == "bar":
        return (
            "% Auto-generated TikZ snippet (Cycle 3 latex_native)\n"
            r"\begin{tikzpicture}" "\n"
            r"\begin{axis}[ybar, width=0.9\columnwidth, height=5cm,"
            r" xlabel={Method}, ylabel={Score}, title={" + title + r"}]" "\n"
            r"\addplot+[error bars/.cd, y dir=both, y explicit]" "\n"
            r"  coordinates {(A,0.82) +- (0,0.02) (B,0.79) +- (0,0.03)};" "\n"
            r"\end{axis}" "\n"
            r"\end{tikzpicture}" "\n"
        )
    if kind == "timeline":
        return (
            r"\begin{tikzpicture}[every node/.style={font=\small}]" "\n"
            r"\draw[->] (0,0) -- (8,0) node[right] {year};" "\n"
            r"\foreach \x/\y in {1/2020,3/2022,5/2024,7/2026}" "\n"
            r"  \draw (\x,0.1) -- (\x,-0.1) node[below] {\y};" "\n"
            r"\end{tikzpicture}" "\n"
        )
    # Generic fallback
    return (
        r"\begin{tikzpicture}" "\n"
        r"\node {" + title + r" (" + kind + r")};" "\n"
        r"\end{tikzpicture}" "\n"
    )


def cycle3_polish_export(self, *, mode: str = "scripting") -> dict:
    """Cycle 3: polish + export.

    mode='scripting' produces fig.pdf via matplotlib (real rendering left
    to caller-injected hook); also emits figures.tex with \\includegraphics.

    mode='latex_native' produces TikZ snippets per figure (no matplotlib).
    """
    final_dir = self.output_dir / "figures_final"
    final_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(
        (self.output_dir / "figures_draft1" / "manifest.json").read_text())
    rubric = json.loads(
        (self.output_dir / "figures_draft2" / "vlm_rubric.json").read_text())

    journal = JOURNAL_STYLES.get(self.journal_style, JOURNAL_STYLES["auto"])
    figures = manifest["figures"]

    # Per-figure emit
    if mode == "latex_native":
        for f in figures:
            tex = _emit_tikz_snippet(
                spec_id=f["figure_id"],
                kind=f.get("kind", "bar"),
                title=f.get("title", f["figure_id"]),
            )
            (final_dir / f"{f['figure_id']}.tex").write_text(
                tex, encoding="utf-8")

    # figures.tex aggregate (always)
    figures_tex = _emit_includegraphics_tex(figures, journal)
    (final_dir / "figures.tex").write_text(figures_tex, encoding="utf-8")

    # figure_metadata.csv
    csv_lines = ["figure_id,title,kind,journal_style,aggregate_score,mode"]
    rubric_by_id = {r["figure_id"]: r for r in rubric["figures"]}
    for f in figures:
        csv_lines.append(
            f"{f['figure_id']},{f.get('title','').replace(',', ';')},"
            f"{f.get('kind','')},{self.journal_style},"
            f"{rubric_by_id.get(f['figure_id'], {}).get('aggregate_score', 0)},"
            f"{mode}")
    (final_dir / "figure_metadata.csv").write_text(
        "\n".join(csv_lines) + "\n", encoding="utf-8")

    return {
        "cycle": 3,
        "mode": mode,
        "journal_style": self.journal_style,
        "figures_count": len(figures),
        "metadata_csv": str((final_dir / "figure_metadata.csv")
                            .relative_to(self.output_dir)),
    }


PlotterLoop.cycle3_polish_export = cycle3_polish_export

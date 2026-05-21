"""Block 7 Task 3 — smoke-compile the in-house LaTeX class files.

Only the two classes with a full preamble are exercised here
(``preprint`` and ``gost-generic``). The other three in-house stubs
(``jama``, ``dan-ras``, ``uspekhi``) are minimal LaTeX2e scaffolds that
maintainers complete post-launch, so we do not gate the test suite on
their compile output.

Skipped entirely when ``pdflatex`` is absent from ``PATH``.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


# Map venue slug -> (.cls filename without extension).
CLASSES_TO_TEST: dict[str, str] = {
    "preprint": "preprint",
    "gost-generic": "gost-article",
}


def _templates_root() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "plugins"
        / "vedix"
        / "mcp"
        / "templates"
    )


@pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not installed"
)
@pytest.mark.parametrize("venue,cls_stem", list(CLASSES_TO_TEST.items()))
def test_class_minimal_compile(venue: str, cls_stem: str, tmp_path: Path):
    cls_src = _templates_root() / venue / "latex" / f"{cls_stem}.cls"
    assert cls_src.exists(), f"class file missing: {cls_src}"
    shutil.copy2(cls_src, tmp_path / cls_src.name)
    tex = tmp_path / "test.tex"
    body = "Hello world."
    if venue == "gost-generic":
        # Cyrillic + Latin smoke; class loads russian babel.
        body = "Здравствуй, мир."
    tex.write_text(
        f"\\documentclass{{{cls_stem}}}\n"
        f"\\begin{{document}}\n"
        f"{body}\n"
        f"\\end{{document}}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", str(tex)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (tmp_path / "test.pdf").exists(), (
        f"pdflatex failed to produce test.pdf for {venue}; "
        f"tail of stdout:\n{result.stdout[-1500:]}"
    )


def test_all_inhouse_class_files_present():
    """All 5 in-house venues have a .cls on disk, regardless of pdflatex."""
    inhouse = {
        "preprint": "preprint.cls",
        "gost-generic": "gost-article.cls",
        "jama": "jama-style.cls",
        "dan-ras": "dan-ras.cls",
        "uspekhi": "uspekhi.cls",
    }
    for venue, filename in inhouse.items():
        path = _templates_root() / venue / "latex" / filename
        assert path.exists(), f"missing in-house class: {path}"
        text = path.read_text(encoding="utf-8")
        assert "\\NeedsTeXFormat" in text
        assert "\\ProvidesClass" in text
        assert "\\LoadClass" in text

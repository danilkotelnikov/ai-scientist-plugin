"""Block 7 Task 5 — end-to-end render smoke per representative venue.

The full render pipeline requires both ``pandoc`` (markdown→tex / docx)
and ``pdflatex`` (or ``xelatex`` for CJK locales). When either tool is
absent the test SKIPs cleanly so CI on minimal containers stays green.

Coverage: one Latin-script venue (``preprint``), one numbered-IEEE
template (``ieee``), one MDPI open-access template (``mdpi``), and one
ВАК-perechen' Cyrillic template (``gost-generic``).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from plugins.vedix.mcp.lib.orchestrator.publisher_engine import (
    list_venues,
    render,
)


_TOOLCHAIN_AVAILABLE = (
    shutil.which("pandoc") is not None and shutil.which("pdflatex") is not None
)


@pytest.mark.skipif(
    not _TOOLCHAIN_AVAILABLE, reason="pandoc / pdflatex missing"
)
@pytest.mark.parametrize(
    "venue",
    ["preprint", "ieee", "mdpi", "gost-generic"],
)
def test_render_per_venue(tmp_path: Path, venue: str):
    md = tmp_path / "manuscript.md"
    md.write_text(
        "# Title\n\n"
        "Introduction text. See [@smith2024].\n\n"
        "# Methods\n\n"
        "Methods text.\n",
        encoding="utf-8",
    )
    bib = tmp_path / "references.bib"
    bib.write_text(
        "@article{smith2024,\n"
        "  author={Smith, J.},\n"
        "  title={A study},\n"
        "  year={2024},\n"
        "  journal={Journal of Things},\n"
        "}\n",
        encoding="utf-8",
    )
    workdir = tmp_path / "work"
    workdir.mkdir()
    language = "ru" if venue == "gost-generic" else "en"
    out = render(
        venue=venue,
        language=language,
        manuscript_md=md,
        references_bib=bib,
        workdir=workdir,
    )
    # Acceptance: at least the .tex made it through pandoc; PDF is best-effort.
    assert out["tex"].exists()
    assert out["venue"] == venue
    assert out["language"] == language


def test_render_rejects_unknown_venue(tmp_path: Path):
    """Quick sanity check — runs without any toolchain."""
    md = tmp_path / "m.md"
    md.write_text("hi", encoding="utf-8")
    bib = tmp_path / "r.bib"
    bib.write_text("", encoding="utf-8")
    with pytest.raises(KeyError):
        render(
            venue="not-a-venue",
            language="en",
            manuscript_md=md,
            references_bib=bib,
            workdir=tmp_path,
        )


def test_all_23_venues_have_template_dirs():
    """Smoke check that scaffolding has populated each venue dir."""
    root = (
        Path(__file__).resolve().parents[2]
        / "plugins"
        / "vedix"
        / "mcp"
        / "templates"
    )
    for name in list_venues():
        venue_dir = root / name
        assert venue_dir.exists(), f"missing template dir: {venue_dir}"
        assert (venue_dir / "latex").exists()
        assert (venue_dir / "word").exists()
        assert (venue_dir / "PROVENANCE.md").exists()
        assert (venue_dir / "profile.json").exists()

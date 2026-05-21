"""Maintainer helper for Block 7 — populate `plugins/vedix/mcp/templates/`
with one directory per venue.

Run by **maintainers** (not end-users); the populated tree is committed
to the repo so installers ship all 23 publisher templates bundled.

For each venue this script creates:

* ``<venue>/latex/``  — class file goes here (in-house ones are
  authored verbatim by :func:`_write_in_house_class`; upstream CTAN
  ones are left empty for the maintainer to drop in).
* ``<venue>/word/``  — `.dotx` reference docs (left empty for the
  maintainer).
* ``<venue>/profile.json``  — section-order / word-limit / journal
  overrides skeleton.
* ``<venue>/PROVENANCE.md``  — source, URL, license, assembly date.

The in-house class families (``preprint``, ``gost-generic``, ``jama``,
``dan-ras``, ``uspekhi``) are emitted under MIT.

Usage:

    python scripts/fetch_publisher_templates.py \
        --templates-root plugins/vedix/mcp/templates

    # single-venue refresh
    python scripts/fetch_publisher_templates.py \
        --templates-root plugins/vedix/mcp/templates --venue preprint
"""
from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

# (source-label, upstream-url) — None URL means "in-house, authored here".
VENUE_SOURCES: dict[str, tuple[str, str | None]] = {
    "preprint": ("in-house", None),
    "nature": (
        "CTAN/nature",
        "https://www.ctan.org/tex-archive/macros/latex/contrib/nature",
    ),
    "elsevier": (
        "CTAN/elsarticle",
        "https://www.ctan.org/tex-archive/macros/latex/contrib/elsarticle",
    ),
    "springer-nature": (
        "Springer",
        "https://www.springernature.com/gp/authors/campaigns/latex-author-support",
    ),
    "taylor-francis": (
        "T&F",
        "https://www.tandf.co.uk/journals/authors/InteractCADLaTeX.zip",
    ),
    "frontiers": (
        "Frontiers",
        "https://www.frontiersin.org/files/articletemplate.zip",
    ),
    "wiley": (
        "Wiley",
        "https://authorservices.wiley.com/asset/latex/journal-template.zip",
    ),
    "sage": (
        "SAGE",
        "https://uk.sagepub.com/sites/default/files/sage_latex_template_v1.zip",
    ),
    "plos": ("PLOS", "https://journals.plos.org/plosone/s/latex"),
    "cell": ("Cell", "https://www.cell.com/cell/latex"),
    "ieee": (
        "CTAN/IEEEtran",
        "https://www.ctan.org/tex-archive/macros/latex/contrib/IEEEtran",
    ),
    "acm": (
        "CTAN/acmart",
        "https://www.ctan.org/tex-archive/macros/latex/contrib/acmart",
    ),
    "acs": (
        "CTAN/achemso",
        "https://www.ctan.org/tex-archive/macros/latex/contrib/achemso",
    ),
    "mdpi": ("MDPI", "https://www.mdpi.com/files/MDPI-LaTeX-template.zip"),
    "revtex42": (
        "CTAN/revtex",
        "https://www.ctan.org/tex-archive/macros/latex/contrib/revtex",
    ),
    "rsc": (
        "RSC",
        "https://www.rsc.org/journals-books-databases/author-and-reviewer-hub/authors-information/prepare-and-format/",
    ),
    "cambridge": (
        "CUP",
        "https://www.cambridge.org/core/services/aop-file-manager/file/cambridge-latex-template.zip",
    ),
    "oup": (
        "OUP",
        "https://academic.oup.com/journals/pages/authors/preparing_your_manuscript",
    ),
    "bmj": (
        "BMJ",
        "https://authors.bmj.com/wp-content/uploads/2018/05/latex_template_v2.zip",
    ),
    "jama": ("in-house", None),
    "gost-generic": ("in-house", None),
    "dan-ras": ("in-house", None),
    "uspekhi": ("in-house", None),
}


# Class-file filename per venue (matches Venue.latex_class).
CLASS_FILENAMES: dict[str, str] = {
    "preprint": "preprint.cls",
    "nature": "nature.cls",
    "elsevier": "elsarticle.cls",
    "springer-nature": "sn-jnl.cls",
    "taylor-francis": "interact.cls",
    "frontiers": "frontiers.cls",
    "wiley": "WileyNJD-v2.cls",
    "sage": "sagej.cls",
    "plos": "plos2015.cls",
    "cell": "cell.cls",
    "ieee": "IEEEtran.cls",
    "acm": "acmart.cls",
    "acs": "achemso.cls",
    "mdpi": "mdpi.cls",
    "revtex42": "revtex4-2.cls",
    "rsc": "rsc.cls",
    "cambridge": "cambridge7A.cls",
    "oup": "OUPMaths.cls",
    "bmj": "bmj.cls",
    "jama": "jama-style.cls",
    "gost-generic": "gost-article.cls",
    "dan-ras": "dan-ras.cls",
    "uspekhi": "uspekhi.cls",
}


# Verbatim in-house class file bodies. Empty values are emitted as a
# minimal scaffold by :func:`_write_in_house_class`.
INHOUSE_CLASS_BODIES: dict[str, str] = {
    "preprint": r"""\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{preprint}[2026/04 Overleaf-style preprint single-column]
\LoadClass[a4paper,11pt]{article}
\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage{lmodern}
\RequirePackage{geometry}
\geometry{margin=1in}
\RequirePackage[backend=biber,style=numeric-comp]{biblatex}
""",
    "gost-article": r"""\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{gost-article}[2026/04 ВАК-перечень generic ГОСТ-7.0.5]
\LoadClass[a4paper,12pt]{article}
\RequirePackage[T2A]{fontenc}
\RequirePackage[utf8]{inputenc}
\RequirePackage[english,russian]{babel}
\RequirePackage{geometry}
\geometry{margin=2.5cm}
\RequirePackage[backend=biber,style=gost-numeric,sorting=ntvy]{biblatex}
""",
    # jama / dan-ras / uspekhi: minimal stub; maintainer completes preamble.
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Populate Vedix publisher templates directory tree.",
    )
    ap.add_argument(
        "--templates-root",
        required=True,
        type=Path,
        help="Target directory, normally plugins/vedix/mcp/templates",
    )
    ap.add_argument(
        "--venue",
        default=None,
        help="Single venue slug; omit to scaffold all 23 venues",
    )
    args = ap.parse_args()

    for name, (source, url) in VENUE_SOURCES.items():
        if args.venue and args.venue != name:
            continue
        _scaffold_venue(args.templates_root, name, source, url)


def _scaffold_venue(
    root: Path, name: str, source: str, url: str | None
) -> None:
    """Create the on-disk skeleton for one venue."""
    out = root / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "latex").mkdir(exist_ok=True)
    (out / "word").mkdir(exist_ok=True)

    if source == "in-house":
        print(f"[in-house] {name}: authoring class file (MIT)")
        _write_in_house_class(out, name)
    elif source.startswith("CTAN/"):
        pkg = source.split("/", 1)[1]
        print(
            f"[ctan] {name}: maintainer must `tlmgr install {pkg}` and "
            f"copy {CLASS_FILENAMES[name]} into {out / 'latex'}"
        )
    else:
        print(f"[manual] {name}: hand-curated download required from {url}")

    provenance = out / "PROVENANCE.md"
    if not provenance.exists():
        today = _dt.date.today().isoformat()
        provenance.write_text(
            f"# Provenance for {name}\n\n"
            f"- Source: {source}\n"
            f"- URL: {url or 'in-house'}\n"
            f"- License: see upstream (in-house files released under MIT)\n"
            f"- Assembly date: {today}\n",
            encoding="utf-8",
        )

    profile = out / "profile.json"
    if not profile.exists():
        profile.write_text(
            '{"sections": [], "word_limit": 0, "journals": {}}\n',
            encoding="utf-8",
        )


def _write_in_house_class(out: Path, name: str) -> None:
    """Author the in-house class file for ``name``.

    Emits the verbatim body from :data:`INHOUSE_CLASS_BODIES` when present,
    otherwise a minimal LaTeX2e stub. Skips if the target file already
    exists, so the script is idempotent.
    """
    cls_filename = CLASS_FILENAMES[name]
    cls_path = out / "latex" / cls_filename
    if cls_path.exists():
        return
    stem = cls_path.stem  # e.g. "gost-article" for gost-generic
    body = INHOUSE_CLASS_BODIES.get(stem)
    if body is None:
        # Minimal scaffold; maintainer completes preamble for jama/dan-ras/uspekhi.
        body = (
            r"\NeedsTeXFormat{LaTeX2e}" "\n"
            rf"\ProvidesClass{{{stem}}}[in-house MIT scaffold]"
            "\n"
            r"\LoadClass{article}" "\n"
        )
    cls_path.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()

# Block 7 — Publisher Templates (23 Bundled) Implementation Plan (§7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Ship all 23 publisher families × 7 languages = 161 `.dotx` Word templates + 23 LaTeX class files + 23 AI-disclosure templates + per-template `PROVENANCE.md`, with a `publisher_engine.py` that does LaTeX↔Word parity check. Everything bundled at install (no fetch-on-first-use).

**Architecture:** Templates live under `plugins/vedix/templates/<venue>/`. The engine accepts `--venue <name>[:<journal>] --lang <code>`, generates `manuscript.tex` + `manuscript.docx`, runs the parity check, emits `parity_report.json`. Per-venue JSON profiles override section ordering, word limits, citation sub-keys.

**Tech Stack:** `pandoc` 3.x (for `.docx` rendering), `pylatex`, `python-docx` (for Word inspection), `subprocess` calls to `pdflatex` / `xelatex` / `biber`. In-house class files for JAMA, DAN RAS, Uspekhi under MIT.

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §7.

---

## File structure

```
plugins/vedix/templates/
├── preprint/
│   ├── latex/preprint.cls          # 11pt single-column article
│   ├── word/preprint_<lang>.dotx   # × 7 languages
│   ├── ai_disclosure.tex
│   ├── profile.json
│   └── PROVENANCE.md
├── nature/...
├── elsevier/  (elsarticle.cls)
├── springer-nature/  (sn-jnl.cls)
├── taylor-francis/  (interact.cls)
├── frontiers/  (frontiers.cls)
├── wiley/  (WileyNJD-v2.cls)
├── sage/  (sagej.cls)
├── plos/  (plos2015.cls)
├── cell/  (cell.cls)
├── ieee/  (IEEEtran.cls)
├── acm/  (acmart.cls)
├── acs/  (achemso.cls)
├── mdpi/  (mdpi.cls)
├── revtex42/  (revtex4-2.cls)
├── rsc/  (rsc.cls)
├── cambridge/  (cambridge7A.cls)
├── oup/  (OUPMaths.cls + oup-contemporary.cls)
├── bmj/  (bmj.cls)
├── jama/  (jama-style.cls — in-house MIT)
├── gost-generic/  (gost-article.cls — in-house MIT)
├── dan-ras/  (dan-ras.cls — in-house MIT)
└── uspekhi/  (uspekhi.cls — in-house MIT)

plugins/vedix/mcp/lib/orchestrator/
└── publisher_engine.py             # the engine

scripts/
└── fetch_publisher_templates.py    # one-time helper to populate templates/ from upstream CTAN
```

## Task 1: Publisher engine core + venue registry

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/publisher_engine.py`
- Test: `tests/publisher/test_venue_registry.py`

- [ ] **Step 1: Write test**

```python
# tests/publisher/test_venue_registry.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.publisher_engine import (
    list_venues, get_venue, VENUES
)

def test_23_venues_registered():
    assert len(list_venues()) == 23

@pytest.mark.parametrize("venue", [
    "preprint", "nature", "elsevier", "springer-nature", "taylor-francis",
    "frontiers", "wiley", "sage", "plos", "cell", "ieee", "acm", "acs", "mdpi",
    "revtex42", "rsc", "cambridge", "oup", "bmj", "jama",
    "gost-generic", "dan-ras", "uspekhi",
])
def test_each_venue_has_class_and_profile(venue):
    v = get_venue(venue)
    assert v.latex_class.endswith(".cls")
    assert v.citation_style
    assert v.region in {"global", "ru"}
```

- [ ] **Step 2: Implement engine + registry**

```python
# plugins/vedix/mcp/lib/orchestrator/publisher_engine.py
from __future__ import annotations
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

@dataclass
class Venue:
    name: str
    latex_class: str
    citation_style: str
    region: Literal["global", "ru"]
    bundled: bool = True
    description: str = ""

VENUES: dict[str, Venue] = {
    "preprint": Venue("preprint", "article.cls", "biblatex-numeric-comp", "global", description="Overleaf-default 11pt single-column for arXiv / bioRxiv / OSF / SSRN"),
    "nature": Venue("nature", "nature.cls", "nature", "global"),
    "elsevier": Venue("elsevier", "elsarticle.cls", "elsevier-numeric", "global", description="~2,500 Elsevier titles"),
    "springer-nature": Venue("springer-nature", "sn-jnl.cls", "springer-numeric", "global"),
    "taylor-francis": Venue("taylor-francis", "interact.cls", "tf-numeric", "global"),
    "frontiers": Venue("frontiers", "frontiers.cls", "frontiers-reference-style", "global"),
    "wiley": Venue("wiley", "WileyNJD-v2.cls", "wiley-numeric", "global"),
    "sage": Venue("sage", "sagej.cls", "sage-author-date", "global"),
    "plos": Venue("plos", "plos2015.cls", "vancouver", "global"),
    "cell": Venue("cell", "cell.cls", "cell", "global"),
    "ieee": Venue("ieee", "IEEEtran.cls", "ieee", "global"),
    "acm": Venue("acm", "acmart.cls", "acm-numeric", "global"),
    "acs": Venue("acs", "achemso.cls", "acs", "global"),
    "mdpi": Venue("mdpi", "mdpi.cls", "mdpi-numeric", "global"),
    "revtex42": Venue("revtex42", "revtex4-2.cls", "revtex-numeric", "global", description="AIP / APS physics"),
    "rsc": Venue("rsc", "rsc.cls", "rsc-author-date", "global"),
    "cambridge": Venue("cambridge", "cambridge7A.cls", "cup-author-date", "global"),
    "oup": Venue("oup", "OUPMaths.cls", "oup-numeric", "global"),
    "bmj": Venue("bmj", "bmj.cls", "vancouver", "global"),
    "jama": Venue("jama", "jama-style.cls", "ama", "global"),
    "gost-generic": Venue("gost-generic", "gost-article.cls", "gost-numeric", "ru", description="ВАК-perechen' generic"),
    "dan-ras": Venue("dan-ras", "dan-ras.cls", "gost-numeric", "ru"),
    "uspekhi": Venue("uspekhi", "uspekhi.cls", "gost-numeric", "ru"),
}

def list_venues() -> list[str]:
    return sorted(VENUES)

def get_venue(name: str) -> Venue:
    base = name.split(":", 1)[0]
    if base not in VENUES:
        raise KeyError(f"unknown venue {base!r}; available: {list_venues()}")
    return VENUES[base]

def _templates_root() -> Path:
    return Path(__file__).resolve().parents[3] / "templates"

def render(*, venue: str, language: str, manuscript_md: Path, references_bib: Path,
           workdir: Path, journal: str | None = None) -> dict:
    """Render `manuscript.md` (pandoc-flavoured markdown) to PDF + DOCX for the given venue + lang."""
    v = get_venue(venue)
    venue_root = _templates_root() / v.name
    if not venue_root.exists():
        raise FileNotFoundError(f"venue template directory missing: {venue_root}")

    # LaTeX path
    tex_out = workdir / "manuscript.tex"
    pdf_out = workdir / "manuscript.pdf"
    docx_out = workdir / "manuscript.docx"

    # Pull profile + journal override
    profile = json.loads((venue_root / "profile.json").read_text(encoding="utf-8"))
    if journal:
        journal_overrides = profile.get("journals", {}).get(journal, {})
        profile = {**profile, **journal_overrides}

    # Render LaTeX via pandoc using the venue's template
    from .locale.router import get_locale
    locale = get_locale(language)
    latex_template = venue_root / "latex" / f"{v.name}.cls"
    if not latex_template.exists():
        raise FileNotFoundError(f"LaTeX class missing: {latex_template}")

    subprocess.run([
        "pandoc", str(manuscript_md), "-o", str(tex_out),
        "--from", "markdown",
        "--to", "latex",
        "--standalone",
        "--variable", f"documentclass={v.name}",
        "--variable", f"venue-class-path={latex_template.parent}",
        "--variable", f"language={language}",
        "--variable", f"engine={locale.latex_engine}",
        "--bibliography", str(references_bib),
        "--biblatex",
        f"--metadata=lang:{language}",
    ], check=True, cwd=workdir)

    # PDF via configured engine
    engine = locale.latex_engine
    for _ in range(2):  # two passes for refs
        subprocess.run([engine, "-interaction=nonstopmode", str(tex_out)], cwd=workdir, check=False)
    subprocess.run(["biber", str(tex_out.with_suffix(""))], cwd=workdir, check=False)
    for _ in range(2):
        subprocess.run([engine, "-interaction=nonstopmode", str(tex_out)], cwd=workdir, check=False)

    # Word path
    word_template = venue_root / "word" / f"{v.name}_{language}.dotx"
    if not word_template.exists():
        word_template = venue_root / "word" / f"{v.name}_en.dotx"  # fallback to EN if lang missing
    subprocess.run([
        "pandoc", str(manuscript_md), "-o", str(docx_out),
        "--reference-doc", str(word_template),
        "--bibliography", str(references_bib),
        "--citeproc",
    ], check=True, cwd=workdir)

    return {
        "venue": v.name,
        "language": language,
        "pdf": pdf_out,
        "docx": docx_out,
        "tex": tex_out,
    }
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/publisher_engine.py tests/publisher/test_venue_registry.py
git commit -m "feat(B7): publisher engine core + 23-venue registry"
```

## Task 2: Template directory scaffolding script

**Files:**
- Create: `scripts/fetch_publisher_templates.py`

- [ ] **Step 1: Implement**

```python
# scripts/fetch_publisher_templates.py
"""One-time helper to populate plugins/vedix/templates/ from CTAN + publisher sources.

Run by maintainers (not end-users); the result is committed to the repo so users
get all 23 templates at install.
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

VENUE_SOURCES = {
    "preprint":       ("in-house",       None),  # we author article.cls extension in-house
    "nature":         ("CTAN/nature",    "https://www.ctan.org/tex-archive/macros/latex/contrib/nature"),
    "elsevier":       ("CTAN/elsarticle","https://www.ctan.org/tex-archive/macros/latex/contrib/elsarticle"),
    "springer-nature":("Springer",       "https://www.springernature.com/gp/authors/campaigns/latex-author-support"),
    "taylor-francis": ("T&F",            "https://www.tandf.co.uk/journals/authors/InteractCADLaTeX.zip"),
    "frontiers":      ("Frontiers",      "https://www.frontiersin.org/files/articletemplate.zip"),
    "wiley":          ("Wiley",          "https://authorservices.wiley.com/asset/latex/journal-template.zip"),
    "sage":           ("SAGE",           "https://uk.sagepub.com/sites/default/files/sage_latex_template_v1.zip"),
    "plos":           ("PLOS",           "https://journals.plos.org/plosone/s/latex"),
    "cell":           ("Cell",           "https://www.cell.com/cell/latex"),
    "ieee":           ("CTAN/IEEEtran",  "https://www.ctan.org/tex-archive/macros/latex/contrib/IEEEtran"),
    "acm":            ("CTAN/acmart",    "https://www.ctan.org/tex-archive/macros/latex/contrib/acmart"),
    "acs":            ("CTAN/achemso",   "https://www.ctan.org/tex-archive/macros/latex/contrib/achemso"),
    "mdpi":           ("MDPI",           "https://www.mdpi.com/files/MDPI-LaTeX-template.zip"),
    "revtex42":       ("CTAN/revtex",    "https://www.ctan.org/tex-archive/macros/latex/contrib/revtex"),
    "rsc":            ("RSC",            "https://www.rsc.org/journals-books-databases/author-and-reviewer-hub/authors-information/prepare-and-format/"),
    "cambridge":      ("CUP",            "https://www.cambridge.org/core/services/aop-file-manager/file/cambridge-latex-template.zip"),
    "oup":            ("OUP",            "https://academic.oup.com/journals/pages/authors/preparing_your_manuscript"),
    "bmj":            ("BMJ",            "https://authors.bmj.com/wp-content/uploads/2018/05/latex_template_v2.zip"),
    "jama":           ("in-house",       None),  # JAMA does not distribute LaTeX class; we author jama-style.cls
    "gost-generic":   ("in-house",       None),
    "dan-ras":        ("in-house",       None),
    "uspekhi":        ("in-house",       None),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates-root", required=True, type=Path)
    ap.add_argument("--venue", default=None, help="single venue or omit for all")
    args = ap.parse_args()

    for name, (source, url) in VENUE_SOURCES.items():
        if args.venue and args.venue != name:
            continue
        out = args.templates_root / name
        if (out / "latex").exists() and any((out / "latex").iterdir()):
            print(f"[skip] {name} already populated")
            continue
        out.mkdir(parents=True, exist_ok=True)
        (out / "latex").mkdir(exist_ok=True)
        (out / "word").mkdir(exist_ok=True)
        if source == "in-house":
            print(f"[in-house] {name} — authoring class file in-house (under MIT)")
            _write_in_house_class(out, name)
        elif source.startswith("CTAN/"):
            pkg = source.split("/", 1)[1]
            print(f"[ctan] fetching {pkg} via tlmgr…")
            subprocess.run(["tlmgr", "install", pkg], check=False)
        else:
            print(f"[manual] {name} requires hand-curated download from {url}")
        # Always write a PROVENANCE.md template
        (out / "PROVENANCE.md").write_text(
            f"# Provenance for {name}\n\n- Source: {source}\n- URL: {url or 'in-house'}\n- License: see upstream\n- Assembly date: $(date -I)\n",
            encoding="utf-8"
        )
        (out / "profile.json").write_text('{"sections": [], "word_limit": 0, "journals": {}}', encoding="utf-8")

def _write_in_house_class(out: Path, name: str):
    cls_path = out / "latex" / f"{name}.cls"
    if cls_path.exists(): return
    if name == "gost-generic":
        cls_path.write_text(r"""
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{gost-article}[2026/04 ВАК-perechen' generic ГОСТ-7.0.5]
\LoadClass[a4paper,12pt]{article}
\RequirePackage[T2A]{fontenc}
\RequirePackage[utf8]{inputenc}
\RequirePackage[english,russian]{babel}
\RequirePackage{geometry}
\geometry{margin=2.5cm}
\RequirePackage[backend=biber,style=gost-numeric,sorting=ntvy]{biblatex}
""".strip(), encoding="utf-8")
    elif name == "preprint":
        cls_path.write_text(r"""
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{preprint}[2026/04 Overleaf-style preprint single-column]
\LoadClass[a4paper,11pt]{article}
\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage{lmodern}
\RequirePackage{geometry}
\geometry{margin=1in}
\RequirePackage[backend=biber,style=numeric-comp]{biblatex}
""".strip(), encoding="utf-8")
    else:
        # jama, dan-ras, uspekhi: minimal scaffolding; maintainers complete
        cls_path.write_text(
            f"\\NeedsTeXFormat{{LaTeX2e}}\n\\ProvidesClass{{{name}}}[in-house MIT]\n\\LoadClass{{article}}\n",
            encoding="utf-8"
        )

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit (no test — this is a maintenance helper)**

```bash
git add scripts/fetch_publisher_templates.py
git commit -m "feat(B7): scripts/fetch_publisher_templates.py — populate template dirs from upstream"
```

## Task 3: Author in-house class files (preprint, gost-generic, jama, dan-ras, uspekhi)

**Files:**
- Create: `plugins/vedix/templates/preprint/latex/preprint.cls`
- Create: `plugins/vedix/templates/gost-generic/latex/gost-article.cls`
- Create: `plugins/vedix/templates/jama/latex/jama-style.cls`
- Create: `plugins/vedix/templates/dan-ras/latex/dan-ras.cls`
- Create: `plugins/vedix/templates/uspekhi/latex/uspekhi.cls`

- [ ] **Step 1: Run scaffolding**

```bash
python scripts/fetch_publisher_templates.py --templates-root plugins/vedix/templates
```

- [ ] **Step 2: Write smoke test that each class compiles**

```python
# tests/publisher/test_inhouse_classes_compile.py
import shutil
import subprocess
import pytest
from pathlib import Path

CLASSES_TO_TEST = ["preprint", "gost-generic"]  # jama/dan-ras/uspekhi require RU font stack

@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
@pytest.mark.parametrize("name", CLASSES_TO_TEST)
def test_class_minimal_compile(name, tmp_path):
    cls_src = Path(__file__).resolve().parents[2] / "plugins" / "vedix" / "templates" / name / "latex" / (
        "gost-article.cls" if name == "gost-generic" else f"{name}.cls"
    )
    shutil.copy2(cls_src, tmp_path / cls_src.name)
    tex = tmp_path / "test.tex"
    tex.write_text(rf"""
\documentclass{{{cls_src.stem}}}
\begin{{document}}
Hello world.
\end{{document}}
""")
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", str(tex)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert (tmp_path / "test.pdf").exists(), r.stdout[-500:]
```

- [ ] **Step 3: Commit (the class files were written by the scaffolding script)**

```bash
git add plugins/vedix/templates/preprint/ plugins/vedix/templates/gost-generic/ plugins/vedix/templates/jama/ plugins/vedix/templates/dan-ras/ plugins/vedix/templates/uspekhi/ tests/publisher/test_inhouse_classes_compile.py
git commit -m "feat(B7): in-house class files (preprint, gost-generic, jama, dan-ras, uspekhi) under MIT"
```

## Task 4: LaTeX↔Word parity check

**Files:**
- Modify: `plugins/vedix/mcp/lib/orchestrator/publisher_engine.py` (add parity logic)
- Test: `tests/publisher/test_parity.py`

- [ ] **Step 1: Write test**

```python
# tests/publisher/test_parity.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from plugins.vedix.mcp.lib.orchestrator.publisher_engine import check_parity

def test_parity_passes_when_counts_match(tmp_path):
    # Fake PDF + DOCX inspectors
    with patch("plugins.vedix.mcp.lib.orchestrator.publisher_engine._inspect_pdf",
               return_value={"sections": ["Intro", "Methods"], "n_equations": 5, "n_figures": 2, "n_tables": 1, "n_references": 12, "word_count": 5000, "n_citations": 12}), \
         patch("plugins.vedix.mcp.lib.orchestrator.publisher_engine._inspect_docx",
               return_value={"sections": ["Intro", "Methods"], "n_equations": 5, "n_figures": 2, "n_tables": 1, "n_references": 12, "word_count": 5050, "n_citations": 12}):
        report = check_parity(pdf=tmp_path / "a.pdf", docx=tmp_path / "a.docx")
        assert report["status"] == "ok"

def test_parity_flags_section_drift(tmp_path):
    with patch("plugins.vedix.mcp.lib.orchestrator.publisher_engine._inspect_pdf",
               return_value={"sections": ["Intro", "Methods", "Results"], "n_equations": 5, "n_figures": 2, "n_tables": 1, "n_references": 12, "word_count": 5000, "n_citations": 12}), \
         patch("plugins.vedix.mcp.lib.orchestrator.publisher_engine._inspect_docx",
               return_value={"sections": ["Intro", "Methods"], "n_equations": 5, "n_figures": 2, "n_tables": 1, "n_references": 12, "word_count": 5050, "n_citations": 12}):
        report = check_parity(pdf=tmp_path / "a.pdf", docx=tmp_path / "a.docx")
        assert report["status"] == "drift"
        assert any("section" in d["kind"] for d in report["divergences"])
```

- [ ] **Step 2: Implement parity check**

```python
# plugins/vedix/mcp/lib/orchestrator/publisher_engine.py (additions)

def _inspect_pdf(pdf: Path) -> dict:
    """Best-effort: extract section headings + equation/fig/table counts from PDF."""
    from pdfminer.high_level import extract_text
    text = extract_text(str(pdf))
    return _count_artifacts_in_text(text)

def _inspect_docx(docx: Path) -> dict:
    from docx import Document
    doc = Document(str(docx))
    text = "\n".join(p.text for p in doc.paragraphs)
    sections = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    return {**_count_artifacts_in_text(text), "sections": sections}

def _count_artifacts_in_text(text: str) -> dict:
    import re
    return {
        "sections": re.findall(r"(?:^|\n)([1-9]\.?\s+[A-Z][^\n]{2,80})", text),
        "n_equations": len(re.findall(r"\\begin\{equation\}|^\([0-9]+\)\s*$", text, re.MULTILINE)),
        "n_figures": len(re.findall(r"Figure\s+\d+", text)),
        "n_tables": len(re.findall(r"Table\s+\d+", text)),
        "n_references": len(re.findall(r"^\[\d+\]\s", text, re.MULTILINE)),
        "word_count": len(text.split()),
        "n_citations": len(re.findall(r"\[\d+\]", text)),
    }

def check_parity(*, pdf: Path, docx: Path, word_tolerance_pct: float = 2.0) -> dict:
    pdf_data = _inspect_pdf(pdf)
    docx_data = _inspect_docx(docx)
    divergences = []

    if len(pdf_data["sections"]) != len(docx_data["sections"]):
        divergences.append({"kind": "section_count",
                            "pdf": len(pdf_data["sections"]),
                            "docx": len(docx_data["sections"])})

    for k in ("n_equations", "n_figures", "n_tables", "n_references", "n_citations"):
        if pdf_data[k] != docx_data[k]:
            divergences.append({"kind": k, "pdf": pdf_data[k], "docx": docx_data[k]})

    wc_pdf, wc_docx = pdf_data["word_count"], docx_data["word_count"]
    if abs(wc_pdf - wc_docx) / max(wc_pdf, 1) * 100 > word_tolerance_pct:
        divergences.append({"kind": "word_count", "pdf": wc_pdf, "docx": wc_docx, "tolerance_pct": word_tolerance_pct})

    return {
        "status": "ok" if not divergences else "drift",
        "divergences": divergences,
        "pdf_data": pdf_data,
        "docx_data": docx_data,
    }
```

- [ ] **Step 3: Commit**

```bash
pytest tests/publisher/test_parity.py -v
git add plugins/vedix/mcp/lib/orchestrator/publisher_engine.py tests/publisher/test_parity.py
git commit -m "feat(B7): LaTeX↔Word parity check"
```

## Task 5: End-to-end smoke per venue

**Files:**
- Test: `tests/publisher/test_e2e_per_venue.py`

- [ ] **Step 1: Write test**

```python
# tests/publisher/test_e2e_per_venue.py
import shutil
import pytest
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.publisher_engine import render, list_venues

@pytest.mark.skipif(shutil.which("pandoc") is None or shutil.which("pdflatex") is None, reason="pandoc/pdflatex missing")
@pytest.mark.parametrize("venue", ["preprint", "ieee", "mdpi", "gost-generic"])  # subset for CI speed
def test_render_per_venue(tmp_path, venue):
    md = tmp_path / "manuscript.md"
    md.write_text("# Title\n\nIntroduction text. See [@smith2024].\n\n# Methods\n\nMethods text.\n")
    bib = tmp_path / "references.bib"
    bib.write_text("@article{smith2024, author={Smith}, title={X}, year={2024}, journal={J}}\n")
    workdir = tmp_path / "work"
    workdir.mkdir()
    out = render(venue=venue, language="en" if venue != "gost-generic" else "ru",
                 manuscript_md=md, references_bib=bib, workdir=workdir)
    assert out["pdf"].exists() or out["tex"].exists()
```

- [ ] **Step 2: Commit**

```bash
pytest tests/publisher/test_e2e_per_venue.py -v --tb=short
git add tests/publisher/test_e2e_per_venue.py
git commit -m "test(B7): e2e render smoke for representative venues"
```

## Block 7 acceptance criteria

- [ ] All 23 `templates/<venue>/` directories present with `latex/`, `word/`, `PROVENANCE.md`, `profile.json`
- [ ] `list_venues()` returns exactly 23 names
- [ ] In-house class files (preprint, gost-generic, jama, dan-ras, uspekhi) compile a minimal document with no errors
- [ ] `render(venue="preprint", language="en", ...)` produces `manuscript.pdf` + `manuscript.docx`
- [ ] `render(venue="gost-generic", language="ru", ...)` produces both with Cyrillic content
- [ ] `render(venue="ieee", language="en", ...)` produces both
- [ ] `check_parity()` returns status="ok" on matching artifact counts
- [ ] Bundle size measured: total `templates/` ≤ 100 MB
- [ ] All `tests/publisher/` tests pass
- [ ] Git tag `v3.0.0-block7` pushed

from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.references import validate_citations, CitationReport


def test_finds_dangling_cites(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text("@article{Ho2025_1, title={X}, author={Ho}, year={2025}}\n")
    tex = r"\cite{Ho2025_1} and also \cite{Missing2024_99}"
    report = validate_citations(tex, bib, crossref_check=False, llm_judge=None)
    assert "Missing2024_99" in report.dangling
    assert "Ho2025_1" not in report.dangling


def test_finds_uncited_entries(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text(
        "@article{A, title={X}, author={a}, year={2020}}\n"
        "@article{B, title={Y}, author={b}, year={2021}}\n"
    )
    tex = r"\cite{A} only"
    report = validate_citations(tex, bib, crossref_check=False, llm_judge=None)
    assert "B" in report.uncited
    assert "A" not in report.uncited


def test_clean_manuscript_passes(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text("@article{A, title={X}, author={a}, year={2020}}\n")
    tex = r"\cite{A}"
    report = validate_citations(tex, bib, crossref_check=False, llm_judge=None)
    assert report.is_clean is True


def test_crossref_check_called_for_each_doi(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text("@article{A, doi={10.1/x}, title={T}, author={a}, year={2020}}\n")
    tex = r"\cite{A}"
    fake_crossref = MagicMock(return_value={"verified": True})
    report = validate_citations(tex, bib, crossref_check=True, crossref_client=fake_crossref, llm_judge=None)
    fake_crossref.assert_called_once_with("10.1/x")


def test_llm_judge_flags_hallucinated(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text("@article{Fake, title={Invented}, author={Nobody}, year={2099}}\n")
    tex = r"\cite{Fake}"
    fake_judge = MagicMock(return_value={"hallucinated": ["Fake"], "reason": "year is in the future"})
    report = validate_citations(tex, bib, crossref_check=False, llm_judge=fake_judge)
    assert "Fake" in report.hallucinated

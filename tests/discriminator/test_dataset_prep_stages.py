"""Tests for §5.3.1 dataset preparation stages.

Each stage is implemented as a module under ``scripts/corpus_lib``; this
file mirrors the 10 stage modules with focused unit tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Make the bare ``corpus_lib`` package importable the way prepare_corpus.py
# imports it.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


# -- Stage 1: acquisition + checkpoint -------------------------------------- #


def test_checkpoint_skips_done_stages(tmp_path):
    from corpus_lib import checkpoint

    cp = checkpoint.StageCheckpoint(root=tmp_path)
    assert not cp.is_done("acquisition")
    cp.mark_done("acquisition")
    assert cp.is_done("acquisition")
    cp.reset("acquisition")
    assert not cp.is_done("acquisition")


@pytest.mark.asyncio
async def test_acquisition_returns_candidates(tmp_path):
    pytest.importorskip("corpus_lib.acquisition")
    from corpus_lib import acquisition

    fake_papers = [
        {
            "doi": "10.1/a",
            "title": "Catalysis",
            "year": 2023,
            "language": "en",
            "license": "cc-by",
            "full_text_url": "u1",
        },
        {
            "doi": "10.1/b",
            "title": "Synthesis",
            "year": 2024,
            "language": "en",
            "license": "cc-by",
            "full_text_url": "u2",
        },
    ]
    targets = (
        "corpus_lib.acquisition._call_openalex",
        "corpus_lib.acquisition._call_semanticscholar",
        "corpus_lib.acquisition._call_arxiv",
        "corpus_lib.acquisition._call_biorxiv",
        "corpus_lib.acquisition._call_pubmed",
        "corpus_lib.acquisition._call_annas",
    )
    with patch(targets[0], new=AsyncMock(return_value=fake_papers)), \
         patch(targets[1], new=AsyncMock(return_value=[])), \
         patch(targets[2], new=AsyncMock(return_value=[])), \
         patch(targets[3], new=AsyncMock(return_value=[])), \
         patch(targets[4], new=AsyncMock(return_value=[])), \
         patch(targets[5], new=AsyncMock(return_value=[])):
        out = tmp_path / "acquisition.jsonl"
        candidates = await acquisition.harvest(
            discipline="chemistry",
            language="en",
            target_count=2,
            out_path=out,
        )
        assert len(candidates) == 2
        assert out.exists()


@pytest.mark.asyncio
async def test_acquisition_rejects_wrong_license(tmp_path):
    from corpus_lib import acquisition

    fake_papers = [
        {"doi": "10.1/a", "title": "x", "language": "en", "license": "all-rights-reserved"},
    ]
    with patch("corpus_lib.acquisition._call_openalex", new=AsyncMock(return_value=fake_papers)), \
         patch("corpus_lib.acquisition._call_semanticscholar", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_arxiv", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_biorxiv", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_pubmed", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_annas", new=AsyncMock(return_value=[])):
        candidates = await acquisition.harvest(
            discipline="chemistry",
            language="en",
            target_count=5,
            out_path=tmp_path / "out.jsonl",
        )
        assert candidates == []


# -- Stage 2: download ------------------------------------------------------ #


@pytest.mark.asyncio
async def test_download_skips_existing(tmp_path):
    from corpus_lib import download

    dest = tmp_path / "out.pdf"
    dest.write_bytes(b"cached")
    # url is bogus; should be skipped because dest already exists.
    out = await download.download_one("http://no.such.host/x.pdf", dest)
    assert out == dest
    assert dest.read_bytes() == b"cached"


# -- Stage 3: extraction ---------------------------------------------------- #


def test_extraction_handles_pdf(tmp_path, monkeypatch):
    from corpus_lib import extraction

    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake")
    monkeypatch.setattr(
        extraction,
        "_pdf_to_text",
        lambda p: "Hello world. This is paragraph 1.\n\nThis is paragraph 2.",
    )
    out = extraction.extract(pdf, tmp_path / "p.txt")
    assert "Hello world" in out.read_text(encoding="utf-8")


def test_extraction_handles_html(tmp_path):
    pytest.importorskip("bs4")
    from corpus_lib import extraction

    html = tmp_path / "p.html"
    html.write_text("<html><body><p>First.</p><p>Second.</p></body></html>", encoding="utf-8")
    out = extraction.extract(html, tmp_path / "p.txt")
    body = out.read_text(encoding="utf-8")
    assert "First" in body and "Second" in body


def test_extraction_falls_back_to_plain_text(tmp_path):
    from corpus_lib import extraction

    src = tmp_path / "p.txt"
    src.write_text("plain paragraph here", encoding="utf-8")
    out = extraction.extract(src, tmp_path / "out.txt")
    assert "plain paragraph" in out.read_text(encoding="utf-8")


# -- Stage 4: language verification ----------------------------------------- #


def test_lang_verify_ascii_fallback(monkeypatch):
    from corpus_lib import lang_verify

    # Force the fasttext loader to raise so the ascii-ratio heuristic fires.
    def _boom():
        raise RuntimeError("no fasttext in test env")

    monkeypatch.setattr(lang_verify, "_load_fasttext", _boom)
    assert lang_verify.detect_lang("Hello this is in English") == "en"
    assert lang_verify.detect_lang("") == "unknown"


def test_filter_papers_keeps_target_language(tmp_path, monkeypatch):
    from corpus_lib import lang_verify

    text_root = tmp_path / "text"
    text_root.mkdir()
    (text_root / "a.txt").write_text("Hello English text", encoding="utf-8")
    (text_root / "b.txt").write_text("foo bar", encoding="utf-8")
    monkeypatch.setattr(lang_verify, "detect_lang", lambda t: "en" if "English" in t else "fr")
    kept = lang_verify.filter_papers(
        [{"id": "a"}, {"id": "b"}],
        target_lang="en",
        text_root=text_root,
    )
    assert [p["id"] for p in kept] == ["a"]


# -- Stage 5: segmentation -------------------------------------------------- #


def test_segmentation_produces_paragraphs():
    from corpus_lib import segmentation

    text = (
        "First paragraph " + " ".join(["word"] * 30) + ".\n\n"
        "Second paragraph " + " ".join(["item"] * 30) + ".\n\n"
        "tiny"  # below the 20-word floor → dropped
    )
    paras = segmentation.segment(text, paper_id="x")
    assert len(paras) == 2
    assert paras[0]["paper_id"] == "x"
    assert "n_words" in paras[0]
    assert paras[0]["section"] in {
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
        "Conclusion",
        "Body",
    }


def test_segmentation_detects_methods_section():
    from corpus_lib import segmentation

    text = (
        "Methods. Materials and methods were employed. " + " ".join(["w"] * 30) + ".\n\n"
        "Detailed protocol description goes here. " + " ".join(["x"] * 30) + ".\n\n"
    )
    paras = segmentation.segment(text, paper_id="paper")
    assert any(p["section"] == "Methods" for p in paras)


def test_segment_paper_writes_jsonl(tmp_path):
    from corpus_lib import segmentation

    src = tmp_path / "src.txt"
    src.write_text(
        "Hello " + " ".join(["w"] * 30) + ".\n\n" + "World " + " ".join(["x"] * 30) + ".",
        encoding="utf-8",
    )
    out = tmp_path / "paragraphs.jsonl"
    count = segmentation.segment_paper(src, paper_id="P", language="en", out_jsonl=out)
    assert count == 2
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

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

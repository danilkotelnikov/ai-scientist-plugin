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


# -- Stage 6: dedup --------------------------------------------------------- #


def test_dedup_removes_near_duplicates():
    pytest.importorskip("datasketch")
    from corpus_lib import dedup

    pgs = [
        {"paper_id": "a", "text": "The reaction was carried out at room temperature."},
        {
            "paper_id": "b",
            "text": "The reaction was carried out at room temperature!",
        },  # near-dup
        {
            "paper_id": "c",
            "text": "Quantum entanglement was observed in the photonic system.",
        },
    ]
    kept = dedup.dedup_minhash(pgs, jaccard_threshold=0.85)
    # at most 2 should survive — c is unrelated, a/b are near-duplicates.
    paper_ids = {p["paper_id"] for p in kept}
    assert "c" in paper_ids
    assert len(kept) == 2


# -- Stage 7: labeling ------------------------------------------------------ #


def test_labeling_picks_section_paragraphs():
    from corpus_lib import labeling

    pgs = [
        {"paper_id": "a", "text": "x" * 200, "n_words": 50, "section": "Methods"},
        {"paper_id": "a", "text": "y" * 200, "n_words": 50, "section": "References"},
        {"paper_id": "a", "text": "z" * 200, "n_words": 10, "section": "Results"},  # too short
    ]
    labeled = labeling.label_positives(pgs)
    assert len(labeled) == 1
    assert labeled[0]["label"] == 1
    assert labeled[0]["label_source"] == "rule"


# -- Stage 8: negative generation ------------------------------------------- #


@pytest.mark.asyncio
async def test_negative_generator_dispatches_through_byok(tmp_path):
    """Stage 8 talks to BYOK via dispatch_agent. Mock it and confirm payload shape."""
    from corpus_lib import negative_generator

    class _Resp:
        content = "Rewritten paragraph in AI register."

    async def _fake_dispatch(**kwargs):
        return _Resp()

    with patch.object(negative_generator, "dispatch_agent", side_effect=_fake_dispatch):
        positives = [
            {
                "paper_id": "a",
                "para_idx": 1,
                "text": "Original paragraph.",
                "section": "Methods",
            }
        ]
        negatives = await negative_generator.generate_negatives(positives, concurrency=2)
        assert len(negatives) == 1
        neg = negatives[0]
        assert neg["label"] == 0
        assert neg["paper_id"] == "a_neg"
        assert neg["label_source"] == "adversarial_generator"
        assert neg["text"] == "Rewritten paragraph in AI register."


# -- Stage 9: splits -------------------------------------------------------- #


def test_splits_no_paper_leak():
    from corpus_lib import splits

    data = (
        [{"paper_id": f"p{i}", "text": "x", "label": 1} for i in range(10)]
        + [{"paper_id": f"q{i}", "text": "y", "label": 0} for i in range(10)]
    )
    train, val, test = splits.stratified_split_by_paper(
        data, val_frac=0.2, test_frac=0.2, seed=42
    )
    train_pids = {d["paper_id"] for d in train}
    val_pids = {d["paper_id"] for d in val}
    test_pids = {d["paper_id"] for d in test}
    assert not (train_pids & val_pids)
    assert not (train_pids & test_pids)
    assert not (val_pids & test_pids)
    # All papers accounted for.
    assert train_pids | val_pids | test_pids == {d["paper_id"] for d in data}


# -- Stage 10: stats -------------------------------------------------------- #


def test_stats_writes_class_balance(tmp_path):
    from corpus_lib import stats

    train = [
        {"paper_id": "a", "text": "x", "label": 1, "n_words": 10},
        {"paper_id": "b", "text": "y", "label": 0, "n_words": 20},
    ]
    val = [{"paper_id": "c", "text": "z", "label": 1, "n_words": 30}]
    test = [{"paper_id": "d", "text": "w", "label": 0, "n_words": 40}]
    out = tmp_path / "corpus_stats.json"
    obj = stats.compute_stats(train=train, val=val, test=test, out=out)
    assert out.exists()
    assert obj["train"]["n"] == 2
    assert obj["train"]["class_balance"] == {1: 1, 0: 1}
    assert obj["val"]["n"] == 1
    assert obj["test"]["n"] == 1


# -- Orchestrator (prepare_corpus.py) -------------------------------------- #


@pytest.mark.asyncio
async def test_prepare_one_pair_end_to_end(tmp_path, monkeypatch):
    """End-to-end smoke: each stage mocked so we can verify checkpoint flow."""
    pytest.importorskip("datasketch")
    import importlib

    # Import the orchestrator from the scripts/ folder.
    if "prepare_corpus" in sys.modules:
        del sys.modules["prepare_corpus"]
    prepare_corpus = importlib.import_module("prepare_corpus")

    fake_papers = [
        {
            "doi": "10.1/a",
            "id": "p1",
            "language": "en",
            "license": "cc-by",
            "full_text_url": "u1",
        },
        {
            "doi": "10.1/b",
            "id": "p2",
            "language": "en",
            "license": "cc-by",
            "full_text_url": "u2",
        },
    ]

    async def _fake_harvest(*, discipline, language, target_count, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            "\n".join(__import__("json").dumps(p) for p in fake_papers),
            encoding="utf-8",
        )
        return list(fake_papers)

    async def _fake_download_many(urls_and_dests, concurrency=8):
        for url, dest in urls_and_dests:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4 fake")
        return [d for _, d in urls_and_dests]

    def _fake_extract(src, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "Methods. " + " ".join(["w"] * 60) + ".\n\n"
            + "Results. " + " ".join(["x"] * 60) + ".\n\n"
            + "Discussion. " + " ".join(["y"] * 60) + ".\n\n"
        )
        dest.write_text(text, encoding="utf-8")
        return dest

    monkeypatch.setattr(prepare_corpus.acquisition, "harvest", _fake_harvest)
    monkeypatch.setattr(prepare_corpus.download, "download_many", _fake_download_many)
    monkeypatch.setattr(prepare_corpus.extraction, "extract", _fake_extract)
    monkeypatch.setattr(
        prepare_corpus.lang_verify,
        "filter_papers",
        lambda papers, *, target_lang, text_root: list(papers),
    )

    async def _fake_negs(positives, *, concurrency=4):
        return [
            {
                "paper_id": p["paper_id"] + "_neg",
                "para_idx": p.get("para_idx", -1),
                "text": "AI-style rewrite of " + p["text"][:30],
                "n_words": 50,
                "section": p.get("section", "Body"),
                "label": 0,
                "label_source": "adversarial_generator",
                "source_para_id": p["paper_id"],
            }
            for p in positives
        ]

    monkeypatch.setattr(
        prepare_corpus.negative_generator,
        "generate_negatives",
        _fake_negs,
    )

    corpus_root = tmp_path / "corpus"
    await prepare_corpus.prepare_one_pair(
        discipline="chemistry",
        language="en",
        target_count=2,
        corpus_root=corpus_root,
    )

    pair_dir = corpus_root / "chemistry" / "en"
    # All 10 stage markers written.
    for stage in (
        "acquisition",
        "download",
        "extraction",
        "lang_verify",
        "segmentation",
        "dedup",
        "labeling",
        "negatives",
        "splits",
        "stats",
    ):
        assert (pair_dir / ".checkpoints" / f"{stage}.done").exists(), stage
    assert (pair_dir / "train.jsonl").exists()
    assert (pair_dir / "val.jsonl").exists()
    assert (pair_dir / "test.jsonl").exists()
    assert (pair_dir / "corpus_stats.json").exists()


@pytest.mark.asyncio
async def test_prepare_one_pair_skips_done_stages(tmp_path, monkeypatch):
    """Stages marked done must not be re-run."""
    pytest.importorskip("datasketch")
    import importlib

    if "prepare_corpus" in sys.modules:
        del sys.modules["prepare_corpus"]
    prepare_corpus = importlib.import_module("prepare_corpus")

    corpus_root = tmp_path / "corpus"
    pair_dir = corpus_root / "chemistry" / "en"
    pair_dir.mkdir(parents=True)

    # Pre-mark every stage done so the orchestrator should skip them all.
    (pair_dir / ".checkpoints").mkdir(parents=True, exist_ok=True)
    for stage in (
        "acquisition",
        "download",
        "extraction",
        "lang_verify",
        "segmentation",
        "dedup",
        "labeling",
        "negatives",
        "splits",
        "stats",
    ):
        (pair_dir / ".checkpoints" / f"{stage}.done").write_text("{}", encoding="utf-8")

    called: dict[str, bool] = {}

    async def _flag(name):
        async def _g(**kw):
            called[name] = True
            return []

        return _g

    monkeypatch.setattr(
        prepare_corpus.acquisition,
        "harvest",
        await _flag("acquisition"),
    )

    await prepare_corpus.prepare_one_pair(
        discipline="chemistry",
        language="en",
        target_count=2,
        corpus_root=corpus_root,
    )
    assert called == {}

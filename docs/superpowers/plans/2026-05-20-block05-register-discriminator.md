# Block 5 — Hybrid Register Discriminator + Dataset Prep + CPU/GPU Training Implementation Plan (§5.3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Build the hybrid linguistic register discriminator end-to-end: (A) the always-on retrieval-grounded Layer A; (B) the always-on trained Layer B classifier with full corpus preparation (8 disciplines × 7 languages = 56 pairs, ~150 papers per pair) and **two complete training scripts** — CPU path on Intel Xeon 8368 (mDeBERTa-v3-small) and GPU path on RTX 4060 8 GB (xlm-roberta-base), with an auto-dispatcher that picks the right one; (C) a model registry + distribution pipeline that bundles pre-trained classifiers in the install (via `vedix model fetch`) so every user gets Layer B without local training, and an opt-in `vedix model train` for advanced users.

**Architecture:** Three subsystems. (1) Dataset prep: `scripts/prepare_corpus.py` orchestrates a 10-stage pipeline per (discipline, lang) pair — acquisition via MCPs → download → text extraction → language verification → segmentation → dedup → positive labeling → adversarial negative generation → train/val/test split → statistics. Idempotent with stage-level checkpoints. (2) Training: two siblings (`train_register_classifier_cpu.py` for bf16 mDeBERTa-v3-small; `train_register_classifier_gpu.py` for fp16 xlm-roberta-base) plus `train_register_classifier.py --auto` that detects hardware. Both emit identical output layout to `~/.vedix/classifiers/register_{discipline}_{lang}/`. (3) Inference: a `register_discriminator.py` module that loads the matching model per (discipline, lang), runs Layer A retrieval + Layer B classifier in parallel, gates manuscripts.

**Tech Stack:**
- **Dataset prep:** `httpx` (downloads), `pdfminer.six` + `lxml` + `tika` (extraction), `fasttext-langdetect` (lang verification), `spacy` (sentence + paragraph), `datasketch` (MinHashLSH dedup), MCPs (`mcp__openalex`, `mcp__semanticscholar`, `mcp__arxiv`, `mcp__biorxiv`, `mcp__pubmed`, `mcp__annas-mcp`)
- **Training:** `torch 2.4+`, `transformers 4.45+` (`AutoModelForSequenceClassification`), `safetensors`, `accelerate`, `tensorboard`, `psutil` (hardware detection)
- **Inference:** `chromadb` (Layer A retrieval), `sentence-transformers` (`intfloat/multilingual-e5-large`), the trained classifier checkpoints from above
- **Model registry:** `httpx` + `boto3`-style multipart upload to `models.vedix.ai`

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §5.3.1, §5.3.2.a, §5.3.2.b, §5.3.2.c, §5.3.2.d.

---

## File structure

```
plugins/vedix/mcp/lib/orchestrator/
├── register_discriminator.py        # Layer A + Layer B inference

scripts/
├── prepare_corpus.py                # §5.3.1 dataset prep dispatcher
├── train_register_classifier.py     # §5.3.2.c auto-dispatcher (CPU vs GPU)
├── train_register_classifier_cpu.py # §5.3.2.a CPU path (Xeon 8368, mDeBERTa-v3-small)
├── train_register_classifier_gpu.py # §5.3.2.b GPU path (RTX 4060 8 GB, xlm-roberta-base)
└── corpus_lib/                      # shared helpers used by both training scripts
    ├── __init__.py
    ├── acquisition.py               # stage 1: MCP-driven candidate harvest
    ├── download.py                  # stage 2: PDF/XML fetch
    ├── extraction.py                # stage 3: text extraction
    ├── lang_verify.py               # stage 4: fasttext lid
    ├── segmentation.py              # stage 5: spacy paragraph split
    ├── dedup.py                     # stage 6: MinHashLSH
    ├── labeling.py                  # stage 7: positive labeling (rule-based)
    ├── negative_generator.py        # stage 8: adversarial AI-style negatives via BYOK
    ├── splits.py                    # stage 9: stratified train/val/test
    ├── stats.py                     # stage 10: corpus_stats.json
    └── checkpoint.py                # per-stage idempotency

docs/training/
├── README.md                        # one-page launch guide for users
├── cpu-instructions.md              # detailed CPU launch
└── gpu-instructions.md              # detailed GPU launch

tests/discriminator/
├── test_layer_a.py
├── test_layer_b.py
├── test_dataset_prep_stages.py
├── test_cpu_training_smoke.py       # smoke test with tiny dataset
└── test_gpu_training_smoke.py       # smoke test with tiny dataset (cuda-skip if no GPU)
```

## Task 1: Layer A — retrieval-grounded discriminator

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/register_discriminator.py` (Layer A portion)
- Test: `tests/discriminator/test_layer_a.py`

- [ ] **Step 1: Write failing test**

```python
# tests/discriminator/test_layer_a.py
import pytest
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.register_discriminator import LayerA

def test_layer_a_passes_in_register(tmp_path):
    layer = LayerA(corpus_root=tmp_path, discipline="chemistry", language="en")
    # Seed a tiny corpus
    corpus_chunks = [
        "We synthesized 5 g of compound 1 by refluxing in ethanol.",
        "The reaction was monitored by TLC; column chromatography gave the pure product.",
        "NMR (CDCl3, 400 MHz): δ 7.25 (m, 2H), 4.12 (q, 2H).",
    ]
    layer.add_corpus(corpus_chunks)
    verdict = layer.judge("The compound was prepared by reflux in ethanol.")
    assert verdict.pass_ or verdict.score > 0.5

def test_layer_a_fails_out_of_register(tmp_path):
    layer = LayerA(corpus_root=tmp_path, discipline="chemistry", language="en")
    corpus_chunks = ["We synthesized compound 1 by refluxing in ethanol."] * 10
    layer.add_corpus(corpus_chunks)
    verdict = layer.judge("OMG this catalyst is just SO amazing!!1!")
    assert not verdict.pass_
```

- [ ] **Step 2: Run — verify fails**

- [ ] **Step 3: Implement Layer A**

```python
# plugins/vedix/mcp/lib/orchestrator/register_discriminator.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:  # pragma: no cover
    chromadb = None

@dataclass
class Verdict:
    pass_: bool
    score: float
    explanation: str
    layer: str  # "A" or "B"

class LayerA:
    """Retrieval-grounded discriminator."""

    def __init__(self, *, corpus_root: Path, discipline: str, language: str, threshold: float = 0.55):
        self.corpus_root = Path(corpus_root)
        self.discipline = discipline
        self.language = language
        self.threshold = threshold
        self._client = chromadb.PersistentClient(path=str(self.corpus_root / discipline / language / "chromadb"))
        self._collection = self._client.get_or_create_collection(
            name=f"{discipline}_{language}",
            metadata={"hnsw:space": "cosine"},
        )
        self._encoder = None

    def _enc(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer("intfloat/multilingual-e5-large")
        return self._encoder

    def add_corpus(self, chunks: list[str]) -> None:
        embs = self._enc().encode(["passage: " + c for c in chunks], normalize_embeddings=True).tolist()
        self._collection.add(
            ids=[f"chunk_{i}_{hash(c) & 0xffffffff}" for i, c in enumerate(chunks)],
            embeddings=embs,
            documents=chunks,
        )

    def judge(self, paragraph: str, k: int = 5) -> Verdict:
        emb = self._enc().encode([f"query: {paragraph}"], normalize_embeddings=True).tolist()
        res = self._collection.query(query_embeddings=emb, n_results=k)
        if not res["distances"] or not res["distances"][0]:
            return Verdict(pass_=False, score=0.0, explanation="empty corpus", layer="A")
        # ChromaDB cosine "distance" = 1 - cosine_similarity
        best_similarity = 1.0 - min(res["distances"][0])
        passes = best_similarity >= self.threshold
        return Verdict(
            pass_=passes, score=round(float(best_similarity), 3),
            explanation=f"best k-NN cosine similarity {best_similarity:.3f} vs threshold {self.threshold}",
            layer="A",
        )
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/discriminator/test_layer_a.py -v
git add plugins/vedix/mcp/lib/orchestrator/register_discriminator.py tests/discriminator/test_layer_a.py
git commit -m "feat(B5): Layer A retrieval-grounded register discriminator (ChromaDB + multilingual-e5)"
```

## Task 2: Dataset prep stage 1 — Acquisition

**Files:**
- Create: `scripts/corpus_lib/__init__.py`
- Create: `scripts/corpus_lib/acquisition.py`
- Create: `scripts/corpus_lib/checkpoint.py`
- Test: `tests/discriminator/test_dataset_prep_stages.py` (stage 1 subset)

- [ ] **Step 1: Write failing test**

```python
# tests/discriminator/test_dataset_prep_stages.py
import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from corpus_lib import acquisition, checkpoint

@pytest.mark.asyncio
async def test_acquisition_returns_candidates(tmp_path):
    fake_papers = [
        {"doi": "10.1/a", "title": "Catalysis", "year": 2023, "language": "en", "license": "cc-by", "full_text_url": "u1"},
        {"doi": "10.1/b", "title": "Synthesis", "year": 2024, "language": "en", "license": "cc-by", "full_text_url": "u2"},
    ]
    with patch("corpus_lib.acquisition._call_openalex", new=AsyncMock(return_value=fake_papers)), \
         patch("corpus_lib.acquisition._call_semanticscholar", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_arxiv", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_biorxiv", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_pubmed", new=AsyncMock(return_value=[])), \
         patch("corpus_lib.acquisition._call_annas", new=AsyncMock(return_value=[])):
        out = tmp_path / "acquisition.jsonl"
        candidates = await acquisition.harvest(discipline="chemistry", language="en", target_count=2, out_path=out)
        assert len(candidates) == 2
        assert out.exists()

def test_checkpoint_skips_done_stages(tmp_path):
    cp = checkpoint.StageCheckpoint(root=tmp_path)
    assert not cp.is_done("acquisition")
    cp.mark_done("acquisition")
    assert cp.is_done("acquisition")
```

- [ ] **Step 2: Run — verify fails**

- [ ] **Step 3: Implement checkpoint helper**

```python
# scripts/corpus_lib/checkpoint.py
from __future__ import annotations
import json
import time
from pathlib import Path

class StageCheckpoint:
    def __init__(self, root: Path):
        self.dir = Path(root) / ".checkpoints"
        self.dir.mkdir(parents=True, exist_ok=True)

    def is_done(self, stage: str) -> bool:
        return (self.dir / f"{stage}.done").exists()

    def mark_done(self, stage: str, payload: dict | None = None) -> None:
        info = {"stage": stage, "ts": time.time(), **(payload or {})}
        (self.dir / f"{stage}.done").write_text(json.dumps(info), encoding="utf-8")

    def reset(self, stage: str) -> None:
        (self.dir / f"{stage}.done").unlink(missing_ok=True)
```

- [ ] **Step 4: Implement acquisition**

```python
# scripts/corpus_lib/acquisition.py
"""Stage 1 — harvest paper candidates via MCPs."""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

# Discipline → search-keyword routing (used to scope MCP queries)
DISCIPLINE_QUERIES = {
    "chemistry": ["organic synthesis", "catalysis", "spectroscopy", "reaction kinetics", "crystallography"],
    "biology":   ["gene expression", "protein structure", "cell signaling", "microbiome", "evolutionary biology"],
    "medicine":  ["randomized clinical trial", "epidemiology", "biomarker", "therapeutic intervention", "diagnostic accuracy"],
    "physics":   ["quantum mechanics", "condensed matter", "particle physics", "general relativity", "thermodynamics"],
    "mathematics": ["topology", "algebraic geometry", "stochastic processes", "graph theory", "functional analysis"],
    "geology":   ["plate tectonics", "geochronology", "stratigraphy", "geochemistry", "volcanology"],
    "computer_science": ["machine learning", "distributed systems", "type theory", "computational complexity", "computer vision"],
    "humanities":["literary analysis", "historical methodology", "philosophical argument", "linguistic semantics", "cultural studies"],
}

# Per-language query language hints — pass to MCPs
LANG_HINTS = {"en": "English", "ru": "Russian", "es": "Spanish", "de": "German", "fr": "French", "zh": "Chinese", "ja": "Japanese"}

async def _call_openalex(query: str, language: str, n: int) -> list[dict]:
    """Call mcp__openalex__search_works (skill is wired through Vedix's MCP layer)."""
    # In real run, this dispatches through plugins/vedix/mcp/lib/orchestrator/mcp_client.py.
    # Tests patch this function.
    return []

async def _call_semanticscholar(query: str, language: str, n: int) -> list[dict]: return []
async def _call_arxiv(query: str, language: str, n: int) -> list[dict]: return []
async def _call_biorxiv(query: str, language: str, n: int) -> list[dict]: return []
async def _call_pubmed(query: str, language: str, n: int) -> list[dict]: return []
async def _call_annas(query: str, language: str, n: int) -> list[dict]: return []

async def harvest(*, discipline: str, language: str, target_count: int = 200, out_path: Path) -> list[dict]:
    queries = DISCIPLINE_QUERIES.get(discipline, [discipline])
    per_query = max(10, target_count // len(queries))
    candidates: list[dict] = []
    seen_dois = set()

    # Run each MCP in parallel for each query
    tasks = []
    for q in queries:
        tasks.append(_call_openalex(q, language, per_query))
        tasks.append(_call_semanticscholar(q, language, per_query))
        tasks.append(_call_arxiv(q, language, per_query))
        if discipline in ("biology", "medicine"):
            tasks.append(_call_biorxiv(q, language, per_query))
            tasks.append(_call_pubmed(q, language, per_query))
        tasks.append(_call_annas(q, language, per_query))
    results_lists = await asyncio.gather(*tasks)

    for lst in results_lists:
        for paper in lst:
            doi = paper.get("doi") or paper.get("id")
            if not doi or doi in seen_dois:
                continue
            if not paper.get("license", "").lower().startswith(("cc", "public", "open", "mit", "apache")):
                continue
            if paper.get("language") and paper["language"][:2] != language:
                continue
            candidates.append(paper)
            seen_dois.add(doi)
            if len(candidates) >= target_count:
                break
        if len(candidates) >= target_count:
            break

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")
    return candidates
```

- [ ] **Step 5: Run + commit**

```bash
pytest tests/discriminator/test_dataset_prep_stages.py::test_acquisition_returns_candidates tests/discriminator/test_dataset_prep_stages.py::test_checkpoint_skips_done_stages -v
git add scripts/corpus_lib/ tests/discriminator/test_dataset_prep_stages.py
git commit -m "feat(B5): stage 1 acquisition + stage checkpoint helper"
```

## Task 3: Dataset prep stages 2-5 — download / extract / lang-verify / segment

**Files:**
- Create: `scripts/corpus_lib/download.py`
- Create: `scripts/corpus_lib/extraction.py`
- Create: `scripts/corpus_lib/lang_verify.py`
- Create: `scripts/corpus_lib/segmentation.py`

- [ ] **Step 1: Write tests**

```python
# tests/discriminator/test_dataset_prep_stages.py (extend)
def test_extraction_handles_pdf(tmp_path, monkeypatch):
    from corpus_lib import extraction
    # Use a tiny valid PDF; for unit test, use a stub
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake")
    monkeypatch.setattr(extraction, "_pdf_to_text", lambda p: "Hello world. This is paragraph 1.\n\nThis is paragraph 2.")
    out = extraction.extract(pdf, tmp_path / "p.txt")
    assert "Hello world" in out.read_text(encoding="utf-8")

def test_lang_verify_filters_wrong_language(tmp_path):
    from corpus_lib import lang_verify
    # Stub the fasttext detector
    text = "Hello this is in English"
    assert lang_verify.detect_lang(text) == "en"

def test_segmentation_produces_paragraphs(tmp_path):
    from corpus_lib import segmentation
    text = "First paragraph sentence one. Sentence two.\n\nSecond paragraph here.\n\nThird."
    paras = segmentation.segment(text, paper_id="x")
    assert len(paras) >= 2
    assert paras[0]["paper_id"] == "x"
```

- [ ] **Step 2: Implement download**

```python
# scripts/corpus_lib/download.py
from __future__ import annotations
import asyncio
import httpx
from pathlib import Path

async def download_one(url: str, dest: Path, timeout: float = 60.0) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                with dest.open("wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=64_000):
                        f.write(chunk)
        return dest
    except Exception as e:
        print(f"[download] failed {url}: {e}")
        return None

async def download_many(urls_and_dests: list[tuple[str, Path]], concurrency: int = 8) -> list[Path]:
    sem = asyncio.Semaphore(concurrency)
    async def _g(url, dest):
        async with sem:
            return await download_one(url, dest)
    results = await asyncio.gather(*[_g(u, d) for u, d in urls_and_dests])
    return [r for r in results if r is not None]
```

- [ ] **Step 3: Implement extraction**

```python
# scripts/corpus_lib/extraction.py
from __future__ import annotations
from pathlib import Path

def _pdf_to_text(p: Path) -> str:
    from pdfminer.high_level import extract_text
    return extract_text(str(p))

def _xml_to_text(p: Path) -> str:
    from lxml import etree
    tree = etree.parse(str(p))
    # JATS-flavoured XML: pull body paragraphs
    body = tree.xpath("//body | //article-body")
    if body:
        text_chunks = []
        for elem in body[0].iter("p"):
            text_chunks.append(" ".join(elem.itertext()).strip())
        return "\n\n".join(text_chunks)
    return " ".join(tree.getroot().itertext())

def extract(src: Path, dest: Path) -> Path:
    if src.suffix.lower() == ".pdf":
        text = _pdf_to_text(src)
    elif src.suffix.lower() in (".xml", ".jats"):
        text = _xml_to_text(src)
    elif src.suffix.lower() in (".html", ".htm"):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(src.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        text = soup.get_text("\n")
    else:
        text = src.read_text(encoding="utf-8", errors="ignore")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest
```

- [ ] **Step 4: Implement lang verification**

```python
# scripts/corpus_lib/lang_verify.py
from __future__ import annotations
from pathlib import Path
import os

_MODEL = None
def _load_fasttext():
    global _MODEL
    if _MODEL is None:
        import fasttext
        # lid.176.bin is shipped via huggingface — caller can override path via VEDIX_FASTTEXT_LID
        path = os.environ.get("VEDIX_FASTTEXT_LID", str(Path.home() / ".vedix" / "models" / "lid.176.bin"))
        if not Path(path).exists():
            import urllib.request
            url = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, path)
        _MODEL = fasttext.load_model(path)
    return _MODEL

def detect_lang(text: str) -> str:
    if not text.strip():
        return "unknown"
    try:
        m = _load_fasttext()
        labels, _ = m.predict(text.replace("\n", " ")[:1000])
        return labels[0].replace("__label__", "")
    except Exception:
        # ASCII heuristic fallback
        ascii_ratio = sum(1 for c in text if c.isascii()) / max(1, len(text))
        return "en" if ascii_ratio > 0.9 else "unknown"

def filter_papers(papers: list[dict], target_lang: str, text_root: Path) -> list[dict]:
    keep = []
    for p in papers:
        text_file = text_root / f"{p.get('id', p.get('doi'))}.txt"
        if not text_file.exists():
            continue
        detected = detect_lang(text_file.read_text(encoding="utf-8")[:5000])
        if detected == target_lang:
            keep.append(p)
    return keep
```

- [ ] **Step 5: Implement segmentation**

```python
# scripts/corpus_lib/segmentation.py
from __future__ import annotations
import json
import re
from pathlib import Path

_SPACY = None
def _spacy_for(language: str):
    global _SPACY
    import spacy
    model_map = {"en": "en_core_web_sm", "ru": "ru_core_news_sm", "es": "es_core_news_sm",
                 "de": "de_core_news_sm", "fr": "fr_core_news_sm", "zh": "zh_core_web_sm", "ja": "ja_core_news_sm"}
    name = model_map.get(language, "xx_sent_ud_sm")
    if _SPACY is None or _SPACY.lang != name:
        try:
            _SPACY = spacy.load(name, disable=["ner", "tagger"])
        except OSError:
            from spacy.cli import download
            download(name)
            _SPACY = spacy.load(name, disable=["ner", "tagger"])
    return _SPACY

# Heuristic: paragraphs separated by blank lines OR by indent
def _paragraph_split(text: str) -> list[str]:
    paras = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paras if p.strip()]

def segment(text: str, *, paper_id: str, language: str = "en") -> list[dict]:
    paragraphs = _paragraph_split(text)
    out = []
    for i, p in enumerate(paragraphs):
        n_words = len(p.split())
        if n_words < 20 or n_words > 600:  # too short = boilerplate; too long = bad split
            continue
        out.append({
            "paper_id": paper_id,
            "para_idx": i,
            "text": p,
            "n_words": n_words,
            "section": _guess_section(p, i, paragraphs),
        })
    return out

_SECTION_KW = {
    "Introduction": [r"\bintroduction\b", r"\bbackground\b"],
    "Methods": [r"\bmethods\b", r"\bmethodolog", r"\bexperimental\b", r"\bmaterials and methods\b"],
    "Results": [r"\bresults\b", r"\bfindings\b"],
    "Discussion": [r"\bdiscussion\b"],
    "Conclusion": [r"\bconclusion\b", r"\bsummary\b"],
}

def _guess_section(text: str, idx: int, all_paras: list[str]) -> str:
    # Look back at recent paragraphs for a header keyword
    head_text = " ".join(all_paras[max(0, idx-2):idx+1]).lower()
    for sect, patterns in _SECTION_KW.items():
        if any(re.search(p, head_text) for p in patterns):
            return sect
    return "Body"

def segment_paper(text_file: Path, *, paper_id: str, language: str, out_jsonl: Path) -> int:
    text = text_file.read_text(encoding="utf-8")
    paragraphs = segment(text, paper_id=paper_id, language=language)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("a", encoding="utf-8") as f:
        for p in paragraphs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return len(paragraphs)
```

- [ ] **Step 6: Run + commit**

```bash
pytest tests/discriminator/test_dataset_prep_stages.py -v
git add scripts/corpus_lib/download.py scripts/corpus_lib/extraction.py scripts/corpus_lib/lang_verify.py scripts/corpus_lib/segmentation.py
git commit -m "feat(B5): stages 2-5 — download / extraction / lang-verify / segmentation"
```

## Task 4: Dataset prep stages 6-10 — dedup / labeling / negative generation / splits / stats

**Files:**
- Create: `scripts/corpus_lib/dedup.py`
- Create: `scripts/corpus_lib/labeling.py`
- Create: `scripts/corpus_lib/negative_generator.py`
- Create: `scripts/corpus_lib/splits.py`
- Create: `scripts/corpus_lib/stats.py`

- [ ] **Step 1: Write tests**

```python
# tests/discriminator/test_dataset_prep_stages.py (extend)
def test_dedup_removes_near_duplicates(tmp_path):
    from corpus_lib import dedup
    pgs = [
        {"paper_id": "a", "text": "The reaction was carried out at room temperature."},
        {"paper_id": "b", "text": "The reaction was carried out at room temperature!"},  # near-duplicate
        {"paper_id": "c", "text": "Quantum entanglement was observed in the photonic system."},
    ]
    kept = dedup.dedup_minhash(pgs, jaccard_threshold=0.85)
    assert len(kept) == 2

def test_labeling_picks_section_paragraphs(tmp_path):
    from corpus_lib import labeling
    pgs = [
        {"paper_id": "a", "text": "x" * 200, "n_words": 50, "section": "Methods"},
        {"paper_id": "a", "text": "y" * 200, "n_words": 50, "section": "References"},  # excluded
    ]
    labeled = labeling.label_positives(pgs)
    assert all(p["label"] == 1 for p in labeled)
    assert len(labeled) == 1

def test_splits_no_paper_leak(tmp_path):
    from corpus_lib import splits
    data = [{"paper_id": f"p{i}", "text": "x", "label": 1} for i in range(10)] + \
           [{"paper_id": f"q{i}", "text": "y", "label": 0} for i in range(10)]
    train, val, test = splits.stratified_split_by_paper(data, val_frac=0.2, test_frac=0.2, seed=42)
    train_pids = {d["paper_id"] for d in train}
    val_pids = {d["paper_id"] for d in val}
    test_pids = {d["paper_id"] for d in test}
    assert not (train_pids & val_pids)
    assert not (train_pids & test_pids)
```

- [ ] **Step 2: Implement dedup**

```python
# scripts/corpus_lib/dedup.py
from __future__ import annotations
from datasketch import MinHash, MinHashLSH

def _shingles(text: str, k: int = 5) -> list[str]:
    text = text.lower()
    return [text[i:i+k] for i in range(len(text) - k + 1)]

def _minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for s in _shingles(text):
        m.update(s.encode("utf-8"))
    return m

def dedup_minhash(paragraphs: list[dict], jaccard_threshold: float = 0.85, num_perm: int = 128) -> list[dict]:
    lsh = MinHashLSH(threshold=jaccard_threshold, num_perm=num_perm)
    kept = []
    for i, p in enumerate(paragraphs):
        mh = _minhash(p["text"], num_perm=num_perm)
        key = f"p{i}"
        if not lsh.query(mh):
            lsh.insert(key, mh)
            kept.append(p)
    return kept
```

- [ ] **Step 3: Implement labeling**

```python
# scripts/corpus_lib/labeling.py
KEEP_SECTIONS = {"Introduction", "Methods", "Results", "Discussion", "Conclusion", "Body"}

def label_positives(paragraphs: list[dict]) -> list[dict]:
    return [
        {**p, "label": 1, "label_source": "rule"}
        for p in paragraphs
        if p.get("section") in KEEP_SECTIONS and 40 <= p.get("n_words", 0) <= 400
    ]
```

- [ ] **Step 4: Implement negative generation**

```python
# scripts/corpus_lib/negative_generator.py
"""Stage 8 — generate adversarial AI-style negatives via the BYOK provider."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "vedix" / "mcp" / "lib"))
from orchestrator.dispatch import dispatch_agent

# Tier-1+2 AI-tell blacklist (excerpt; full list in plugins/vedix/.../anti_llm_lint.py)
TIER1_BLACKLIST_HINT = [
    "delve", "intricate", "tapestry", "myriad", "navigate", "underscore",
    "showcase", "leverage", "harness", "robust",
    "It is important to note that", "It is worth mentioning that",
    "In conclusion", "Furthermore", "Moreover", "Notably",
]

PROMPT = """Rewrite this academic paragraph in clearly AI-generated register.
Inject these markers naturally (pick at least 3): {markers}
Maintain the technical content but make the prose unmistakably AI-stylistic.

Original paragraph:
{text}

Output ONLY the rewritten paragraph, no commentary.
"""

async def generate_one_negative(text: str) -> str:
    import random
    markers = random.sample(TIER1_BLACKLIST_HINT, 4)
    resp = await dispatch_agent(
        agent_type="register-negative-generator",
        prompt=PROMPT.format(text=text, markers=", ".join(markers)),
        max_tokens=600,
    )
    return resp.content.strip()

async def generate_negatives(positives: list[dict], concurrency: int = 4) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    async def _g(p):
        async with sem:
            neg_text = await generate_one_negative(p["text"])
            return {
                "paper_id": p["paper_id"] + "_neg",
                "para_idx": p.get("para_idx", -1),
                "text": neg_text,
                "n_words": len(neg_text.split()),
                "section": p.get("section", "Body"),
                "label": 0,
                "label_source": "adversarial_generator",
                "source_para_id": p["paper_id"],
            }
    return await asyncio.gather(*[_g(p) for p in positives])
```

- [ ] **Step 5: Implement splits**

```python
# scripts/corpus_lib/splits.py
from __future__ import annotations
import random
from collections import defaultdict

def stratified_split_by_paper(data: list[dict], *, val_frac: float = 0.1, test_frac: float = 0.1, seed: int = 42) -> tuple[list, list, list]:
    rng = random.Random(seed)
    by_paper: dict[str, list[dict]] = defaultdict(list)
    for d in data:
        by_paper[d["paper_id"]].append(d)
    papers = list(by_paper)
    rng.shuffle(papers)
    n = len(papers)
    n_val = max(1, int(n * val_frac))
    n_test = max(1, int(n * test_frac))
    val_pids = set(papers[:n_val])
    test_pids = set(papers[n_val:n_val + n_test])
    train, val, test = [], [], []
    for pid, samples in by_paper.items():
        bucket = val if pid in val_pids else (test if pid in test_pids else train)
        bucket.extend(samples)
    return train, val, test
```

- [ ] **Step 6: Implement stats**

```python
# scripts/corpus_lib/stats.py
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from statistics import mean

def compute_stats(*, train: list[dict], val: list[dict], test: list[dict], out: Path) -> dict:
    def stat_for(name, lst):
        labels = Counter(d["label"] for d in lst)
        lengths = [d.get("n_words", len(d["text"].split())) for d in lst]
        return {
            "n": len(lst),
            "class_balance": dict(labels),
            "mean_n_words": round(mean(lengths) if lengths else 0, 1),
        }
    out_obj = {
        "train": stat_for("train", train),
        "val": stat_for("val", val),
        "test": stat_for("test", test),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_obj, indent=2), encoding="utf-8")
    return out_obj
```

- [ ] **Step 7: Run + commit**

```bash
pytest tests/discriminator/test_dataset_prep_stages.py -v
git add scripts/corpus_lib/dedup.py scripts/corpus_lib/labeling.py scripts/corpus_lib/negative_generator.py scripts/corpus_lib/splits.py scripts/corpus_lib/stats.py
git commit -m "feat(B5): stages 6-10 — dedup / labeling / adversarial negatives / splits / stats"
```

## Task 5: Dataset prep orchestrator — `scripts/prepare_corpus.py`

**Files:**
- Create: `scripts/prepare_corpus.py`

- [ ] **Step 1: Implement**

```python
# scripts/prepare_corpus.py
"""Vedix — Dataset preparation pipeline (§5.3.1).

Run for ALL pairs:
    python scripts/prepare_corpus.py --languages en,ru,es,de,fr,zh,ja \
        --disciplines chemistry,biology,medicine,physics,mathematics,geology,computer_science,humanities \
        --target-count 150

Run for ONE pair:
    python scripts/prepare_corpus.py --only-pair chemistry:en --target-count 150

Stages run idempotently with per-stage checkpoints under {corpus_root}/{discipline}/{lang}/.checkpoints/.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_lib import (
    acquisition, download, extraction, lang_verify, segmentation,
    dedup, labeling, negative_generator, splits, stats,
)
from corpus_lib.checkpoint import StageCheckpoint

DISCIPLINES = ["chemistry", "biology", "medicine", "physics", "mathematics", "geology", "computer_science", "humanities"]
LANGUAGES = ["en", "ru", "es", "de", "fr", "zh", "ja"]

def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

def _corpus_root() -> Path:
    return _home() / ".vedix" / "corpus"

async def prepare_one_pair(*, discipline: str, language: str, target_count: int, force_restart: bool = False) -> None:
    root = _corpus_root() / discipline / language
    root.mkdir(parents=True, exist_ok=True)
    cp = StageCheckpoint(root=root)
    if force_restart:
        for stage in ("acquisition", "download", "extraction", "lang_verify", "segmentation",
                      "dedup", "labeling", "negatives", "splits", "stats"):
            cp.reset(stage)

    print(f"\n=== preparing {discipline}/{language} (target {target_count} papers) ===")

    # Stage 1 — acquisition
    if not cp.is_done("acquisition"):
        await acquisition.harvest(discipline=discipline, language=language, target_count=target_count,
                                   out_path=root / "acquisition.jsonl")
        cp.mark_done("acquisition")

    candidates = [json.loads(l) for l in (root / "acquisition.jsonl").read_text(encoding="utf-8").splitlines() if l]
    print(f"  [1/10] {len(candidates)} candidates")

    # Stage 2 — download
    if not cp.is_done("download"):
        pdf_dir = root / "pdf"
        urls_dests = [(p["full_text_url"], pdf_dir / f"{p.get('id', p.get('doi','x')).replace('/', '_')}.pdf")
                      for p in candidates if p.get("full_text_url")]
        await download.download_many(urls_dests, concurrency=8)
        cp.mark_done("download")
    print(f"  [2/10] downloads complete")

    # Stage 3 — extraction
    if not cp.is_done("extraction"):
        text_dir = root / "text"
        for p in candidates:
            pid = p.get("id", p.get("doi","x")).replace("/", "_")
            pdf = root / "pdf" / f"{pid}.pdf"
            if pdf.exists():
                extraction.extract(pdf, text_dir / f"{pid}.txt")
        cp.mark_done("extraction")
    print(f"  [3/10] text extracted")

    # Stage 4 — language verification
    if not cp.is_done("lang_verify"):
        kept = lang_verify.filter_papers(candidates, target_lang=language, text_root=root / "text")
        (root / "lang_verified.jsonl").write_text("\n".join(json.dumps(p) for p in kept) + "\n", encoding="utf-8")
        cp.mark_done("lang_verify")
    print(f"  [4/10] language verified")

    # Stage 5 — segmentation
    if not cp.is_done("segmentation"):
        kept = [json.loads(l) for l in (root / "lang_verified.jsonl").read_text(encoding="utf-8").splitlines() if l]
        para_file = root / "paragraphs.jsonl"
        if para_file.exists():
            para_file.unlink()
        for p in kept:
            pid = p.get("id", p.get("doi","x")).replace("/", "_")
            text_file = root / "text" / f"{pid}.txt"
            if text_file.exists():
                segmentation.segment_paper(text_file, paper_id=pid, language=language, out_jsonl=para_file)
        cp.mark_done("segmentation")
    print(f"  [5/10] segmented into paragraphs")

    # Stage 6 — dedup
    if not cp.is_done("dedup"):
        paras = [json.loads(l) for l in (root / "paragraphs.jsonl").read_text(encoding="utf-8").splitlines() if l]
        kept = dedup.dedup_minhash(paras, jaccard_threshold=0.85)
        (root / "paragraphs_dedup.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in kept) + "\n", encoding="utf-8")
        cp.mark_done("dedup")
    print(f"  [6/10] deduplicated")

    # Stage 7 — labeling
    if not cp.is_done("labeling"):
        paras = [json.loads(l) for l in (root / "paragraphs_dedup.jsonl").read_text(encoding="utf-8").splitlines() if l]
        positives = labeling.label_positives(paras)
        (root / "positives.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in positives) + "\n", encoding="utf-8")
        cp.mark_done("labeling")
    print(f"  [7/10] positives labeled")

    # Stage 8 — adversarial negatives
    if not cp.is_done("negatives"):
        positives = [json.loads(l) for l in (root / "positives.jsonl").read_text(encoding="utf-8").splitlines() if l]
        # Cap to avoid runaway LLM cost on huge corpora
        sample_positives = positives[:1000]
        negatives = await negative_generator.generate_negatives(sample_positives, concurrency=4)
        (root / "negatives.jsonl").write_text("\n".join(json.dumps(n, ensure_ascii=False) for n in negatives) + "\n", encoding="utf-8")
        cp.mark_done("negatives")
    print(f"  [8/10] adversarial negatives generated")

    # Stage 9 — splits
    if not cp.is_done("splits"):
        pos = [json.loads(l) for l in (root / "positives.jsonl").read_text(encoding="utf-8").splitlines() if l]
        neg = [json.loads(l) for l in (root / "negatives.jsonl").read_text(encoding="utf-8").splitlines() if l]
        combined = pos + neg
        train, val, test = splits.stratified_split_by_paper(combined, val_frac=0.1, test_frac=0.1, seed=42)
        for name, lst in [("train", train), ("val", val), ("test", test)]:
            (root / f"{name}.jsonl").write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in lst) + "\n", encoding="utf-8")
        cp.mark_done("splits")
    print(f"  [9/10] train/val/test split")

    # Stage 10 — stats
    if not cp.is_done("stats"):
        train = [json.loads(l) for l in (root / "train.jsonl").read_text(encoding="utf-8").splitlines() if l]
        val = [json.loads(l) for l in (root / "val.jsonl").read_text(encoding="utf-8").splitlines() if l]
        test = [json.loads(l) for l in (root / "test.jsonl").read_text(encoding="utf-8").splitlines() if l]
        stats.compute_stats(train=train, val=val, test=test, out=root / "corpus_stats.json")
        cp.mark_done("stats")
    print(f"  [10/10] stats written. Pair {discipline}/{language} READY.")

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--languages", default=",".join(LANGUAGES))
    ap.add_argument("--disciplines", default=",".join(DISCIPLINES))
    ap.add_argument("--target-count", type=int, default=150)
    ap.add_argument("--only-pair", default=None, help="discipline:language")
    ap.add_argument("--force-restart", action="store_true")
    args = ap.parse_args()

    if args.only_pair:
        d, l = args.only_pair.split(":", 1)
        await prepare_one_pair(discipline=d, language=l, target_count=args.target_count, force_restart=args.force_restart)
        return

    for d in args.disciplines.split(","):
        for l in args.languages.split(","):
            try:
                await prepare_one_pair(discipline=d.strip(), language=l.strip(),
                                       target_count=args.target_count, force_restart=args.force_restart)
            except Exception as e:
                print(f"[prepare_corpus] {d}/{l} FAILED: {e}")
                continue

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add scripts/prepare_corpus.py
git commit -m "feat(B5): prepare_corpus.py — orchestrator for 10-stage dataset prep pipeline"
```

## Task 6: CPU training script — `train_register_classifier_cpu.py`

**Files:**
- Create: `scripts/train_register_classifier_cpu.py`
- Test: `tests/discriminator/test_cpu_training_smoke.py`

- [ ] **Step 1: Write smoke test**

```python
# tests/discriminator/test_cpu_training_smoke.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch

def test_cpu_training_smoke_with_tiny_dataset(tmp_path):
    # Make a tiny corpus
    corpus = tmp_path / "corpus" / "chemistry" / "en"
    corpus.mkdir(parents=True)
    train = [{"text": f"sample {i}", "label": i % 2, "paper_id": f"p{i}"} for i in range(40)]
    val = [{"text": f"val {i}", "label": i % 2, "paper_id": f"v{i}"} for i in range(10)]
    test = [{"text": f"test {i}", "label": i % 2, "paper_id": f"t{i}"} for i in range(10)]
    for name, lst in [("train", train), ("val", val), ("test", test)]:
        (corpus / f"{name}.jsonl").write_text("\n".join(json.dumps(x) for x in lst), encoding="utf-8")

    import subprocess, sys
    result = subprocess.run([
        sys.executable, "scripts/train_register_classifier_cpu.py",
        "--corpus-root", str(tmp_path / "corpus"),
        "--output-root", str(tmp_path / "out"),
        "--languages", "en", "--disciplines", "chemistry",
        "--model", "prajjwal1/bert-tiny",  # smallest possible for the smoke test
        "--epochs", "1", "--batch-size", "2", "--grad-accum", "1",
    ], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    out_dir = tmp_path / "out" / "register_chemistry_en"
    assert (out_dir / "metrics.json").exists()
```

- [ ] **Step 2: Implement**

```python
# scripts/train_register_classifier_cpu.py
"""Vedix — Layer B classifier training (CPU path, Xeon-class, §5.3.2.a).

Target hardware: Intel Xeon 8368 (38c/76t/512GB) or equivalent. No GPU required.
Default model: microsoft/mDeBERTa-v3-small (140M params, ~530MB checkpoint).
Mixed precision: bf16 (Xeon 8368 supports AVX-512 BF16).
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader

def _read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l]

class RegisterDataset(Dataset):
    def __init__(self, items: list[dict], tokenizer, max_length: int = 256):
        self.items = items
        self.tokenizer = tokenizer
        self.max_length = max_length
    def __len__(self): return len(self.items)
    def __getitem__(self, i):
        item = self.items[i]
        enc = self.tokenizer(item["text"], truncation=True, padding="max_length",
                             max_length=self.max_length, return_tensors="pt")
        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels": torch.tensor(item["label"], dtype=torch.long),
        }

def train_one_pair(*, discipline: str, language: str, corpus_root: Path, output_root: Path,
                   model_name: str, epochs: int, batch_size: int, grad_accum: int, lr: float,
                   num_workers: int, bf16: bool, max_length: int = 256, resume: bool = True) -> dict:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
    from sklearn.metrics import precision_recall_fscore_support, accuracy_score

    pair_dir = corpus_root / discipline / language
    train_items = _read_jsonl(pair_dir / "train.jsonl")
    val_items = _read_jsonl(pair_dir / "val.jsonl")
    test_items = _read_jsonl(pair_dir / "test.jsonl")

    out = output_root / f"register_{discipline}_{language}"
    out.mkdir(parents=True, exist_ok=True)
    ckpt_dir = out / "checkpoint-best"

    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2)
    if resume and (ckpt_dir / "model.safetensors").exists():
        from safetensors.torch import load_file
        model.load_state_dict(load_file(ckpt_dir / "model.safetensors"))
        print(f"[train-cpu] resumed from {ckpt_dir}")

    device = torch.device("cpu")
    dtype = torch.bfloat16 if bf16 and torch.cpu._is_bf16_supported() else torch.float32
    model.to(device)

    train_ds = RegisterDataset(train_items, tokenizer, max_length)
    val_ds = RegisterDataset(val_items, tokenizer, max_length)
    test_ds = RegisterDataset(test_items, tokenizer, max_length)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers, pin_memory=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size * 2, num_workers=num_workers)
    test_loader = DataLoader(test_ds, batch_size=batch_size * 2, num_workers=num_workers)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    total_steps = max(1, len(train_loader) // grad_accum) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(0.06 * total_steps), num_training_steps=total_steps)

    best_val_f1 = -1.0
    log_path = out / "training_log.jsonl"
    log_path.write_text("", encoding="utf-8")

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for step, batch in enumerate(train_loader):
            with torch.autocast(device_type="cpu", dtype=dtype):
                outputs = model(
                    input_ids=batch["input_ids"].to(device),
                    attention_mask=batch["attention_mask"].to(device),
                    labels=batch["labels"].to(device),
                )
                loss = outputs.loss / grad_accum
            loss.backward()
            running_loss += loss.item() * grad_accum
            if (step + 1) % grad_accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
            if step % 50 == 0:
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"epoch": epoch, "step": step, "loss": running_loss / (step + 1),
                                        "lr": scheduler.get_last_lr()[0]}) + "\n")

        # Validation
        model.eval()
        val_preds, val_labels = [], []
        with torch.no_grad():
            for batch in val_loader:
                with torch.autocast(device_type="cpu", dtype=dtype):
                    logits = model(input_ids=batch["input_ids"].to(device),
                                   attention_mask=batch["attention_mask"].to(device)).logits
                val_preds.extend(logits.argmax(-1).cpu().tolist())
                val_labels.extend(batch["labels"].cpu().tolist())
        p, r, f, _ = precision_recall_fscore_support(val_labels, val_preds, average="binary", zero_division=0)
        acc = accuracy_score(val_labels, val_preds)
        print(f"[train-cpu] epoch {epoch}: val P={p:.3f} R={r:.3f} F1={f:.3f} Acc={acc:.3f}")

        if f > best_val_f1:
            best_val_f1 = f
            ckpt_dir.mkdir(exist_ok=True)
            from safetensors.torch import save_file
            save_file(model.state_dict(), ckpt_dir / "model.safetensors")
            tokenizer.save_pretrained(out)
            model.config.save_pretrained(out)

        if best_val_f1 < 0.78 and epoch == 0:
            # spec §5.3.2.a quality gate: abort early
            print(f"[train-cpu] WARN val F1 {best_val_f1:.3f} < 0.78 after epoch 0; aborting pair")
            break

    # Test (with best checkpoint)
    from safetensors.torch import load_file
    model.load_state_dict(load_file(ckpt_dir / "model.safetensors"))
    model.eval()
    test_preds, test_labels = [], []
    with torch.no_grad():
        for batch in test_loader:
            with torch.autocast(device_type="cpu", dtype=dtype):
                logits = model(input_ids=batch["input_ids"].to(device),
                               attention_mask=batch["attention_mask"].to(device)).logits
            test_preds.extend(logits.argmax(-1).cpu().tolist())
            test_labels.extend(batch["labels"].cpu().tolist())
    tp, tr, tf, _ = precision_recall_fscore_support(test_labels, test_preds, average="binary", zero_division=0)
    tacc = accuracy_score(test_labels, test_preds)
    metrics = {
        "precision": round(tp, 4), "recall": round(tr, 4), "f1": round(tf, 4), "accuracy": round(tacc, 4),
        "best_val_f1": round(best_val_f1, 4),
        "model": model_name, "device_trained_on": "cpu",
        "discipline": discipline, "language": language,
        "epochs": epochs, "batch_size": batch_size, "grad_accum": grad_accum, "lr": lr,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    from safetensors.torch import save_file
    save_file(model.state_dict(), out / "model.safetensors")
    return metrics

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-root", required=True, type=Path)
    ap.add_argument("--output-root", required=True, type=Path)
    ap.add_argument("--languages", required=True, help="comma-separated")
    ap.add_argument("--disciplines", required=True, help="comma-separated")
    ap.add_argument("--only-pair", default=None)
    ap.add_argument("--model", default="microsoft/mDeBERTa-v3-small")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--bf16", action="store_true")
    ap.add_argument("--num-workers", type=int, default=12)
    ap.add_argument("--resume-from-checkpoint", default="auto")
    ap.add_argument("--log-to-tensorboard", default=None)
    args = ap.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest = {"models": []}
    manifest_path = args.output_root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if args.only_pair:
        d, l = args.only_pair.split(":", 1)
        m = train_one_pair(discipline=d, language=l, corpus_root=args.corpus_root, output_root=args.output_root,
                           model_name=args.model, epochs=args.epochs, batch_size=args.batch_size,
                           grad_accum=args.grad_accum, lr=args.lr, num_workers=args.num_workers,
                           bf16=args.bf16, resume=(args.resume_from_checkpoint == "auto"))
        manifest["models"].append({"name": f"register_{d}_{l}", **m, "trained_at": time.time()})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return

    for d in args.disciplines.split(","):
        for l in args.languages.split(","):
            try:
                m = train_one_pair(discipline=d.strip(), language=l.strip(),
                                   corpus_root=args.corpus_root, output_root=args.output_root,
                                   model_name=args.model, epochs=args.epochs,
                                   batch_size=args.batch_size, grad_accum=args.grad_accum,
                                   lr=args.lr, num_workers=args.num_workers, bf16=args.bf16,
                                   resume=(args.resume_from_checkpoint == "auto"))
                manifest["models"] = [m for m in manifest["models"] if m["name"] != f"register_{d}_{l}"]
                manifest["models"].append({"name": f"register_{d}_{l}", **m, "trained_at": time.time()})
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[train-cpu] {d}/{l} FAILED: {e}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
pytest tests/discriminator/test_cpu_training_smoke.py -v
git add scripts/train_register_classifier_cpu.py tests/discriminator/test_cpu_training_smoke.py
git commit -m "feat(B5): §5.3.2.a CPU training script (mDeBERTa-v3-small, bf16, Xeon 8368)"
```

## Task 7: GPU training script — `train_register_classifier_gpu.py`

**Files:**
- Create: `scripts/train_register_classifier_gpu.py`
- Test: `tests/discriminator/test_gpu_training_smoke.py` (cuda-skip if no GPU)

- [ ] **Step 1: Write smoke test**

```python
# tests/discriminator/test_gpu_training_smoke.py
import json
import pytest
import torch
from pathlib import Path

@pytest.mark.skipif(not torch.cuda.is_available(), reason="no GPU")
def test_gpu_training_smoke_with_tiny_dataset(tmp_path):
    corpus = tmp_path / "corpus" / "chemistry" / "en"
    corpus.mkdir(parents=True)
    train = [{"text": f"sample {i}", "label": i % 2, "paper_id": f"p{i}"} for i in range(40)]
    val = [{"text": f"val {i}", "label": i % 2, "paper_id": f"v{i}"} for i in range(10)]
    test = [{"text": f"test {i}", "label": i % 2, "paper_id": f"t{i}"} for i in range(10)]
    for name, lst in [("train", train), ("val", val), ("test", test)]:
        (corpus / f"{name}.jsonl").write_text("\n".join(json.dumps(x) for x in lst), encoding="utf-8")

    import subprocess, sys
    result = subprocess.run([
        sys.executable, "scripts/train_register_classifier_gpu.py",
        "--corpus-root", str(tmp_path / "corpus"),
        "--output-root", str(tmp_path / "out"),
        "--languages", "en", "--disciplines", "chemistry",
        "--model", "prajjwal1/bert-tiny",
        "--epochs", "1", "--batch-size", "2", "--grad-accum", "1",
    ], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Implement (same shape as CPU script but with fp16 + cuda)**

```python
# scripts/train_register_classifier_gpu.py
"""Vedix — Layer B classifier training (GPU path, §5.3.2.b).

Target hardware: NVIDIA RTX 4060 8 GB or any GPU with ≥ 8 GB VRAM.
Default model: xlm-roberta-base (278M params, ~1.1 GB fp16 checkpoint).
Mixed precision: fp16 via torch.cuda.amp.
Gradient checkpointing enabled by default to fit in 8 GB.
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
import torch
from torch.utils.data import DataLoader

# Reuse the Dataset class from the CPU script
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_register_classifier_cpu import RegisterDataset, _read_jsonl

def train_one_pair_gpu(*, discipline: str, language: str, corpus_root: Path, output_root: Path,
                       model_name: str, epochs: int, batch_size: int, grad_accum: int, lr: float,
                       fp16: bool, gradient_checkpointing: bool, max_length: int = 512,
                       resume: bool = True) -> dict:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
    from sklearn.metrics import precision_recall_fscore_support, accuracy_score

    pair_dir = corpus_root / discipline / language
    train_items = _read_jsonl(pair_dir / "train.jsonl")
    val_items = _read_jsonl(pair_dir / "val.jsonl")
    test_items = _read_jsonl(pair_dir / "test.jsonl")

    out = output_root / f"register_{discipline}_{language}"
    out.mkdir(parents=True, exist_ok=True)
    ckpt_dir = out / "checkpoint-best"

    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2)
    if gradient_checkpointing:
        model.gradient_checkpointing_enable()
    if resume and (ckpt_dir / "model.safetensors").exists():
        from safetensors.torch import load_file
        model.load_state_dict(load_file(ckpt_dir / "model.safetensors"))
        print(f"[train-gpu] resumed from {ckpt_dir}")

    device = torch.device("cuda:0")
    model.to(device)

    train_ds = RegisterDataset(train_items, tokenizer, max_length)
    val_ds = RegisterDataset(val_items, tokenizer, max_length)
    test_ds = RegisterDataset(test_items, tokenizer, max_length)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size * 2, num_workers=2, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=batch_size * 2, num_workers=2, pin_memory=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    total_steps = max(1, len(train_loader) // grad_accum) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(0.06 * total_steps), num_training_steps=total_steps)
    scaler = torch.cuda.amp.GradScaler(enabled=fp16)

    best_val_f1 = -1.0
    log_path = out / "training_log.jsonl"
    log_path.write_text("", encoding="utf-8")

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for step, batch in enumerate(train_loader):
            with torch.cuda.amp.autocast(enabled=fp16):
                outputs = model(
                    input_ids=batch["input_ids"].to(device, non_blocking=True),
                    attention_mask=batch["attention_mask"].to(device, non_blocking=True),
                    labels=batch["labels"].to(device, non_blocking=True),
                )
                loss = outputs.loss / grad_accum
            scaler.scale(loss).backward()
            running_loss += loss.item() * grad_accum
            if (step + 1) % grad_accum == 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            if step % 50 == 0:
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"epoch": epoch, "step": step, "loss": running_loss / (step + 1),
                                        "lr": scheduler.get_last_lr()[0],
                                        "gpu_mem_mb": torch.cuda.max_memory_allocated() / 1e6}) + "\n")

        # Validation
        model.eval()
        val_preds, val_labels = [], []
        with torch.no_grad():
            for batch in val_loader:
                with torch.cuda.amp.autocast(enabled=fp16):
                    logits = model(input_ids=batch["input_ids"].to(device),
                                   attention_mask=batch["attention_mask"].to(device)).logits
                val_preds.extend(logits.argmax(-1).cpu().tolist())
                val_labels.extend(batch["labels"].cpu().tolist())
        p, r, f, _ = precision_recall_fscore_support(val_labels, val_preds, average="binary", zero_division=0)
        acc = accuracy_score(val_labels, val_preds)
        print(f"[train-gpu] epoch {epoch}: val P={p:.3f} R={r:.3f} F1={f:.3f} Acc={acc:.3f}")
        if f > best_val_f1:
            best_val_f1 = f
            ckpt_dir.mkdir(exist_ok=True)
            from safetensors.torch import save_file
            save_file(model.state_dict(), ckpt_dir / "model.safetensors")
            tokenizer.save_pretrained(out)
            model.config.save_pretrained(out)
        if best_val_f1 < 0.78 and epoch == 0:
            print(f"[train-gpu] WARN val F1 {best_val_f1:.3f} < 0.78 after epoch 0; aborting pair")
            break

    # Test
    from safetensors.torch import load_file
    model.load_state_dict(load_file(ckpt_dir / "model.safetensors"))
    model.eval()
    test_preds, test_labels = [], []
    with torch.no_grad():
        for batch in test_loader:
            with torch.cuda.amp.autocast(enabled=fp16):
                logits = model(input_ids=batch["input_ids"].to(device),
                               attention_mask=batch["attention_mask"].to(device)).logits
            test_preds.extend(logits.argmax(-1).cpu().tolist())
            test_labels.extend(batch["labels"].cpu().tolist())
    tp, tr, tf, _ = precision_recall_fscore_support(test_labels, test_preds, average="binary", zero_division=0)
    tacc = accuracy_score(test_labels, test_preds)
    gpu_name = torch.cuda.get_device_properties(0).name
    metrics = {
        "precision": round(tp, 4), "recall": round(tr, 4), "f1": round(tf, 4), "accuracy": round(tacc, 4),
        "best_val_f1": round(best_val_f1, 4),
        "model": model_name, "device_trained_on": f"cuda:0 {gpu_name}",
        "discipline": discipline, "language": language,
        "epochs": epochs, "batch_size": batch_size, "grad_accum": grad_accum, "lr": lr,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    from safetensors.torch import save_file
    save_file(model.state_dict(), out / "model.safetensors")
    return metrics

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-root", required=True, type=Path)
    ap.add_argument("--output-root", required=True, type=Path)
    ap.add_argument("--languages", required=True)
    ap.add_argument("--disciplines", required=True)
    ap.add_argument("--only-pair", default=None)
    ap.add_argument("--model", default="xlm-roberta-base")
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--fp16", action="store_true", default=True)
    ap.add_argument("--gradient-checkpointing", action="store_true", default=True)
    ap.add_argument("--resume-from-checkpoint", default="auto")
    ap.add_argument("--log-to-tensorboard", default=None)
    args = ap.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest = {"models": []}
    manifest_path = args.output_root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if args.only_pair:
        d, l = args.only_pair.split(":", 1)
        m = train_one_pair_gpu(discipline=d, language=l, corpus_root=args.corpus_root, output_root=args.output_root,
                               model_name=args.model, epochs=args.epochs, batch_size=args.batch_size,
                               grad_accum=args.grad_accum, lr=args.lr,
                               fp16=args.fp16, gradient_checkpointing=args.gradient_checkpointing,
                               resume=(args.resume_from_checkpoint == "auto"))
        manifest["models"].append({"name": f"register_{d}_{l}", **m, "trained_at": time.time()})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return

    for d in args.disciplines.split(","):
        for l in args.languages.split(","):
            try:
                m = train_one_pair_gpu(discipline=d.strip(), language=l.strip(),
                                       corpus_root=args.corpus_root, output_root=args.output_root,
                                       model_name=args.model, epochs=args.epochs,
                                       batch_size=args.batch_size, grad_accum=args.grad_accum,
                                       lr=args.lr, fp16=args.fp16,
                                       gradient_checkpointing=args.gradient_checkpointing,
                                       resume=(args.resume_from_checkpoint == "auto"))
                manifest["models"] = [m for m in manifest["models"] if m["name"] != f"register_{d}_{l}"]
                manifest["models"].append({"name": f"register_{d}_{l}", **m, "trained_at": time.time()})
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[train-gpu] {d}/{l} FAILED: {e}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
pytest tests/discriminator/test_gpu_training_smoke.py -v
git add scripts/train_register_classifier_gpu.py tests/discriminator/test_gpu_training_smoke.py
git commit -m "feat(B5): §5.3.2.b GPU training script (xlm-roberta-base, fp16, RTX 4060 8GB)"
```

## Task 8: Auto-dispatcher — `train_register_classifier.py`

**Files:**
- Create: `scripts/train_register_classifier.py`

- [ ] **Step 1: Implement**

```python
# scripts/train_register_classifier.py
"""Vedix — Layer B classifier auto-dispatcher (§5.3.2.c).

Detects available hardware and dispatches to train_register_classifier_gpu.py
or train_register_classifier_cpu.py.

Usage:
  python scripts/train_register_classifier.py --auto                     # let it pick
  python scripts/train_register_classifier.py --force-cpu                # ignore GPU
  python scripts/train_register_classifier.py --only-pair chemistry:en   # one pair
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

def detect_hardware() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024**3)
            if vram_gb >= 7:
                return "gpu"
            print(f"[auto] GPU detected but only {vram_gb:.1f}GB VRAM; falling back to CPU")
    except ImportError:
        pass
    import psutil
    cpu_cores = psutil.cpu_count(logical=False) or 0
    ram_gb = psutil.virtual_memory().total / (1024**3)
    if cpu_cores >= 16 and ram_gb >= 64:
        return "cpu"
    raise SystemExit(f"hardware insufficient: cpu_cores={cpu_cores}, ram={ram_gb:.1f}GB, no GPU. "
                     f"Use a workstation with ≥16 cores + 64GB RAM or a GPU with ≥7GB VRAM. "
                     f"Or use Vedix.ai SaaS hosted training (Pro tier).")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-root", required=True, type=Path)
    ap.add_argument("--output-root", required=True, type=Path)
    ap.add_argument("--languages", default="en,ru,es,de,fr,zh,ja")
    ap.add_argument("--disciplines", default="chemistry,biology,medicine,physics,mathematics,geology,computer_science,humanities")
    ap.add_argument("--only-pair", default=None)
    ap.add_argument("--auto", action="store_true", default=True)
    ap.add_argument("--force-cpu", action="store_true")
    ap.add_argument("--force-gpu", action="store_true")
    args = ap.parse_args()

    if args.force_cpu:
        target = "cpu"
    elif args.force_gpu:
        target = "gpu"
    else:
        target = detect_hardware()

    script = Path(__file__).resolve().parent / (
        "train_register_classifier_gpu.py" if target == "gpu" else "train_register_classifier_cpu.py"
    )
    print(f"[auto] dispatching to {script.name}")

    cmd = [sys.executable, str(script),
           "--corpus-root", str(args.corpus_root),
           "--output-root", str(args.output_root),
           "--languages", args.languages,
           "--disciplines", args.disciplines]
    if args.only_pair:
        cmd += ["--only-pair", args.only_pair]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/train_register_classifier.py
git commit -m "feat(B5): §5.3.2.c auto-dispatcher (hardware detection → CPU or GPU path)"
```

## Task 9: Layer B inference + model fetch/publish CLI

**Files:**
- Modify: `plugins/vedix/mcp/lib/orchestrator/register_discriminator.py` (add LayerB class)
- Create: `plugins/vedix/scripts/vedix_model.py` (CLI: `vedix model fetch / publish`)
- Test: `tests/discriminator/test_layer_b.py`

- [ ] **Step 1: Write test**

```python
# tests/discriminator/test_layer_b.py
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

@pytest.fixture
def fake_model_dir(tmp_path):
    d = tmp_path / "register_chemistry_en"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"model_type": "bert", "num_labels": 2}))
    (d / "metrics.json").write_text(json.dumps({"f1": 0.91}))
    return d

def test_layer_b_loads_and_judges(fake_model_dir, monkeypatch):
    from plugins.vedix.mcp.lib.orchestrator.register_discriminator import LayerB
    fake_model = MagicMock()
    fake_logits = MagicMock()
    fake_logits.argmax.return_value.item.return_value = 1
    fake_logits.softmax.return_value.cpu.return_value.numpy.return_value = [[0.1, 0.9]]
    fake_model.return_value.logits = fake_logits
    fake_tokenizer = MagicMock(return_value={"input_ids": MagicMock(), "attention_mask": MagicMock()})
    with patch("plugins.vedix.mcp.lib.orchestrator.register_discriminator.AutoModelForSequenceClassification.from_pretrained", return_value=fake_model), \
         patch("plugins.vedix.mcp.lib.orchestrator.register_discriminator.AutoTokenizer.from_pretrained", return_value=fake_tokenizer):
        layer = LayerB(model_dir=fake_model_dir)
        v = layer.judge("Some paragraph.")
        assert v.layer == "B"
        assert isinstance(v.pass_, bool)
```

- [ ] **Step 2: Implement Layer B**

```python
# Append to plugins/vedix/mcp/lib/orchestrator/register_discriminator.py
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class LayerB:
    def __init__(self, *, model_dir: Path):
        self.model_dir = Path(model_dir)
        self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir), use_fast=True)
        self._model = AutoModelForSequenceClassification.from_pretrained(str(self.model_dir))
        self._device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device).eval()

    def judge(self, paragraph: str, threshold: float = 0.5) -> Verdict:
        enc = self._tokenizer(paragraph, truncation=True, max_length=256, padding="max_length", return_tensors="pt")
        with torch.no_grad():
            logits = self._model(input_ids=enc["input_ids"].to(self._device),
                                  attention_mask=enc["attention_mask"].to(self._device)).logits
        probs = logits.softmax(-1).cpu().numpy()[0]
        in_register_prob = float(probs[1])
        return Verdict(
            pass_=in_register_prob >= threshold,
            score=round(in_register_prob, 3),
            explanation=f"P(in-register) = {in_register_prob:.3f} vs threshold {threshold}",
            layer="B",
        )

class HybridDiscriminator:
    """Layer A (retrieval) + Layer B (trained) — both must pass for the paragraph to be in-register."""
    def __init__(self, *, corpus_root: Path, classifiers_root: Path, discipline: str, language: str):
        self.layer_a = LayerA(corpus_root=corpus_root, discipline=discipline, language=language)
        model_dir = classifiers_root / f"register_{discipline}_{language}"
        self.layer_b = LayerB(model_dir=model_dir) if model_dir.exists() else None

    def judge(self, paragraph: str) -> dict:
        va = self.layer_a.judge(paragraph)
        result = {"layer_a": {"pass": va.pass_, "score": va.score, "explanation": va.explanation}}
        if self.layer_b:
            vb = self.layer_b.judge(paragraph)
            result["layer_b"] = {"pass": vb.pass_, "score": vb.score, "explanation": vb.explanation}
            result["overall_pass"] = va.pass_ and vb.pass_
        else:
            result["overall_pass"] = va.pass_
        return result
```

- [ ] **Step 3: Implement model CLI**

```python
# plugins/vedix/scripts/vedix_model.py
"""`vedix model fetch/publish/list` — distribute trained classifiers."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import httpx

REGISTRY_URL = os.environ.get("VEDIX_MODEL_REGISTRY", "https://models.vedix.ai/v1")

def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

def fetch(*, languages: list[str], disciplines: list[str]) -> None:
    out = _home() / ".vedix" / "classifiers"
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120) as client:
        for d in disciplines:
            for l in languages:
                name = f"register_{d}_{l}"
                pair_dir = out / name
                pair_dir.mkdir(exist_ok=True)
                for fn in ("model.safetensors", "config.json", "tokenizer.json", "metrics.json"):
                    url = f"{REGISTRY_URL}/{name}/{fn}"
                    try:
                        r = client.get(url)
                        if r.status_code == 200:
                            (pair_dir / fn).write_bytes(r.content)
                            print(f"  fetched {name}/{fn}")
                        else:
                            print(f"  miss {name}/{fn} (status {r.status_code})")
                    except Exception as e:
                        print(f"  error {name}/{fn}: {e}")

def publish(*, name: str, model_dir: Path) -> None:
    if not (model_dir / "metrics.json").exists():
        raise SystemExit(f"{model_dir} missing metrics.json — cannot publish unvalidated model")
    metrics = json.loads((model_dir / "metrics.json").read_text(encoding="utf-8"))
    if metrics.get("f1", 0) < 0.85:
        raise SystemExit(f"f1={metrics.get('f1')} < 0.85 — refusing to publish")
    with httpx.Client(timeout=300) as client:
        for fn in ("model.safetensors", "config.json", "tokenizer.json", "metrics.json"):
            f = model_dir / fn
            if not f.exists(): continue
            r = client.post(f"{REGISTRY_URL}/{name}/{fn}", files={"file": f.open("rb")})
            print(f"  POST {name}/{fn}: {r.status_code}")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    fp = sub.add_parser("fetch"); fp.add_argument("--languages", default="en,ru,es,de,fr,zh,ja"); fp.add_argument("--disciplines", default="chemistry,biology,medicine,physics,mathematics,geology,computer_science,humanities")
    pp = sub.add_parser("publish"); pp.add_argument("--name", required=True); pp.add_argument("--model-dir", required=True, type=Path)
    sub.add_parser("list")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(languages=args.languages.split(","), disciplines=args.disciplines.split(","))
    elif args.cmd == "publish":
        publish(name=args.name, model_dir=args.model_dir)
    elif args.cmd == "list":
        out = _home() / ".vedix" / "classifiers"
        for d in sorted(out.glob("register_*")):
            m = json.loads((d / "metrics.json").read_text()) if (d / "metrics.json").exists() else {}
            print(f"{d.name}\tf1={m.get('f1','?')}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
pytest tests/discriminator/test_layer_b.py -v
git add plugins/vedix/mcp/lib/orchestrator/register_discriminator.py plugins/vedix/scripts/vedix_model.py tests/discriminator/test_layer_b.py
git commit -m "feat(B5): Layer B inference + HybridDiscriminator + vedix model fetch/publish CLI"
```

## Task 10: Documentation — user-facing training instructions

**Files:**
- Create: `docs/training/README.md`
- Create: `docs/training/cpu-instructions.md`
- Create: `docs/training/gpu-instructions.md`

- [ ] **Step 1: Write README**

```markdown
# Training the Vedix register classifier locally

Most users will fetch pre-trained classifiers automatically via `vedix model fetch`.
This document is for users who want to retrain locally — either because they need
a discipline+language pair we don't ship yet, or they want to refine the
classifier on their own corpus.

## Hardware paths

Vedix ships two training scripts. Pick the one that matches your hardware:

| Hardware                                              | Script                          | Model               | Time per pair      |
|---|---|---|---|
| **NVIDIA RTX 4060 8 GB** (or any GPU ≥ 8 GB VRAM)     | `train_register_classifier_gpu.py` | `xlm-roberta-base` | 6–10 hours         |
| **Intel Xeon 8368 / 512 GB RAM** (no GPU)             | `train_register_classifier_cpu.py` | `mDeBERTa-v3-small`| 20–28 hours        |
| **Don't know which** — let Vedix choose               | `train_register_classifier.py --auto` | auto-selected    | —                  |

See `cpu-instructions.md` or `gpu-instructions.md` for full command details.

## Workflow (high level)

```bash
# 1. Prepare the corpus (download + extract + dedup + label + split)
python scripts/prepare_corpus.py --target-count 150

# 2. Train (auto-detect hardware)
python scripts/train_register_classifier.py --auto \
  --corpus-root ~/.vedix/corpus \
  --output-root ~/.vedix/classifiers

# 3. (Optional) Publish high-quality models back to the community
vedix model publish register_chemistry_en --model-dir ~/.vedix/classifiers/register_chemistry_en
```

## Quality gate

Training auto-aborts a (discipline, language) pair if val F1 < 0.78 after 1 epoch.
This signals a corpus problem (too few papers, bad language verification,
weak adversarial negatives). Fix the corpus and re-run.

## Where things live

| Path | What |
|---|---|
| `~/.vedix/corpus/<discipline>/<lang>/` | Prepared corpus (acquisition + dedup + train/val/test splits) |
| `~/.vedix/classifiers/register_<discipline>_<lang>/` | Trained model checkpoints + metrics |
| `~/.vedix/classifiers/manifest.json` | Per-model metadata (F1, training timestamp, device used) |
| `~/.vedix/classifiers/tb_logs/` | TensorBoard event files |
```

- [ ] **Step 2: Write CPU instructions**

```markdown
# CPU training (Xeon 8368, no GPU)

## Hardware target

- Intel Xeon 8368 (38 cores / 76 threads / 512 GB RAM) — confirmed working
- Any modern Xeon / EPYC with ≥ 64 logical cores and ≥ 128 GB RAM should work

## Time budget

- Per (discipline, language) pair: ~20–28 hours
- All 56 pairs sequentially: ~7–9 days
- All 56 pairs with `--parallel-pairs 4`: ~2–3 days

## Command — train everything

```bash
source ~/.vedix/repo/venv/bin/activate

python ~/.vedix/repo/plugins/vedix/scripts/train_register_classifier_cpu.py \
  --corpus-root ~/.vedix/corpus \
  --output-root ~/.vedix/classifiers \
  --languages en,ru,es,de,fr,zh,ja \
  --disciplines chemistry,biology,medicine,physics,mathematics,geology,computer_science,humanities \
  --model microsoft/mDeBERTa-v3-small \
  --batch-size 16 --grad-accum 4 \
  --lr 2e-5 --epochs 3 \
  --bf16 \
  --num-workers 12 \
  --resume-from-checkpoint auto \
  --log-to-tensorboard ~/.vedix/classifiers/tb_logs
```

## Command — train one pair

```bash
python .../train_register_classifier_cpu.py \
  --corpus-root ~/.vedix/corpus --output-root ~/.vedix/classifiers \
  --languages en --disciplines chemistry \
  --only-pair chemistry:en
```

## Resume after interruption

The `--resume-from-checkpoint auto` flag picks up at the last best-val checkpoint.
Just re-run the same command.

## Memory expectations

mDeBERTa-v3-small consumes ~5 GB RAM per training process. Per the recommended
`--parallel-pairs 4`, peak RAM ~24 GB total — comfortably within 512 GB.

## Output

```
~/.vedix/classifiers/register_<discipline>_<lang>/
├── model.safetensors        # ~530 MB
├── tokenizer.json
├── config.json
├── training_log.jsonl
├── metrics.json
└── checkpoint-best/
~/.vedix/classifiers/manifest.json
~/.vedix/classifiers/tb_logs/
```
```

- [ ] **Step 3: Write GPU instructions**

```markdown
# GPU training (RTX 4060 8 GB or similar)

## Hardware target

- NVIDIA RTX 4060 8 GB — confirmed working
- Any NVIDIA GPU with ≥ 8 GB VRAM should work

## Time budget

- Per (discipline, language) pair: ~6–10 hours
- All 56 pairs sequentially: ~2–3 weeks

Recommended: train 8–10 pairs per weekend, pause + resume.

## Command — train everything

```bash
source ~/.vedix/repo/venv/bin/activate

python ~/.vedix/repo/plugins/vedix/scripts/train_register_classifier_gpu.py \
  --corpus-root ~/.vedix/corpus \
  --output-root ~/.vedix/classifiers \
  --languages en,ru,es,de,fr,zh,ja \
  --disciplines chemistry,biology,medicine,physics,mathematics,geology,computer_science,humanities \
  --model xlm-roberta-base \
  --batch-size 4 --grad-accum 16 \
  --lr 2e-5 --epochs 3 \
  --fp16 \
  --gradient-checkpointing \
  --resume-from-checkpoint auto \
  --log-to-tensorboard ~/.vedix/classifiers/tb_logs
```

## Memory expectations (RTX 4060 8 GB)

Peak VRAM ~7.1 GB with the recommended flags. If you see CUDA OOM:

- Reduce `--max-length` from 512 to 384 (smaller activation tensors)
- Or reduce `--batch-size` from 4 to 2 (and double `--grad-accum`)
- Or remove `--gradient-checkpointing` only if you have more VRAM

Other GPUs:

| GPU | Recommended batch-size × grad-accum | Notes |
|---|---|---|
| RTX 4060 8 GB | 4 × 16 | bring `--gradient-checkpointing` |
| RTX 4070 12 GB | 8 × 8 | gradient-checkpointing optional |
| RTX 4090 24 GB | 32 × 2 | drop gradient-checkpointing |
| H100 80 GB | 64 × 1 | drop gradient-checkpointing; remove --fp16 if you want bf16 |

## Output

Same layout as CPU path. The `metrics.json` records the exact GPU used:

```json
{ "device_trained_on": "cuda:0 NVIDIA GeForce RTX 4060", "f1": 0.91, ... }
```
```

- [ ] **Step 4: Commit**

```bash
git add docs/training/
git commit -m "docs(B5): training instructions (README, cpu-instructions, gpu-instructions)"
```

## Block 5 acceptance criteria

- [ ] All `tests/discriminator/` tests pass
- [ ] `python scripts/prepare_corpus.py --only-pair chemistry:en --target-count 30` runs end-to-end on real MCPs and produces `~/.vedix/corpus/chemistry/en/{train,val,test}.jsonl` + `corpus_stats.json`
- [ ] `python scripts/train_register_classifier.py --auto --only-pair chemistry:en` selects the right script and reaches val F1 > 0.78 on a 50-paper toy corpus
- [ ] `python scripts/train_register_classifier_cpu.py --only-pair chemistry:en` produces `~/.vedix/classifiers/register_chemistry_en/model.safetensors`
- [ ] (GPU available) `python scripts/train_register_classifier_gpu.py --only-pair physics:en` similarly produces the GPU-trained model
- [ ] `HybridDiscriminator(corpus_root=..., classifiers_root=..., discipline="chemistry", language="en").judge("...")` returns both Layer A and Layer B verdicts
- [ ] `vedix model fetch` downloads canonical models from `models.vedix.ai` (mock the registry in CI)
- [ ] `docs/training/` README + cpu-instructions + gpu-instructions all populated
- [ ] Git tag `v3.0.0-block5` pushed

# Block 3 — Novel Rigor Tracks Implementation Plan (§4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Implement the 7 clean-room rigor tracks from spec §4: failure-mode learning (§4.1), citation graph analytics (§4.2), counterfactual citation probing (§4.3), adversarial multi-pass review (§4.4), semantic revision diff (§4.5), pre-registration replay (§4.6), provenance ledger + auto-disclosure (§4.7).

**Architecture:** Each track is one Python module under `orchestrator/`. The orchestrator pipeline wires them as standard phase hooks (pre-phase / post-phase). All emit JSON artifacts under `~/.vedix/jobs/<job_id>/rigor/`. Each artifact has a corresponding `<artifact>.rationale.md` per §5.4 (handled by Block 4). The hard-gates (citation graph severity, prereg violations) raise `RigorBlockError` which the pipeline catches and surfaces to the user.

**Tech Stack:** `sentence-transformers` (multilingual-e5), `hdbscan`, `networkx`, `scipy`, `numpy`. LLM-judge calls go through B2's router. Crossref + DataCite via `httpx`.

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §4.1–§4.7.

---

## File structure

```
plugins/vedix/mcp/lib/orchestrator/
├── failure_mode_learning.py       # §4.1
├── citation_graph.py              # §4.2
├── counterfactual_probe.py        # §4.3
├── adversarial_review.py          # §4.4
├── semantic_revision_diff.py      # §4.5
├── prereg_replay.py               # §4.6
└── provenance_ledger.py           # §4.7
scripts/
└── learn_failure_modes.py         # Monthly batch for §4.1
templates/
└── ai_disclosure/                 # Per-venue disclosure templates for §4.7
    ├── nature.tex
    ├── elsevier.tex
    └── ... (one per venue)
```

## Task 1: Failure-Mode Learning (§4.1)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/failure_mode_learning.py`
- Create: `scripts/learn_failure_modes.py`
- Test: `tests/rigor/test_failure_mode_learning.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rigor/test_failure_mode_learning.py
import json
from pathlib import Path
import pytest
from plugins.vedix.mcp.lib.orchestrator.failure_mode_learning import (
    FailureCorpus, cluster_failures, mark_failure, load_active_modes
)

def test_mark_failure_writes_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    mark_failure(job_id="abc123", description="hallucinated DOI for Smith 2024 paper")
    fc = FailureCorpus()
    entries = fc.list_all()
    assert len(entries) == 1
    assert entries[0]["job_id"] == "abc123"
    assert "hallucinated" in entries[0]["description"]

def test_cluster_failures_produces_named_clusters(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Inject 30 synthetic failures across 3 clusters
    citation_fail = ["hallucinated DOI for paper X"] * 10
    code_fail = ["ImportError on torch in experiment.py"] * 10
    method_fail = ["fabricated experimental method"] * 10
    for desc in citation_fail + code_fail + method_fail:
        mark_failure(job_id=f"j{hash(desc)}", description=desc)
    clusters = cluster_failures(min_cluster_size=5)
    assert len(clusters) >= 2  # HDBSCAN should find at least 2 real clusters
```

- [ ] **Step 2: Run — verify fails**

- [ ] **Step 3: Implement module**

```python
# plugins/vedix/mcp/lib/orchestrator/failure_mode_learning.py
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Optional

def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

def _corpus_dir() -> Path:
    d = _home() / ".vedix" / "failure_corpus"
    d.mkdir(parents=True, exist_ok=True)
    return d

def mark_failure(*, job_id: str, description: str, phase: Optional[str] = None) -> Path:
    """User-invoked: mark a job as failed with a description."""
    entry = {
        "ts": time.time(),
        "job_id": job_id,
        "description": description,
        "phase": phase,
    }
    out = _corpus_dir() / f"{job_id}_{int(entry['ts'])}.json"
    out.write_text(json.dumps(entry), encoding="utf-8")
    return out

class FailureCorpus:
    def __init__(self):
        self.dir = _corpus_dir()

    def list_all(self) -> list[dict]:
        entries = []
        for f in self.dir.glob("*.json"):
            entries.append(json.loads(f.read_text(encoding="utf-8")))
        return sorted(entries, key=lambda e: e["ts"])

def cluster_failures(min_cluster_size: int = 5) -> list[dict]:
    """Run sentence-transformers + HDBSCAN over the failure corpus, return clusters."""
    from sentence_transformers import SentenceTransformer
    import hdbscan
    import numpy as np

    corpus = FailureCorpus().list_all()
    if len(corpus) < min_cluster_size:
        return []

    model = SentenceTransformer("intfloat/multilingual-e5-small")
    descriptions = [e["description"] for e in corpus]
    embeddings = model.encode(["query: " + d for d in descriptions], normalize_embeddings=True)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(embeddings)

    clusters: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if label == -1:  # noise
            continue
        clusters.setdefault(int(label), []).append(idx)

    out = []
    for label, indices in clusters.items():
        sample_descriptions = [descriptions[i] for i in indices[:3]]
        out.append({
            "cluster_id": label,
            "size": len(indices),
            "sample_descriptions": sample_descriptions,
            "indices": indices,
        })
    return sorted(out, key=lambda c: c["size"], reverse=True)

def load_active_modes(version: int = 1) -> list[dict]:
    """Load the currently-active failure-mode set."""
    p = _home() / ".vedix" / "failure_modes" / f"v{version}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))["modes"]
```

- [ ] **Step 4: Run — verify passes**

- [ ] **Step 5: Implement monthly batch script**

```python
# scripts/learn_failure_modes.py
"""Monthly batch: cluster the failure corpus and emit a new active-mode set."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "vedix" / "mcp" / "lib"))
from orchestrator.failure_mode_learning import cluster_failures, _home

def main():
    clusters = cluster_failures(min_cluster_size=5)
    print(f"[learn] found {len(clusters)} clusters")
    # Take the top 15 active, the rest go to watch-list
    active = clusters[:15]
    watch = clusters[15:]
    out_dir = _home() / ".vedix" / "failure_modes"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Bump version
    existing = sorted(out_dir.glob("v*.json"))
    next_v = int(existing[-1].stem[1:]) + 1 if existing else 1
    out_dir / f"v{next_v}.json"
    payload = {
        "version": next_v,
        "generated_at": time.time(),
        "active_modes": [
            {
                "cluster_id": c["cluster_id"],
                "synthetic_name": _synthesize_name(c["sample_descriptions"]),
                "size": c["size"],
                "sample_descriptions": c["sample_descriptions"],
                "severity": "warn",  # default; can be hand-edited to "block"
            }
            for c in active
        ],
        "watch_list": [{"cluster_id": c["cluster_id"], "size": c["size"]} for c in watch],
    }
    (out_dir / f"v{next_v}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[learn] wrote {out_dir / f'v{next_v}.json'}")

def _synthesize_name(samples: list[str]) -> str:
    # Compact name from common keywords; can be LLM-rewritten later
    from collections import Counter
    words = []
    for s in samples:
        words.extend(w.lower() for w in s.split() if len(w) > 3)
    top = [w for w, _ in Counter(words).most_common(3)]
    return "_".join(top) if top else "unnamed_cluster"

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/failure_mode_learning.py scripts/learn_failure_modes.py tests/rigor/test_failure_mode_learning.py
git commit -m "feat(B3): §4.1 failure-mode learning — HDBSCAN over failure corpus + monthly batch"
```

## Task 2: Citation graph analytics (§4.2)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/citation_graph.py`
- Test: `tests/rigor/test_citation_graph.py`

- [ ] **Step 1: Write test**

```python
# tests/rigor/test_citation_graph.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.citation_graph import (
    build_graph, density, freshness_gini, venue_diversity,
    self_citation_ratio, chronology_violations, dangling_references, analyze
)

def test_chronology_violation_detected():
    references = {"smith2030": {"year": 2030, "venue": "Nature"}}
    citations_by_para = {"para1": ["smith2030"]}
    paragraphs = {"para1": "we follow smith2030."}
    manuscript_year = 2026
    violations = chronology_violations(references, citations_by_para, manuscript_year)
    assert ("para1", "smith2030", 2030, 2026) in violations

def test_dangling_reference_detected():
    references = {"a2020": {"year": 2020}, "b2021": {"year": 2021}}
    citations_by_para = {"para1": ["a2020"]}  # b2021 is dangling
    dangling = dangling_references(references, citations_by_para)
    assert "b2021" in dangling
    assert "a2020" not in dangling

def test_self_citation_ratio():
    references = {
        "smith2020": {"first_author": "Smith"},
        "jones2021": {"first_author": "Jones"},
        "smith2022": {"first_author": "Smith"},
    }
    citations_by_para = {"para1": ["smith2020", "jones2021", "smith2022"]}
    ratio = self_citation_ratio(references, citations_by_para, manuscript_authors=["Smith"])
    assert ratio == pytest.approx(2/3)

def test_analyze_emits_report():
    references = {"a2020": {"year": 2020, "first_author": "Smith", "venue": "Nature"}}
    citations_by_para = {"para1": ["a2020"]}
    paragraphs = {"para1": "we follow a2020 word " * 30}
    report = analyze(references=references, citations_by_para=citations_by_para,
                     paragraphs=paragraphs, manuscript_year=2026, manuscript_authors=[])
    assert "per_paragraph" in report
    assert "overall" in report
```

- [ ] **Step 2: Run — verify fails**

- [ ] **Step 3: Implement module**

```python
# plugins/vedix/mcp/lib/orchestrator/citation_graph.py
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import networkx as nx
import numpy as np

def build_graph(references: dict[str, dict], citations_by_para: dict[str, list[str]]) -> nx.DiGraph:
    g = nx.DiGraph()
    for r, meta in references.items():
        g.add_node(r, kind="reference", **meta)
    for p, cited in citations_by_para.items():
        g.add_node(p, kind="paragraph")
        for r in cited:
            g.add_edge(p, r)
    return g

def density(paragraph_text: str, n_citations: int) -> float:
    n_words = len(paragraph_text.split())
    return n_citations / max(1, n_words / 100)  # cites per 100 words

def freshness_gini(references: dict[str, dict]) -> float:
    years = [m.get("year") for m in references.values() if m.get("year")]
    if not years:
        return 0.0
    year_counts = Counter(years)
    counts = np.array(sorted(year_counts.values()))
    n = len(counts)
    cum = np.cumsum(counts)
    return float((2 * np.sum((np.arange(1, n + 1)) * counts) - (n + 1) * np.sum(counts)) / (n * np.sum(counts)))

def venue_diversity(references: dict[str, dict]) -> int:
    return len({m.get("venue") for m in references.values() if m.get("venue")})

def self_citation_ratio(references: dict[str, dict], citations_by_para: dict[str, list[str]], manuscript_authors: list[str]) -> float:
    cited_keys = [k for cs in citations_by_para.values() for k in cs]
    if not cited_keys:
        return 0.0
    self_cites = sum(1 for k in cited_keys if references.get(k, {}).get("first_author") in manuscript_authors)
    return self_cites / len(cited_keys)

def chronology_violations(references: dict[str, dict], citations_by_para: dict[str, list[str]], manuscript_year: int) -> list[tuple]:
    violations = []
    for p, cited in citations_by_para.items():
        for k in cited:
            ref_year = references.get(k, {}).get("year")
            if ref_year and ref_year > manuscript_year:
                violations.append((p, k, ref_year, manuscript_year))
    return violations

def dangling_references(references: dict[str, dict], citations_by_para: dict[str, list[str]]) -> list[str]:
    cited = {k for cs in citations_by_para.values() for k in cs}
    return [r for r in references if r not in cited]

def analyze(*, references, citations_by_para, paragraphs, manuscript_year, manuscript_authors) -> dict:
    g = build_graph(references, citations_by_para)
    per_paragraph = {}
    for p, txt in paragraphs.items():
        cs = citations_by_para.get(p, [])
        per_paragraph[p] = {
            "n_citations": len(cs),
            "density_per_100w": round(density(txt, len(cs)), 2),
            "outlier_density": density(txt, len(cs)) > 10 or (density(txt, len(cs)) < 0.5 and len(txt.split()) > 100),
        }
    overall = {
        "n_references": len(references),
        "n_paragraphs": len(paragraphs),
        "freshness_gini": round(freshness_gini(references), 3),
        "venue_diversity": venue_diversity(references),
        "self_citation_ratio": round(self_citation_ratio(references, citations_by_para, manuscript_authors), 3),
        "chronology_violations": chronology_violations(references, citations_by_para, manuscript_year),
        "dangling_references": dangling_references(references, citations_by_para),
    }
    return {"per_paragraph": per_paragraph, "overall": overall}

def write_report(report: dict, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run — verify passes**

```
pytest tests/rigor/test_citation_graph.py -v
```

- [ ] **Step 5: Commit**

```bash
git add plugins/vedix/mcp/lib/orchestrator/citation_graph.py tests/rigor/test_citation_graph.py
git commit -m "feat(B3): §4.2 citation graph analytics — density / Gini / chronology / dangling"
```

## Task 3: Counterfactual citation probing (§4.3)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/counterfactual_probe.py`
- Test: `tests/rigor/test_counterfactual_probe.py`

- [ ] **Step 1: Write test**

```python
# tests/rigor/test_counterfactual_probe.py
import pytest
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.counterfactual_probe import (
    generate_decoy, probe_citation, probe_all
)

@pytest.mark.asyncio
async def test_generate_decoy_returns_plausible():
    real = {"year": 2024, "title": "Effect of solvent polarity on Diels-Alder kinetics"}
    with patch("plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
               new=AsyncMock(return_value=type("R", (), {"content": "Effect of temperature on Diels-Alder yield (Smith 2024)"})())):
        decoy = await generate_decoy(real)
        assert decoy["year"] == 2024
        assert decoy["title"] != real["title"]

@pytest.mark.asyncio
async def test_probe_citation_classifies_load_bearing():
    paragraph = "The reaction follows Diels-Alder kinetics [smith2024]."
    real = {"key": "smith2024", "title": "Diels-Alder kinetics"}
    decoy_title = "Cake recipe optimization"
    with patch("plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
               new=AsyncMock(return_value=type("R", (), {"content": "DIFFERENT"})())):
        verdict = await probe_citation(paragraph=paragraph, citation_key="smith2024", real=real, decoy_title=decoy_title)
        assert verdict["load_bearing"] is True

@pytest.mark.asyncio
async def test_probe_citation_classifies_decorative():
    paragraph = "Many reactions exist [smith2024]."
    real = {"key": "smith2024", "title": "Diels-Alder kinetics"}
    decoy_title = "Cake recipe optimization"
    with patch("plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
               new=AsyncMock(return_value=type("R", (), {"content": "SAME"})())):
        verdict = await probe_citation(paragraph=paragraph, citation_key="smith2024", real=real, decoy_title=decoy_title)
        assert verdict["load_bearing"] is False
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/counterfactual_probe.py
from __future__ import annotations
import json
import re
from pathlib import Path
from .dispatch import dispatch_agent

DECOY_PROMPT = """Given the real citation below, invent a plausible-but-fictional alternative citation
with the same publication year and a thematically-adjacent title. Output JSON with keys: title.

Real: {real_json}
"""

JUDGE_PROMPT = """Read these two variants of the same paragraph. The only difference is which citation is used.

Variant A: {variant_a}
Variant B: {variant_b}

Are these making the same factual claim, or different claims? Respond with exactly "SAME" or "DIFFERENT".
"""

async def generate_decoy(real: dict) -> dict:
    resp = await dispatch_agent(agent_type="decoy-generator",
                                 prompt=DECOY_PROMPT.format(real_json=json.dumps(real)))
    # Parse the title from the LLM response (loose; fallback to substring extraction)
    text = resp.content
    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', text)
    title = title_match.group(1) if title_match else text.strip().split("\n")[0]
    return {"year": real.get("year"), "title": title}

async def probe_citation(*, paragraph: str, citation_key: str, real: dict, decoy_title: str) -> dict:
    variant_a = paragraph  # original
    # Variant B: swap real citation with decoy in the same position
    variant_b = paragraph.replace(real.get("title", citation_key), decoy_title)
    if variant_a == variant_b:
        # Fallback: just append marker
        variant_b = paragraph + f" (Note: cites '{decoy_title}' instead of real source)"
    resp = await dispatch_agent(agent_type="counterfactual-judge",
                                 prompt=JUDGE_PROMPT.format(variant_a=variant_a, variant_b=variant_b))
    verdict_text = resp.content.strip().upper()
    load_bearing = "DIFFERENT" in verdict_text
    return {
        "citation_key": citation_key,
        "load_bearing": load_bearing,
        "decoy_title": decoy_title,
        "judge_response": verdict_text,
    }

async def probe_all(citations_by_para: dict[str, list[str]], references: dict[str, dict],
                    paragraphs: dict[str, str], cache_path: Path | None = None) -> list[dict]:
    cache = {}
    if cache_path and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    results = []
    for para_id, keys in citations_by_para.items():
        para_text = paragraphs.get(para_id, "")
        for k in keys:
            cache_key = f"{k}::{hash(para_text) & 0xffffffff}"
            if cache_key in cache:
                results.append(cache[cache_key])
                continue
            real = {"key": k, **references.get(k, {})}
            decoy = await generate_decoy(real)
            verdict = await probe_citation(paragraph=para_text, citation_key=k, real=real, decoy_title=decoy["title"])
            verdict["paragraph_id"] = para_id
            cache[cache_key] = verdict
            results.append(verdict)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return results
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/rigor/test_counterfactual_probe.py -v
git add plugins/vedix/mcp/lib/orchestrator/counterfactual_probe.py tests/rigor/test_counterfactual_probe.py
git commit -m "feat(B3): §4.3 counterfactual citation probing — decoy injection + LLM-judge"
```

## Task 4: Adversarial multi-pass review (§4.4)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/adversarial_review.py`
- Test: `tests/rigor/test_adversarial_review.py`

- [ ] **Step 1: Write test**

```python
# tests/rigor/test_adversarial_review.py
import pytest
from unittest.mock import AsyncMock, patch
from plugins.vedix.mcp.lib.orchestrator.adversarial_review import review_with_stances

@pytest.mark.asyncio
async def test_two_pass_steelman_break_returns_median_and_disagreement():
    side_effects = [
        type("R", (), {"content": '{"score": 8, "rationale": "strong"}'})(),
        type("R", (), {"content": '{"score": 4, "rationale": "weak"}'})(),
    ]
    with patch("plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
               new=AsyncMock(side_effect=side_effects)):
        result = await review_with_stances(manuscript_text="dummy", n_passes=2)
        assert result["median_score"] == 6
        assert result["disagreement"] == 4
        assert len(result["passes"]) == 2
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/adversarial_review.py
from __future__ import annotations
import json
import statistics
from .dispatch import dispatch_agent

STANCES = [
    "steelman this manuscript — write the strongest possible defense before finding weaknesses",
    "break this manuscript — adopt a hostile reviewer position; find every reason this is wrong",
    "re-steelman after reading the break — what is the strongest case after considering the criticisms",
]

async def _pass(manuscript_text: str, stance: str) -> dict:
    prompt = f"""Stance: {stance}

Manuscript:
{manuscript_text[:8000]}

Score the manuscript 1-10 and give 3 sentences of rationale. Output JSON: {{"score": <int>, "rationale": "<str>"}}.
"""
    resp = await dispatch_agent(agent_type="adversarial-reviewer", prompt=prompt)
    try:
        return json.loads(resp.content)
    except json.JSONDecodeError:
        import re
        score_match = re.search(r'"score"\s*:\s*(\d+)', resp.content)
        return {"score": int(score_match.group(1)) if score_match else 5, "rationale": resp.content[:300]}

async def review_with_stances(*, manuscript_text: str, n_passes: int = 2) -> dict:
    stances = STANCES[:n_passes]
    passes = []
    for s in stances:
        p = await _pass(manuscript_text, s)
        p["stance"] = s
        passes.append(p)
    scores = [p["score"] for p in passes]
    return {
        "passes": passes,
        "median_score": int(statistics.median(scores)),
        "min_score": min(scores),
        "max_score": max(scores),
        "disagreement": max(scores) - min(scores),
    }
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/rigor/test_adversarial_review.py -v
git add plugins/vedix/mcp/lib/orchestrator/adversarial_review.py tests/rigor/test_adversarial_review.py
git commit -m "feat(B3): §4.4 adversarial multi-pass review — steelman / break / disagreement signal"
```

## Task 5: Semantic revision diff (§4.5)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/semantic_revision_diff.py`
- Test: `tests/rigor/test_semantic_revision_diff.py`

- [ ] **Step 1: Write test**

```python
# tests/rigor/test_semantic_revision_diff.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.semantic_revision_diff import diff_revisions

def test_identical_revisions_have_low_diff():
    old = "The cat sat on the mat."
    new = "The cat sat on the mat."
    diff = diff_revisions(old=old, new=new)
    assert diff["overall_similarity"] > 0.99

def test_paraphrase_preserves_meaning():
    old = "The catalyst increased yield by 12%."
    new = "Yield improved by 12% thanks to the catalyst."
    diff = diff_revisions(old=old, new=new)
    assert diff["overall_similarity"] > 0.85

def test_claim_inversion_detected():
    old = "The treatment significantly increased survival."
    new = "The treatment significantly decreased survival."
    diff = diff_revisions(old=old, new=new)
    # Inversion of polarity is a content change, not a paraphrase
    assert diff["overall_similarity"] < 0.95
    assert any(s["risk"] == "high" for s in diff["per_sentence"])
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/semantic_revision_diff.py
from __future__ import annotations
import re
from typing import Optional

_MODEL_CACHE = None

def _model():
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        from sentence_transformers import SentenceTransformer
        _MODEL_CACHE = SentenceTransformer("intfloat/multilingual-e5-large")
    return _MODEL_CACHE

def _sentences(text: str) -> list[str]:
    # cheap sentence splitter
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in raw if s]

def diff_revisions(*, old: str, new: str) -> dict:
    import numpy as np
    old_sents = _sentences(old)
    new_sents = _sentences(new)
    m = _model()
    if not old_sents or not new_sents:
        return {"overall_similarity": 0.0, "per_sentence": []}
    o_emb = m.encode(["query: " + s for s in old_sents], normalize_embeddings=True)
    n_emb = m.encode(["query: " + s for s in new_sents], normalize_embeddings=True)
    sim_matrix = o_emb @ n_emb.T
    # Each old sentence pairs with its best-match new sentence
    per_sentence = []
    for i, os_ in enumerate(old_sents):
        j = int(np.argmax(sim_matrix[i]))
        sim = float(sim_matrix[i][j])
        risk = "low"
        if sim < 0.7:
            risk = "high"
        elif sim < 0.85:
            risk = "medium"
        per_sentence.append({
            "old_idx": i, "new_idx": j,
            "old": os_, "new": new_sents[j], "similarity": round(sim, 3), "risk": risk,
        })
    overall = float(np.mean([p["similarity"] for p in per_sentence]))
    return {"overall_similarity": round(overall, 3), "per_sentence": per_sentence}
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/rigor/test_semantic_revision_diff.py -v
git add plugins/vedix/mcp/lib/orchestrator/semantic_revision_diff.py tests/rigor/test_semantic_revision_diff.py
git commit -m "feat(B3): §4.5 semantic revision diff — embedding-level claim cosine"
```

## Task 6: Pre-registration replay (§4.6)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/prereg_replay.py`
- Test: `tests/rigor/test_prereg_replay.py`

- [ ] **Step 1: Write test**

```python
# tests/rigor/test_prereg_replay.py
import json
import pytest
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.prereg_replay import (
    write_prereg, gate_experiment, audit_results, PreregViolation
)

def test_write_and_gate(tmp_path):
    prereg = {
        "hypothesis": "X improves Y",
        "primary_metric": "accuracy",
        "expected_direction": "increase",
        "tolerance": 0.05,
    }
    p = write_prereg(prereg, dest=tmp_path / "prereg.md")
    assert p.exists()
    gate_experiment(prereg_path=p)  # passes when file exists and is well-formed

def test_audit_detects_metric_swap(tmp_path):
    prereg = {"hypothesis": "X improves Y", "primary_metric": "accuracy", "expected_direction": "increase"}
    p = write_prereg(prereg, dest=tmp_path / "prereg.md")
    actual = {"primary_metric": "loss", "value": 0.4, "direction": "decrease"}
    with pytest.raises(PreregViolation):
        audit_results(prereg_path=p, actual=actual)

def test_audit_passes_when_consistent(tmp_path):
    prereg = {"hypothesis": "X improves Y", "primary_metric": "accuracy", "expected_direction": "increase"}
    p = write_prereg(prereg, dest=tmp_path / "prereg.md")
    actual = {"primary_metric": "accuracy", "value": 0.85, "direction": "increase"}
    audit_results(prereg_path=p, actual=actual)
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/prereg_replay.py
from __future__ import annotations
import json
import re
from pathlib import Path

class PreregViolation(Exception): ...

def write_prereg(prereg: dict, dest: Path) -> Path:
    """Write the prereg as a markdown file that the user can also read."""
    md = "# Pre-registration\n\n"
    md += f"**Hypothesis:** {prereg.get('hypothesis', '')}\n\n"
    md += f"**Primary metric:** {prereg.get('primary_metric', '')}\n\n"
    md += f"**Expected direction:** {prereg.get('expected_direction', '')}\n\n"
    md += f"**Tolerance:** {prereg.get('tolerance', '')}\n\n"
    md += "```yaml\n" + json.dumps(prereg, indent=2) + "\n```\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(md, encoding="utf-8")
    return dest

def _parse_prereg(prereg_path: Path) -> dict:
    text = prereg_path.read_text(encoding="utf-8")
    yaml_block = re.search(r"```yaml\n(.+?)\n```", text, re.DOTALL)
    if not yaml_block:
        raise PreregViolation(f"prereg at {prereg_path} has no machine-readable yaml block")
    return json.loads(yaml_block.group(1))

def gate_experiment(*, prereg_path: Path) -> None:
    """Hard-gate: must exist + parse + have required fields."""
    if not prereg_path.exists():
        raise PreregViolation(f"prereg required but {prereg_path} does not exist; create one before running the experiment")
    p = _parse_prereg(prereg_path)
    required = {"hypothesis", "primary_metric", "expected_direction"}
    missing = required - set(p.keys())
    if missing:
        raise PreregViolation(f"prereg missing keys: {missing}")

def audit_results(*, prereg_path: Path, actual: dict) -> dict:
    p = _parse_prereg(prereg_path)
    violations = []
    if actual.get("primary_metric") != p.get("primary_metric"):
        violations.append(f"primary metric swapped: prereg={p['primary_metric']!r}, actual={actual.get('primary_metric')!r}")
    if actual.get("direction") and p.get("expected_direction") and actual["direction"] != p["expected_direction"]:
        violations.append(f"direction reversed: prereg={p['expected_direction']!r}, actual={actual['direction']!r}")
    if violations:
        raise PreregViolation(" | ".join(violations))
    return {"prereg": p, "actual": actual, "violations": violations, "status": "ok"}
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/rigor/test_prereg_replay.py -v
git add plugins/vedix/mcp/lib/orchestrator/prereg_replay.py tests/rigor/test_prereg_replay.py
git commit -m "feat(B3): §4.6 pre-registration replay — hard-gate + post-experiment audit"
```

## Task 7: Provenance ledger + auto-disclosure (§4.7)

**Files:**
- Create: `plugins/vedix/mcp/lib/orchestrator/provenance_ledger.py`
- Create: `templates/ai_disclosure/preprint.tex` (one example; rest produced by Block 7)
- Test: `tests/rigor/test_provenance_ledger.py`

- [ ] **Step 1: Write test**

```python
# tests/rigor/test_provenance_ledger.py
import json
from pathlib import Path
from plugins.vedix.mcp.lib.orchestrator.provenance_ledger import (
    record_sentence, generate_disclosure, ProvenanceLedger
)

def test_record_and_load(tmp_path):
    ledger = ProvenanceLedger(path=tmp_path / "provenance.jsonl")
    ledger.record(sentence_id="s1", sentence="The cat sat.", agent="manuscript-writer",
                  model="claude-opus-4", evidence=["ref1"], reflection_rounds=2)
    entries = ledger.load_all()
    assert len(entries) == 1
    assert entries[0]["agent"] == "manuscript-writer"

def test_generate_disclosure_for_preprint(tmp_path):
    ledger = ProvenanceLedger(path=tmp_path / "provenance.jsonl")
    ledger.record(sentence_id="s1", sentence="Drafted.", agent="manuscript-writer", model="claude-opus-4", evidence=[], reflection_rounds=1)
    ledger.record(sentence_id="s2", sentence="Audited.", agent="manuscript-writer", model="claude-opus-4", evidence=["smith2024"], reflection_rounds=2)
    out = tmp_path / "AI_disclosure.md"
    generate_disclosure(ledger_path=tmp_path / "provenance.jsonl", venue="preprint", out=out)
    text = out.read_text(encoding="utf-8")
    assert "Vedix" in text
    assert "claude-opus-4" in text
    assert "manuscript-writer" in text
```

- [ ] **Step 2: Implement**

```python
# plugins/vedix/mcp/lib/orchestrator/provenance_ledger.py
from __future__ import annotations
import json
import time
from collections import Counter
from pathlib import Path

class ProvenanceLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, *, sentence_id: str, sentence: str, agent: str, model: str,
               evidence: list[str], reflection_rounds: int = 0) -> None:
        entry = {
            "ts": time.time(),
            "sentence_id": sentence_id,
            "sentence": sentence,
            "agent": agent,
            "model": model,
            "evidence": evidence,
            "reflection_rounds": reflection_rounds,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l]

def generate_disclosure(*, ledger_path: Path, venue: str, out: Path) -> Path:
    entries = ProvenanceLedger(path=ledger_path).load_all()
    agents = Counter(e["agent"] for e in entries)
    models = Counter(e["model"] for e in entries)
    total = len(entries)

    md = f"""# AI Disclosure for this manuscript

This manuscript was prepared using the **Vedix research workbench** ({venue} venue profile).
The pipeline orchestrated specialized agents through a sequence of phases. Sentence-level
provenance is recorded in `provenance.jsonl` (one entry per sentence with the responsible
agent, the LLM model that generated it, the cited evidence, and the number of self-reflection
rounds).

## Aggregate stats

- Sentences emitted: {total}
- Agents involved: {", ".join(sorted(agents))}
- Models used: {", ".join(sorted(models))}

## Per-agent breakdown

{chr(10).join(f"- `{a}`: {n} sentences" for a, n in agents.most_common())}

## Per-model breakdown

{chr(10).join(f"- `{m}`: {n} sentences" for m, n in models.most_common())}

## Reflection-round distribution

{chr(10).join(f"- {r} rounds: {n} sentences" for r, n in Counter(e['reflection_rounds'] for e in entries).most_common())}

## Author responsibilities

The human author(s) reviewed every Vedix-emitted sentence, verified every citation, ran the
reproducibility audit (`reproducibility_audit.json`), inspected the pre-registration audit
(`prereg_audit.json`), and signed off on the final manuscript. Author identities and corresponding
responsibilities appear in the manuscript header.
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/rigor/test_provenance_ledger.py -v
git add plugins/vedix/mcp/lib/orchestrator/provenance_ledger.py tests/rigor/test_provenance_ledger.py
git commit -m "feat(B3): §4.7 provenance ledger + auto-disclosure"
```

## Task 8: Wire rigor tracks into pipeline

**Files:**
- Modify: `plugins/vedix/mcp/lib/orchestrator/pipeline.py` (add hook calls)
- Test: `tests/rigor/test_pipeline_wiring.py`

- [ ] **Step 1: Write integration test**

```python
# tests/rigor/test_pipeline_wiring.py
import pytest
from plugins.vedix.mcp.lib.orchestrator.pipeline import Pipeline

def test_rigor_tracks_registered(tmp_path):
    pipe = Pipeline(workspace=tmp_path)
    hooks = pipe.list_hooks()
    expected = {"failure_mode_check", "citation_graph_analysis", "counterfactual_probe",
                "adversarial_review", "semantic_revision_diff", "prereg_gate",
                "prereg_audit", "provenance_record", "disclosure_generate"}
    assert expected.issubset(hooks)
```

- [ ] **Step 2: Add hook registration**

```python
# plugins/vedix/mcp/lib/orchestrator/pipeline.py (additions)
from . import (
    failure_mode_learning, citation_graph, counterfactual_probe,
    adversarial_review, semantic_revision_diff, prereg_replay, provenance_ledger
)

class Pipeline:
    # ... existing methods ...
    def _register_rigor_hooks(self):
        self._hooks["failure_mode_check"] = failure_mode_learning.load_active_modes
        self._hooks["citation_graph_analysis"] = citation_graph.analyze
        self._hooks["counterfactual_probe"] = counterfactual_probe.probe_all
        self._hooks["adversarial_review"] = adversarial_review.review_with_stances
        self._hooks["semantic_revision_diff"] = semantic_revision_diff.diff_revisions
        self._hooks["prereg_gate"] = prereg_replay.gate_experiment
        self._hooks["prereg_audit"] = prereg_replay.audit_results
        self._hooks["provenance_record"] = lambda *a, **kw: None  # configured per-phase
        self._hooks["disclosure_generate"] = provenance_ledger.generate_disclosure

    def list_hooks(self) -> set[str]:
        if not hasattr(self, "_hooks"):
            self._hooks = {}
            self._register_rigor_hooks()
        return set(self._hooks)
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/rigor/test_pipeline_wiring.py -v
git add plugins/vedix/mcp/lib/orchestrator/pipeline.py tests/rigor/test_pipeline_wiring.py
git commit -m "feat(B3): wire 7 rigor tracks into pipeline hook registry"
```

## Block 3 acceptance criteria

- [ ] All 7 rigor track modules pass their unit tests
- [ ] `pytest tests/rigor/ -v` returns all green
- [ ] Pipeline wiring test confirms hooks registered
- [ ] End-to-end smoke: `/vedix linear regression on synthetic data` produces `rigor/failure_modes.json`, `rigor/citation_graph.json`, `rigor/counterfactual.json`, `rigor/adversarial_review.json`, `rigor/provenance.jsonl`, `AI_disclosure.md`
- [ ] Documented in `docs/rigor/README.md`
- [ ] Git tag `v3.0.0-block3` pushed

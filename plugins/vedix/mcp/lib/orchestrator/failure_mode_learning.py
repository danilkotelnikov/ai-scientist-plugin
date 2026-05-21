"""§4.1 Failure-mode learning.

Mark failures, persist them per-user under ``~/.vedix/failure_corpus``,
then cluster the corpus monthly with sentence-transformers + HDBSCAN to
distill a small active-mode set the pipeline can check against.
"""
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


def mark_failure(
    *,
    job_id: str,
    description: str,
    phase: Optional[str] = None,
) -> Path:
    """User-invoked: mark a job as failed with a description."""
    entry = {
        "ts": time.time(),
        "job_id": job_id,
        "description": description,
        "phase": phase,
    }
    out = _corpus_dir() / f"{job_id}_{int(entry['ts'] * 1000)}.json"
    out.write_text(json.dumps(entry), encoding="utf-8")
    return out


class FailureCorpus:
    """View over the on-disk failure-corpus directory."""

    def __init__(self) -> None:
        self.dir = _corpus_dir()

    def list_all(self) -> list[dict]:
        entries: list[dict] = []
        for f in self.dir.glob("*.json"):
            entries.append(json.loads(f.read_text(encoding="utf-8")))
        return sorted(entries, key=lambda e: e["ts"])


def cluster_failures(min_cluster_size: int = 5) -> list[dict]:
    """Cluster the failure corpus with sentence-transformers + HDBSCAN.

    Returns a list of cluster dicts (largest first); empty list when the
    corpus is smaller than ``min_cluster_size``.
    """
    from sentence_transformers import SentenceTransformer
    import hdbscan  # pyright: ignore[reportMissingImports]

    corpus = FailureCorpus().list_all()
    if len(corpus) < min_cluster_size:
        return []

    model = SentenceTransformer("intfloat/multilingual-e5-small")
    descriptions = [e["description"] for e in corpus]
    embeddings = model.encode(
        ["query: " + d for d in descriptions],
        normalize_embeddings=True,
    )
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size, metric="euclidean",
    )
    labels = clusterer.fit_predict(embeddings)

    clusters: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if int(label) == -1:  # noise
            continue
        clusters.setdefault(int(label), []).append(idx)

    out: list[dict] = []
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
    """Load the currently-active failure-mode set written by the batch job."""
    p = _home() / ".vedix" / "failure_modes" / f"v{version}.json"
    if not p.exists():
        return []
    payload = json.loads(p.read_text(encoding="utf-8"))
    # Support both schema variants ({"modes": [...]} legacy, {"active_modes": [...]} new)
    return payload.get("active_modes", payload.get("modes", []))

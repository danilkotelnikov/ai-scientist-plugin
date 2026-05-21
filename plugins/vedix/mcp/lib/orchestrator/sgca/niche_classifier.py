from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
import yaml


def _bundled_niches_path() -> Path:
    # __file__ -> plugins/vedix/mcp/lib/orchestrator/sgca/niche_classifier.py
    # parents[4] -> plugins/vedix/
    return Path(__file__).resolve().parents[4] / "templates" / "niches.yaml"


def _local_niches_path() -> Path:
    home = Path(os.environ.get("USERPROFILE") or os.environ["HOME"])
    return home / ".vedix" / "niches.local.yaml"


def load_niches() -> dict[str, list[str]]:
    bundled = yaml.safe_load(_bundled_niches_path().read_text(encoding="utf-8"))["niches"]
    local_path = _local_niches_path()
    if local_path.exists():
        local = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
        for disc, items in (local.get("niches") or {}).items():
            existing = bundled.setdefault(disc, [])
            for n in items:
                if n not in existing:
                    existing.append(n)
    return bundled


def _topic_label_cosine(topic: str, label: str) -> float:
    """Stub — production uses sentence-transformers (intfloat/multilingual-e5-large).
    Tests patch this function."""
    from .embeddings import _model
    import numpy as np
    m = _model()
    a = m.encode([f"query: {topic}"], normalize_embeddings=True)[0]
    b = m.encode([f"query: {label.replace('_', ' ')}"], normalize_embeddings=True)[0]
    return float(np.dot(a, b))


def classify_niche(*, discipline: str, topic_text: str, threshold: float = 0.5) -> str:
    candidates = load_niches().get(discipline, [])
    if not candidates:
        return f"{discipline}/general"
    scored = sorted(
        ((label, _topic_label_cosine(topic_text, label)) for label in candidates),
        key=lambda lp: lp[1],
        reverse=True,
    )
    best_label, best_score = scored[0]
    if best_score < threshold:
        return f"{discipline}/general"
    return f"{discipline}/{best_label}"


class NicheClassifier:
    """Convenience wrapper for orchestrator pipeline injection."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def __call__(self, *, discipline: str, topic_text: str) -> str:
        return classify_niche(discipline=discipline, topic_text=topic_text, threshold=self.threshold)

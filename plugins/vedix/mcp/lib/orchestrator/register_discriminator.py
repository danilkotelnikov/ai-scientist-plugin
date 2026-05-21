"""§5.3.2 Hybrid linguistic register discriminator.

Two cooperating layers:
  • Layer A — retrieval-grounded: embed each candidate paragraph with
    multilingual-e5 and require a strong cosine similarity to the nearest
    k chunks of a known-good per-(discipline, language) corpus stored in
    ChromaDB. Always available, no per-pair training required.
  • Layer B — trained classifier: a small transformer fine-tuned per
    (discipline, language) pair against positive samples (real published
    paragraphs) + adversarial AI-style negatives. Bundled via
    ``vedix model fetch`` or trained locally with the CPU/GPU scripts.

The ``HybridDiscriminator`` runs both layers and only admits a paragraph
when both agree (or when Layer B is missing, when Layer A alone passes).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:  # heavy dep — lazily imported in production, gracefully missing in tests
    import chromadb  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    chromadb = None  # type: ignore[assignment]


@dataclass
class Verdict:
    """Per-layer judgement on a single paragraph.

    Attributes:
        pass_: Whether the layer accepted the paragraph as in-register.
        score: Layer-specific confidence in [0, 1] (cosine similarity for
            Layer A, P(label=1) for Layer B).
        explanation: Human-readable rationale ("best k-NN cosine 0.82 vs
            threshold 0.55").
        layer: ``"A"`` (retrieval) or ``"B"`` (trained).
    """

    pass_: bool
    score: float
    explanation: str
    layer: str


class LayerA:
    """Retrieval-grounded discriminator.

    Maintains a per-(discipline, language) ChromaDB collection of
    paragraphs from the prepared corpus, embedded with multilingual-e5.
    To judge a new paragraph: embed it, query the top-k nearest corpus
    chunks, accept if the best cosine similarity meets ``threshold``.

    The encoder is loaded lazily on first ``add_corpus``/``judge`` to keep
    import cost zero when only Layer B is needed.
    """

    def __init__(
        self,
        *,
        corpus_root: Path,
        discipline: str,
        language: str,
        threshold: float = 0.55,
    ):
        if chromadb is None:  # pragma: no cover - guarded by importorskip in tests
            raise ImportError(
                "chromadb is required for LayerA; pip install chromadb"
            )
        self.corpus_root = Path(corpus_root)
        self.discipline = discipline
        self.language = language
        self.threshold = threshold
        self._client = chromadb.PersistentClient(
            path=str(self.corpus_root / discipline / language / "chromadb")
        )
        self._collection = self._client.get_or_create_collection(
            name=f"{discipline}_{language}",
            metadata={"hnsw:space": "cosine"},
        )
        self._encoder = None

    def _enc(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

            self._encoder = SentenceTransformer("intfloat/multilingual-e5-large")
        return self._encoder

    def add_corpus(self, chunks: list[str]) -> None:
        """Embed and index ``chunks`` into the per-pair ChromaDB collection.

        E5 expects the ``passage:`` prefix for indexed text and ``query:``
        for query text; honoured here per the model card.
        """
        embs = self._enc().encode(
            ["passage: " + c for c in chunks], normalize_embeddings=True
        ).tolist()
        self._collection.add(
            ids=[f"chunk_{i}_{hash(c) & 0xFFFFFFFF}" for i, c in enumerate(chunks)],
            embeddings=embs,
            documents=chunks,
        )

    def judge(self, paragraph: str, k: int = 5) -> Verdict:
        """Return the layer's verdict on ``paragraph``.

        Args:
            paragraph: The candidate paragraph to evaluate.
            k: Top-k nearest neighbours to consult; defaults to 5.

        Returns:
            A :class:`Verdict` with ``score`` set to the best cosine
            similarity (1 - distance under the cosine space) and
            ``pass_`` true when that similarity meets ``self.threshold``.
        """
        emb = self._enc().encode(
            [f"query: {paragraph}"], normalize_embeddings=True
        ).tolist()
        res = self._collection.query(query_embeddings=emb, n_results=k)
        if not res["distances"] or not res["distances"][0]:
            return Verdict(
                pass_=False,
                score=0.0,
                explanation="empty corpus",
                layer="A",
            )
        # ChromaDB cosine "distance" = 1 - cosine_similarity
        best_similarity = 1.0 - min(res["distances"][0])
        passes = best_similarity >= self.threshold
        return Verdict(
            pass_=passes,
            score=round(float(best_similarity), 3),
            explanation=(
                f"best k-NN cosine similarity {best_similarity:.3f} "
                f"vs threshold {self.threshold}"
            ),
            layer="A",
        )

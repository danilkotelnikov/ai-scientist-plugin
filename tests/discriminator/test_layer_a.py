"""Tests for §5.3.2 Layer A retrieval-grounded register discriminator.

The implementation relies on chromadb + sentence-transformers. To keep the
unit suite light, this test ``importorskip``s the heavy deps and stubs the
embedding encoder with a deterministic fake — so we exercise the
``add_corpus``/``judge`` plumbing without downloading multilingual-e5.
"""
from __future__ import annotations

import sys
import types
import hashlib
import pytest

pytest.importorskip("chromadb")


class _FakeEncoder:
    """Deterministic 64-dim encoder: hashes the input to a unit vector."""

    def encode(self, texts, normalize_embeddings: bool = True):  # type: ignore[no-untyped-def]
        out = []
        for t in texts:
            # Strip e5 prefixes so "passage: X" and "query: X" both hash to X.
            stem = t.split(": ", 1)[1] if ": " in t else t
            tokens = stem.lower().split()
            vec = [0.0] * 64
            for tok in tokens:
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                vec[h % 64] += 1.0
            # Normalize
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return _AsList(out)


class _AsList(list):
    """Stand-in for the numpy-array `.tolist()` interface used in production."""

    def tolist(self):  # type: ignore[no-untyped-def]
        return list(self)


def _patch_encoder(layer):
    layer._encoder = _FakeEncoder()


def test_layer_a_passes_in_register(tmp_path):
    from plugins.vedix.mcp.lib.orchestrator.register_discriminator import LayerA

    layer = LayerA(corpus_root=tmp_path, discipline="chemistry", language="en")
    _patch_encoder(layer)
    corpus_chunks = [
        "The compound was prepared by reflux in ethanol.",
        "The reaction was monitored by TLC; column chromatography gave the pure product.",
        "NMR spectra in CDCl3 confirmed the structure of compound 1.",
    ]
    layer.add_corpus(corpus_chunks)
    verdict = layer.judge("The compound was prepared by reflux in ethanol.")
    assert verdict.layer == "A"
    assert verdict.pass_ or verdict.score > 0.5


def test_layer_a_fails_out_of_register(tmp_path):
    from plugins.vedix.mcp.lib.orchestrator.register_discriminator import LayerA

    layer = LayerA(corpus_root=tmp_path, discipline="chemistry", language="en")
    _patch_encoder(layer)
    corpus_chunks = ["We synthesized compound 1 by refluxing in ethanol."] * 5
    layer.add_corpus(corpus_chunks)
    verdict = layer.judge("xxxxx yyyyy zzzzz nonsense gibberish jabberwocky")
    assert not verdict.pass_


def test_layer_a_empty_corpus_fails(tmp_path):
    from plugins.vedix.mcp.lib.orchestrator.register_discriminator import LayerA

    layer = LayerA(corpus_root=tmp_path, discipline="chemistry", language="en")
    _patch_encoder(layer)
    verdict = layer.judge("Any paragraph here.")
    assert not verdict.pass_
    assert verdict.score == 0.0

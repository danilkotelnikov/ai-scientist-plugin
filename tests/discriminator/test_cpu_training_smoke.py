"""Smoke test for §5.3.2.a CPU training script.

We exercise ``train_one_pair`` with the tiniest model (``prajjwal1/bert-tiny``,
~17 MB) and a 60-sample synthetic corpus so we cover the data-loader,
optimizer, validation, and checkpoint paths without spending an hour on
real training.

The test is heavy by unit-test standards (~30-60 s with a warm HF cache;
the first run downloads bert-tiny over the network). It is therefore
gated on:

  • torch + transformers + sklearn being importable, and
  • the ``VEDIX_RUN_HEAVY_TESTS=1`` env var being set (so CI nodes that
    don't have transit can opt out).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


HEAVY = os.environ.get("VEDIX_RUN_HEAVY_TESTS") == "1"


@pytest.mark.skipif(
    not HEAVY, reason="set VEDIX_RUN_HEAVY_TESTS=1 to run the CPU training smoke test"
)
def test_cpu_train_one_pair_with_tiny_model(tmp_path):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    pytest.importorskip("sklearn")
    pytest.importorskip("safetensors")

    # Make scripts/ importable so we can call train_one_pair in-process.
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import train_register_classifier_cpu as tr

    corpus = tmp_path / "corpus" / "chemistry" / "en"
    corpus.mkdir(parents=True)

    def _row(i, label):
        return {
            "text": f"sample paragraph number {i} label {label}",
            "label": label,
            "paper_id": f"p{label}_{i}",
        }

    train = [_row(i, i % 2) for i in range(40)]
    val = [_row(100 + i, i % 2) for i in range(10)]
    test = [_row(200 + i, i % 2) for i in range(10)]
    for name, lst in (("train", train), ("val", val), ("test", test)):
        (corpus / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(x) for x in lst), encoding="utf-8"
        )

    # google/bert_uncased_L-2_H-128_A-2 is the official Google tiny BERT
    # checkpoint and works under transformers v5 without the broken-fast-
    # tokenizer issue that ``prajjwal1/bert-tiny`` has.
    metrics = tr.train_one_pair(
        discipline="chemistry",
        language="en",
        corpus_root=tmp_path / "corpus",
        output_root=tmp_path / "out",
        model_name="google/bert_uncased_L-2_H-128_A-2",
        epochs=1,
        batch_size=4,
        grad_accum=1,
        lr=5e-5,
        num_workers=0,
        bf16=False,
        max_length=32,
        resume=False,
    )

    out_dir = tmp_path / "out" / "register_chemistry_en"
    assert (out_dir / "model.safetensors").exists()
    assert (out_dir / "metrics.json").exists()
    assert metrics["device_trained_on"] == "cpu"
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1" in metrics


def test_register_dataset_shapes():
    """Lightweight sanity check that runs without HF downloads."""
    pytest.importorskip("torch")
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import train_register_classifier_cpu as tr

    class _FakeTokenizer:
        def __call__(self, text, **kw):
            import torch

            max_length = kw.get("max_length", 8)
            return {
                "input_ids": torch.zeros((1, max_length), dtype=torch.long),
                "attention_mask": torch.ones((1, max_length), dtype=torch.long),
            }

    ds = tr.RegisterDataset(
        [{"text": "x", "label": 1}, {"text": "y", "label": 0}],
        _FakeTokenizer(),
        max_length=8,
    )
    assert len(ds) == 2
    sample = ds[0]
    assert sample["input_ids"].shape == (8,)
    assert sample["labels"].item() == 1


def test_bf16_supported_returns_bool():
    """The helper must always return a bool (True or False), never raise."""
    pytest.importorskip("torch")
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import train_register_classifier_cpu as tr

    out = tr._bf16_supported()
    assert isinstance(out, bool)

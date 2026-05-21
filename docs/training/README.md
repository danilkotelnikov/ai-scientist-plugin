# Training the Vedix register classifier locally

Most users will fetch pre-trained classifiers automatically via
`vedix model fetch`. This document is for users who want to retrain
locally — either because they need a discipline+language pair we don't
ship yet, or they want to refine the classifier on their own corpus.

## Hardware paths

Vedix ships two training scripts. Pick the one that matches your
hardware:

| Hardware                                          | Script                              | Model               | Time per pair |
|---|---|---|---|
| **NVIDIA RTX 4060 8 GB** (or any GPU >= 8 GB VRAM) | `train_register_classifier_gpu.py`  | `xlm-roberta-base`  | 6-10 hours    |
| **Intel Xeon 8368 / 512 GB RAM** (no GPU)         | `train_register_classifier_cpu.py`  | `mDeBERTa-v3-small` | 20-28 hours   |
| **Don't know which** — let Vedix choose            | `train_register_classifier.py --auto` | auto-selected   | -             |

See [`cpu-instructions.md`](./cpu-instructions.md) or
[`gpu-instructions.md`](./gpu-instructions.md) for full command details.

## Workflow (high level)

```bash
# 1. Prepare the corpus (download + extract + dedup + label + split)
python scripts/prepare_corpus.py --target-count 150

# 2. Train (auto-detect hardware)
python scripts/train_register_classifier.py --auto \
  --corpus-root ~/.vedix/corpus \
  --output-root ~/.vedix/classifiers

# 3. (Optional) Publish high-quality models back to the community
vedix model publish register_chemistry_en \
  --model-dir ~/.vedix/classifiers/register_chemistry_en
```

## Quality gate

Training auto-aborts a (discipline, language) pair if val F1 < 0.78
after one epoch. That signals a corpus problem — too few papers, bad
language verification, weak adversarial negatives. Fix the corpus and
re-run.

Toy corpora (< 200 training rows) skip this gate so quick smoke tests
on synthetic data can complete without spurious aborts.

## Where things live

| Path | What |
|---|---|
| `~/.vedix/corpus/<discipline>/<lang>/` | Prepared corpus (acquisition + dedup + train/val/test splits) |
| `~/.vedix/classifiers/register_<discipline>_<lang>/` | Trained model checkpoints + metrics |
| `~/.vedix/classifiers/manifest.json` | Per-model metadata (F1, training timestamp, device used) |
| `~/.vedix/classifiers/tb_logs/` | TensorBoard event files |

## Resume after interruption

Both training scripts accept `--resume-from-checkpoint auto`, which
picks up at the last best-val checkpoint under `checkpoint-best/`.
Just re-run the same command.

The dataset-prep pipeline (`prepare_corpus.py`) is also idempotent: per-
stage `.checkpoints/<stage>.done` markers let the orchestrator skip
stages that already finished. Use `--force-restart` to scrub them.

## Where the corpus comes from

`prepare_corpus.py` runs a 10-stage pipeline per (discipline, language)
pair:

1. **acquisition** — fans out across OpenAlex, Semantic Scholar, arXiv,
   bioRxiv, PubMed, and Anna's Archive.
2. **download** — bounded async pool fetches PDFs/XML/HTML payloads.
3. **extraction** — pdfminer.six / lxml / BeautifulSoup → plain text.
4. **lang_verify** — fasttext lid drops papers whose extracted text
   doesn't match the target ISO code.
5. **segmentation** — paragraph split with IMRaD section guessing.
6. **dedup** — MinHashLSH near-duplicate removal at Jaccard 0.85.
7. **labeling** — rule-based positive labelling (substantive sections,
   40-400 words).
8. **negatives** — adversarial AI-style negatives generated through
   your BYOK provider with at least 3 Tier-1 AI-tell markers per
   rewrite.
9. **splits** — stratified paper-level train/val/test (no paper leaks).
10. **stats** — `corpus_stats.json` with per-split counts and balance.

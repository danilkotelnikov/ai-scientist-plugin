# CPU training (Xeon 8368, no GPU)

## Hardware target

- Intel Xeon 8368 (38 cores / 76 threads / 512 GB RAM) — confirmed
  working in development.
- Any modern Xeon / EPYC with at least 64 logical cores and at least
  128 GB RAM should work.
- AVX-512 BF16 is highly recommended — the script falls back to fp32
  automatically when bf16 isn't supported, but training is roughly two
  times slower.

## Time budget

- Per (discipline, language) pair: about 20-28 hours.
- All 56 pairs sequentially: about 7-9 days.
- All 56 pairs with `--parallel-pairs 4` (one process per pair, four at
  a time on a 76-thread Xeon): about 2-3 days.

## Command — train everything

```bash
source ~/.vedix/repo/venv/bin/activate

python ~/.vedix/repo/scripts/train_register_classifier_cpu.py \
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
python scripts/train_register_classifier_cpu.py \
  --corpus-root ~/.vedix/corpus \
  --output-root ~/.vedix/classifiers \
  --languages en --disciplines chemistry \
  --only-pair chemistry:en
```

## Resume after interruption

`--resume-from-checkpoint auto` picks up at the last best-val
checkpoint. Just re-run the same command — the trainer detects an
existing `checkpoint-best/model.safetensors` and continues from it.

## Memory expectations

mDeBERTa-v3-small consumes roughly 5 GB RAM per training process. With
the recommended `--parallel-pairs 4`, peak RAM is about 24 GB total —
comfortably within 512 GB.

## Why bf16 specifically

Xeon 8368 ships AVX-512 BF16 instructions. PyTorch 2.4+ uses them
through `torch.autocast("cpu", dtype=torch.bfloat16)`. Throughput
improves roughly 1.6 to 1.9 times over fp32 on dense matmul-heavy
workloads like classification fine-tuning. The script gates on
`torch.cpu.amp.is_bf16_supported()` (with a fallback to the older
`_is_bf16_supported`) and silently downgrades to fp32 if the CPU
doesn't advertise BF16.

## Output

```
~/.vedix/classifiers/register_<discipline>_<lang>/
├── model.safetensors        # ~530 MB final
├── tokenizer.json
├── config.json
├── training_log.jsonl       # per-step loss / lr
├── metrics.json             # test split P/R/F1/Acc + best val F1
└── checkpoint-best/
    └── model.safetensors    # best-val snapshot
~/.vedix/classifiers/manifest.json
~/.vedix/classifiers/tb_logs/
```

## Quality gate

If validation F1 stays below 0.78 after the first epoch on a real
training set (at least 200 rows), the trainer aborts the pair and
proceeds to the next one. The most common causes:

- corpus too small (`--target-count 150` per pair is the recommended
  floor);
- language verification missed a wrong-language paper batch — re-run
  the dataset prep with stricter filtering;
- adversarial negatives are too easy — the BYOK provider hit safety
  rails and refused to rewrite, so the generated negatives are nearly
  identical to the positives.

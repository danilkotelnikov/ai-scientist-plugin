# GPU training (RTX 4060 8 GB or similar)

## Hardware target

- NVIDIA RTX 4060 8 GB — confirmed working in development.
- Any NVIDIA GPU with at least 8 GB VRAM should work.
- Driver: CUDA 12.x toolkit; PyTorch 2.4+ with the matching cu12x
  wheel.

## Time budget

- Per (discipline, language) pair: about 6-10 hours.
- All 56 pairs sequentially: about 2-3 weeks.

Recommended: train 8 to 10 pairs per weekend with `--only-pair` calls,
pause, resume the next weekend.

## Command — train everything

```bash
source ~/.vedix/repo/venv/bin/activate

python ~/.vedix/repo/scripts/train_register_classifier_gpu.py \
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

## Command — train one pair

```bash
python scripts/train_register_classifier_gpu.py \
  --corpus-root ~/.vedix/corpus \
  --output-root ~/.vedix/classifiers \
  --languages en --disciplines physics \
  --only-pair physics:en
```

## Memory expectations (RTX 4060 8 GB)

Peak VRAM is about 7.1 GB with the recommended flags. If you see CUDA
OOM:

- Reduce `--max-length` from 512 to 384 (smaller activation tensors).
- Or reduce `--batch-size` from 4 to 2 (and double `--grad-accum` to
  keep the effective batch unchanged).
- Or drop `--gradient-checkpointing` only if you have more VRAM.

Other GPUs:

| GPU             | Recommended batch-size × grad-accum | Notes                                           |
|-----------------|-------------------------------------|-------------------------------------------------|
| RTX 4060 8 GB   | 4 × 16                              | keep `--gradient-checkpointing`                 |
| RTX 4070 12 GB  | 8 × 8                               | gradient-checkpointing optional                 |
| RTX 4090 24 GB  | 32 × 2                              | drop gradient-checkpointing                     |
| H100 80 GB      | 64 × 1                              | drop gradient-checkpointing; bf16 over fp16     |

## Output

Same layout as the CPU path. The `metrics.json` records the exact GPU
used:

```json
{
  "device_trained_on": "cuda:0 NVIDIA GeForce RTX 4060",
  "f1": 0.91,
  ...
}
```

## Resume after interruption

`--resume-from-checkpoint auto` is the default. Re-running the same
command picks up at the last `checkpoint-best/model.safetensors`.
TensorBoard event files at `~/.vedix/classifiers/tb_logs/` survive
interruption.

## Why fp16 + gradient checkpointing

`xlm-roberta-base` is 278 M params; fp16 weights are about 560 MB, fp16
activations at sequence-length 512 and batch 4 push us close to 7 GB
without gradient checkpointing. Enabling checkpointing trades roughly
35 percent extra wall-time for a 30 percent reduction in peak
activation memory — the difference between fitting in 8 GB and OOM.

## Quality gate

Same as the CPU path: training auto-aborts a pair if val F1 < 0.78
after epoch 0 on a real (at least 200 row) train set. Toy / smoke-test
sized corpora skip the gate.

"""Per-stage idempotency markers for ``prepare_corpus.py`` (§5.3.1).

Each (discipline, language) corpus directory carries a ``.checkpoints/``
subfolder with a single ``<stage>.done`` file per finished stage. The
orchestrator skips a stage whose marker exists and re-runs everything
downstream after ``reset(stage)``.

The marker stores ``{"stage", "ts", **payload}`` so a future inspector
can report when each stage last ran (and any payload metadata such as
candidate counts).
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class StageCheckpoint:
    """File-based stage marker store."""

    def __init__(self, root: Path):
        self.dir = Path(root) / ".checkpoints"
        self.dir.mkdir(parents=True, exist_ok=True)

    def is_done(self, stage: str) -> bool:
        return (self.dir / f"{stage}.done").exists()

    def mark_done(self, stage: str, payload: dict | None = None) -> None:
        info = {"stage": stage, "ts": time.time(), **(payload or {})}
        (self.dir / f"{stage}.done").write_text(
            json.dumps(info), encoding="utf-8"
        )

    def reset(self, stage: str) -> None:
        (self.dir / f"{stage}.done").unlink(missing_ok=True)

    def info(self, stage: str) -> dict | None:
        marker = self.dir / f"{stage}.done"
        if not marker.exists():
            return None
        try:
            return json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

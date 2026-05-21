"""CheckpointManager — per-phase pickle. Per spec §4.16.

Pickles state to <checkpoint_dir>/<phase>.pkl AND mirrors to MemPalace as a
diary entry under 'phase-checkpoints'. The mirror is best-effort; failure to
mirror does NOT block the pickle save.

`--resume` flag loads from latest().
"""
from __future__ import annotations
import pickle
from pathlib import Path
from typing import Optional


class CheckpointManager:
    def __init__(self, checkpoint_dir: Path, palace=None):
        self.dir = Path(checkpoint_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.palace = palace  # Optional: ProjectPalace for mirroring

    def _path(self, phase: str) -> Path:
        return self.dir / f"{phase}.pkl"

    def save(self, phase: str, state: dict) -> None:
        path = self._path(phase)
        with open(path, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
        # Best-effort palace mirror
        if self.palace is not None:
            try:
                self.palace.write_diary(
                    agent="checkpoint",
                    content=f"Phase {phase} checkpoint saved to {path.name}",
                    tags=["phase-checkpoint", f"phase:{phase}"],
                )
            except Exception:
                pass  # Mirror is advisory

    def load(self, phase: str) -> Optional[dict]:
        path = self._path(phase)
        if not path.is_file():
            return None
        with open(path, "rb") as f:
            return pickle.load(f)

    def list_completed(self) -> list:
        return sorted(p.stem for p in self.dir.glob("*.pkl"))

    def latest(self) -> Optional[str]:
        completed = self.list_completed()
        return completed[-1] if completed else None

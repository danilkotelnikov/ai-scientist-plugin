"""Monthly batch: cluster the failure corpus and emit a new active-mode set.

Usage::

    python scripts/learn_failure_modes.py

Writes ``~/.vedix/failure_modes/v<N>.json`` with the top-15 clusters as
active modes and the rest on a watch-list.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path


# Make the orchestrator package importable when the script is run directly.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(_REPO_ROOT / "plugins" / "vedix" / "mcp" / "lib"),
)

from orchestrator.failure_mode_learning import (  # noqa: E402
    _home, cluster_failures,
)


def _synthesize_name(samples: list[str]) -> str:
    """Compact name from common keywords; can be LLM-rewritten later."""
    words: list[str] = []
    for s in samples:
        words.extend(w.lower() for w in s.split() if len(w) > 3)
    top = [w for w, _ in Counter(words).most_common(3)]
    return "_".join(top) if top else "unnamed_cluster"


def main() -> None:
    clusters = cluster_failures(min_cluster_size=5)
    print(f"[learn] found {len(clusters)} clusters")
    active = clusters[:15]
    watch = clusters[15:]
    out_dir = _home() / ".vedix" / "failure_modes"
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("v*.json"))
    next_v = int(existing[-1].stem[1:]) + 1 if existing else 1
    payload = {
        "version": next_v,
        "generated_at": time.time(),
        "active_modes": [
            {
                "cluster_id": c["cluster_id"],
                "synthetic_name": _synthesize_name(c["sample_descriptions"]),
                "size": c["size"],
                "sample_descriptions": c["sample_descriptions"],
                "severity": "warn",  # default; hand-edit to "block"
            }
            for c in active
        ],
        "watch_list": [
            {"cluster_id": c["cluster_id"], "size": c["size"]} for c in watch
        ],
    }
    out = out_dir / f"v{next_v}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[learn] wrote {out}")


if __name__ == "__main__":
    main()

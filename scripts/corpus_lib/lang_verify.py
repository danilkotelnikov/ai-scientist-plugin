"""Stage 4 — verify each extracted paper is in the target language.

Primary path: a cached fasttext ``lid.176.bin`` (downloaded on first use
to ``~/.vedix/models/``). Fallback path when fasttext is missing/fails:
ASCII-ratio heuristic, which catches the common EN-vs-non-EN case but is
deliberately conservative for non-EN pairs.

The model handle is cached at module scope to avoid the ~1 second reload
on every paragraph.
"""
from __future__ import annotations

import os
from pathlib import Path

_MODEL = None


def _load_fasttext():
    """Load (and cache) the fasttext lid.176 classifier."""
    global _MODEL
    if _MODEL is None:
        import fasttext  # type: ignore[import-untyped]

        path = os.environ.get(
            "VEDIX_FASTTEXT_LID",
            str(Path.home() / ".vedix" / "models" / "lid.176.bin"),
        )
        if not Path(path).exists():
            import urllib.request

            url = (
                "https://dl.fbaipublicfiles.com/fasttext/"
                "supervised-models/lid.176.bin"
            )
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, path)
        _MODEL = fasttext.load_model(path)
    return _MODEL


def detect_lang(text: str) -> str:
    """Return an ISO-639-1 code, or ``"unknown"`` if undeterminable."""
    if not text.strip():
        return "unknown"
    try:
        m = _load_fasttext()
        labels, _ = m.predict(text.replace("\n", " ")[:1000])
        return labels[0].replace("__label__", "")
    except Exception:
        # ASCII-ratio heuristic: ≥ 90% ASCII → assume English.
        ascii_ratio = sum(1 for c in text if c.isascii()) / max(1, len(text))
        return "en" if ascii_ratio > 0.9 else "unknown"


def filter_papers(
    papers: list[dict],
    *,
    target_lang: str,
    text_root: Path,
) -> list[dict]:
    """Drop papers whose extracted text doesn't match ``target_lang``."""
    keep: list[dict] = []
    for p in papers:
        pid = p.get("id", p.get("doi"))
        if not pid:
            continue
        text_file = text_root / f"{pid}.txt"
        if not text_file.exists():
            continue
        detected = detect_lang(text_file.read_text(encoding="utf-8")[:5000])
        if detected == target_lang:
            keep.append(p)
    return keep

"""Stage 2 — stream PDF/XML/HTML payloads to disk.

``download_one`` is the unit of work; ``download_many`` runs a bounded
pool of concurrent downloads. Both are idempotent: an existing
destination file is returned as-is, which makes the stage safe to retry
without re-fetching.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


async def download_one(url: str, dest: Path, timeout: float = 60.0) -> Path | None:
    """Stream ``url`` to ``dest``. Return ``dest`` on success, ``None`` on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    try:
        import httpx  # lazy import — keeps test cost zero
    except ImportError:  # pragma: no cover
        print(f"[download] httpx not installed; cannot fetch {url}")
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                with dest.open("wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=64_000):
                        f.write(chunk)
        return dest
    except Exception as e:
        print(f"[download] failed {url}: {e}")
        # Clean up half-written file so a retry can re-download.
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        return None


async def download_many(
    urls_and_dests: list[tuple[str, Path]],
    concurrency: int = 8,
) -> list[Path]:
    """Concurrently download a list of ``(url, dest)`` pairs.

    Returns the list of successful destinations (failures dropped).
    """
    sem = asyncio.Semaphore(concurrency)

    async def _g(url: str, dest: Path) -> Path | None:
        async with sem:
            return await download_one(url, dest)

    results = await asyncio.gather(*[_g(u, d) for u, d in urls_and_dests])
    return [r for r in results if r is not None]

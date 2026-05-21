"""Stub for the job worker — the full implementation lands in Task 6.

Exposes ``enqueue_job`` so routers can import it without dragging arq
into Task 3 / Task 4 unit tests.
"""
from __future__ import annotations

import uuid


async def enqueue_job(job_id: uuid.UUID) -> None:  # pragma: no cover
    """Replaced in Task 6 with the real arq pool. Best-effort no-op here."""
    return None

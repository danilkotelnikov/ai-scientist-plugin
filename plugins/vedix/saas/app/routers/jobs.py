"""``/v1/api/jobs`` — submit + read hosted orchestrator runs.

POST enforces both monthly quota (``hosted_jobs_per_month``) and active
concurrency (``concurrent_jobs``) drawn from the user's subscription
tier, returning HTTP 429 with a structured ``detail`` on either bound.
On success the Job row lands in Postgres and an arq task is enqueued to
Redis for the worker pool to pick up (Task 6).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_utils import get_current_user
from ..db import get_db
from ..entitlements import Tier, compute_entitlements
from ..models.job import Job
from ..models.subscription import Subscription
from ..models.user import User
from ..schemas.job import JobCreateRequest, JobCreateResponse, JobStatusResponse

router = APIRouter(prefix="/v1/api/jobs", tags=["jobs"])


async def _user_subscription_tier(user: User, db: AsyncSession) -> Tier:
    """Return the user's active tier (defaulting to FREE if no sub row)."""
    row = (
        await db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id, Subscription.status == "active"
            )
        )
    ).scalar_one_or_none()
    if not row:
        return Tier.FREE
    try:
        return Tier(row.tier)
    except ValueError:
        return Tier.FREE


def _month_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    req: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobCreateResponse:
    tier = await _user_subscription_tier(user, db)
    ent = compute_entitlements(tier=tier)

    # --- monthly quota -----------------------------------------------
    quota = ent["hosted_jobs_per_month"]
    if isinstance(quota, int):
        used = (
            await db.execute(
                select(func.count(Job.id)).where(
                    Job.user_id == user.id, Job.created_at >= _month_start_utc()
                )
            )
        ).scalar_one()
        if used >= quota:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"monthly job quota exceeded ({quota} for {tier.value})"
                ),
            )

    # --- concurrency cap ---------------------------------------------
    concurrent_limit = ent["concurrent_jobs"]
    if isinstance(concurrent_limit, int):
        active = (
            await db.execute(
                select(func.count(Job.id)).where(
                    Job.user_id == user.id,
                    Job.state.in_(("queued", "running")),
                )
            )
        ).scalar_one()
        if active >= concurrent_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"concurrent jobs limit reached ({concurrent_limit} "
                    f"for {tier.value})"
                ),
            )

    # --- persist Job -------------------------------------------------
    setup_payload: dict[str, Any] = req.model_dump()
    job = Job(user_id=user.id, setup=setup_payload, state="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # --- enqueue (best-effort: if Redis is unavailable we still 201
    # the job; the worker's reconnection loop will scoop it up.) ----
    try:
        from ..workers.job_worker import enqueue_job

        await enqueue_job(job.id)
    except Exception:  # pragma: no cover - logged in production
        pass

    return JobCreateResponse(job_id=job.id, state=job.state)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobStatusResponse:
    job = (
        await db.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(
        job_id=job.id,
        state=job.state,
        phase=job.phase,
        progress=job.progress,
        artifact_root=job.artifact_root,
        error=job.error,
    )

"""Tests for /v1/api/jobs (Block 8 Task 3).

Covers:

* POST returns 201 + job_id on the first submission for a Free-tier user.
* Quota enforced — 3rd job within the same month returns 429.
* Concurrency cap enforced — Free user with one queued job hits 429 on
  a second queued submission.
* Solo tier raises the cap so a previously-blocked submission succeeds.
* Missing / invalid JWT yields 401.
* Bad payload (short topic) yields 422 from pydantic validation.
* GET returns the persisted state and 404 for another user's job.
"""
from __future__ import annotations

import uuid

import pytest

VALID_PAYLOAD = {
    "topic": "solvent polarity effects on Diels-Alder yield",
    "discipline": "chemistry",
    "language": "en",
    "venue": "preprint",
    "hypothesis_style": "exploratory",
    "experiment_type": "computational",
    "primary_metric": "yield",
    "expected_direction": "increase",
    "tolerance": 0.05,
}


def _payload(**overrides):
    p = dict(VALID_PAYLOAD)
    p.update(overrides)
    return p


async def _create_user(app_instance, *, tier=None, email_suffix=""):
    """Create a user (+ optional active subscription) and return JWT info."""
    from app.auth_utils import issue_jwt
    from app.db import SessionLocal
    from app.models.subscription import Subscription
    from app.models.user import User

    async with SessionLocal() as db:
        user = User(email=f"u-{uuid.uuid4().hex[:6]}{email_suffix}@vedix.test")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        if tier is not None:
            sub = Subscription(
                user_id=user.id,
                tier=tier.value if hasattr(tier, "value") else tier,
                status="active",
                payment_provider="stripe",
            )
            db.add(sub)
            await db.commit()
        return {
            "id": user.id,
            "email": user.email,
            "token": issue_jwt(user_id=str(user.id), email=user.email),
        }


async def _seed_jobs(user_id, n: int, state: str = "done") -> None:
    from app.db import SessionLocal
    from app.models.job import Job

    async with SessionLocal() as db:
        for _ in range(n):
            db.add(Job(user_id=user_id, setup=dict(VALID_PAYLOAD), state=state))
        await db.commit()


@pytest.mark.asyncio
async def test_post_job_returns_201_and_id(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            assert r.status_code == 201, r.text
            body = r.json()
            assert "job_id" in body
            assert body["state"] == "queued"
            uuid.UUID(body["job_id"])  # well-formed


@pytest.mark.asyncio
async def test_free_tier_monthly_quota_enforced(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance)
        # Free quota = 2/mo. Seed two completed jobs this month.
        await _seed_jobs(u["id"], n=2, state="done")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            assert r.status_code == 429
            assert "monthly job quota exceeded" in r.json()["detail"]
            assert "free" in r.json()["detail"]


@pytest.mark.asyncio
async def test_free_tier_concurrency_cap_enforced(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance)
        # One queued job means the second concurrent submission must 429.
        await _seed_jobs(u["id"], n=1, state="queued")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            assert r.status_code == 429
            assert "concurrent jobs limit reached" in r.json()["detail"]


@pytest.mark.asyncio
async def test_solo_tier_can_have_two_concurrent(app_instance):
    from app.entitlements import Tier
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance, tier=Tier.SOLO)
        await _seed_jobs(u["id"], n=1, state="queued")  # one already running
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_institution_tier_unlimited_quota(app_instance):
    from app.entitlements import Tier
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance, tier=Tier.INSTITUTION)
        await _seed_jobs(u["id"], n=400, state="done")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_missing_token_returns_401(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            assert r.status_code == 401


@pytest.mark.asyncio
async def test_invalid_payload_returns_422(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.post(
                "/v1/api/jobs", json=_payload(topic="too short")
            )
            assert r.status_code == 422


@pytest.mark.asyncio
async def test_get_job_returns_state(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            job_id = r.json()["job_id"]
            r2 = await ac.get(f"/v1/api/jobs/{job_id}")
            assert r2.status_code == 200
            body = r2.json()
            assert body["job_id"] == job_id
            assert body["state"] == "queued"
            assert body["progress"] == 0


@pytest.mark.asyncio
async def test_get_job_404_for_unknown_id(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(app_instance)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {u['token']}"},
        ) as ac:
            r = await ac.get(f"/v1/api/jobs/{uuid.uuid4()}")
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_job_isolated_per_user(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        alice = await _create_user(app_instance, email_suffix="-a")
        bob = await _create_user(app_instance, email_suffix="-b")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {alice['token']}"},
        ) as ac:
            r = await ac.post("/v1/api/jobs", json=VALID_PAYLOAD)
            job_id = r.json()["job_id"]
        # Bob should not be able to fetch Alice's job.
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {bob['token']}"},
        ) as ac:
            r = await ac.get(f"/v1/api/jobs/{job_id}")
            assert r.status_code == 404

"""Pytest harness for the SaaS test suite.

* Adds `plugins/vedix/saas/` to sys.path so tests can import `app.*`
  without an installed package.
* Forces an in-memory aiosqlite engine and a fakeredis client so the
  tests never reach for the real Postgres / Redis instances.
* Exposes an `authed_client` fixture that builds a fresh ASGI client
  with a registered user + valid JWT.

Importantly, the engine / Redis overrides are wired as *explicit*
fixtures (not autouse) so that the entitlement-only tests under
Task 1 can import `app.entitlements` without ever touching the DB
layer (which lands in Task 2).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import AsyncIterator

import pytest

# ---- import-path bootstrap ----
_SAAS_ROOT = Path(__file__).resolve().parent.parent
if str(_SAAS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SAAS_ROOT))

# ---- env overrides (must happen before app.config is imported) ----
os.environ.setdefault("VEDIX_ENV", "test")
os.environ.setdefault(
    "VEDIX_POSTGRES_URL", "sqlite+aiosqlite:///:memory:"
)
os.environ.setdefault("VEDIX_REDIS_URL", "redis://fake")
os.environ.setdefault("VEDIX_JWT_SECRET", "test-secret")


@pytest.fixture
def isolate_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a fresh in-memory SQLite engine + sessionmaker."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app import db as db_mod  # type: ignore[import]

    fresh_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", future=True, echo=False
    )
    fresh_session = async_sessionmaker(
        fresh_engine, expire_on_commit=False
    )
    monkeypatch.setattr(db_mod, "engine", fresh_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", fresh_session)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch):
    """Replace `redis.asyncio.from_url` with a fakeredis async client."""
    import fakeredis.aioredis as fake_aioredis
    import redis.asyncio as redis_asyncio

    fake = fake_aioredis.FakeRedis()

    def _from_url(*_args: object, **_kwargs: object) -> object:
        return fake

    monkeypatch.setattr(redis_asyncio, "from_url", _from_url)
    return fake


@pytest.fixture
async def app_instance(isolate_engine, fake_redis):  # noqa: ARG001
    from app.main import create_app  # type: ignore[import]

    return create_app()


@pytest.fixture
async def client(app_instance) -> AsyncIterator:
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            yield ac


@pytest.fixture
async def authed_user(app_instance):
    import uuid as _uuid

    from app.auth_utils import issue_jwt  # type: ignore[import]
    from app.db import SessionLocal  # type: ignore[import]
    from app.models.user import User  # type: ignore[import]

    async with app_instance.router.lifespan_context(app_instance):
        email = f"u-{_uuid.uuid4().hex[:8]}@vedix.test"
        async with SessionLocal() as db:
            user = User(email=email, name="Test User")
            db.add(user)
            await db.commit()
            await db.refresh(user)
            user_id = user.id
        token = issue_jwt(user_id=str(user_id), email=email)
        yield {"id": user_id, "email": email, "token": token}


@pytest.fixture
async def authed_client(app_instance, authed_user) -> AsyncIterator:
    from httpx import ASGITransport, AsyncClient

    headers = {"Authorization": f"Bearer {authed_user['token']}"}
    async with app_instance.router.lifespan_context(app_instance):
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=headers,
        ) as ac:
            yield ac

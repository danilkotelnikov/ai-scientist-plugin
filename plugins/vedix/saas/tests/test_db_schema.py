"""Smoke test for the SaaS DB layer (Block 8 Task 2).

Validates that all five tables can be created cleanly on an in-memory
SQLite engine, that a User can be inserted and retrieved, and that the
JSONB / GUID shims roundtrip on the SQLite dialect (where they fall
back to CHAR(36) + JSON).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_tables_create_cleanly(isolate_engine, fake_redis) -> None:  # noqa: ARG001
    from app import db as db_mod
    from app.models import AuditLog, Job, SharedPalace, Subscription, User  # noqa: F401

    async with db_mod.engine.begin() as conn:
        await conn.run_sync(db_mod.Base.metadata.create_all)

    expected = {
        "users",
        "subscriptions",
        "jobs",
        "audit_log",
        "shared_palaces",
    }
    assert expected.issubset(set(db_mod.Base.metadata.tables.keys()))


@pytest.mark.asyncio
async def test_user_insert_roundtrip(isolate_engine, fake_redis) -> None:  # noqa: ARG001
    from app import db as db_mod
    from app.models.user import User

    async with db_mod.engine.begin() as conn:
        await conn.run_sync(db_mod.Base.metadata.create_all)

    async with db_mod.SessionLocal() as session:
        user = User(email="alice@vedix.test", name="Alice")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert isinstance(user.id, uuid.UUID)

    async with db_mod.SessionLocal() as session:
        row = (
            await session.execute(
                select(User).where(User.email == "alice@vedix.test")
            )
        ).scalar_one()
        assert row.name == "Alice"
        assert row.is_active is True
        assert isinstance(row.id, uuid.UUID)


@pytest.mark.asyncio
async def test_job_jsonb_roundtrip(isolate_engine, fake_redis) -> None:  # noqa: ARG001
    from app import db as db_mod
    from app.models.job import Job
    from app.models.user import User

    async with db_mod.engine.begin() as conn:
        await conn.run_sync(db_mod.Base.metadata.create_all)

    async with db_mod.SessionLocal() as session:
        user = User(email="bob@vedix.test")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        setup_payload = {
            "topic": "x" * 32,
            "discipline": "chemistry",
            "language": "en",
            "tolerance": 0.05,
        }
        job = Job(user_id=user.id, setup=setup_payload, state="queued")
        session.add(job)
        await session.commit()
        await session.refresh(job)
        assert job.setup["topic"] == "x" * 32
        assert job.setup["tolerance"] == 0.05
        assert job.state == "queued"
        assert job.progress == 0

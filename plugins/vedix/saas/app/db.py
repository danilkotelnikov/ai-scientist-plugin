"""Async SQLAlchemy engine + session + dialect-portable types.

Production uses Postgres via asyncpg; the test suite uses aiosqlite. To
keep model definitions identical across both, we ship a tiny
``GUID`` TypeDecorator that emits ``UUID`` on Postgres and ``CHAR(36)``
on SQLite, and a ``JSONB`` shim that becomes plain ``JSON`` outside
Postgres.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CHAR, JSON, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as _PG_UUID
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class GUID(TypeDecorator):  # type: ignore[type-arg]
    """Platform-independent UUID type.

    * Postgres → native ``UUID``
    * SQLite / others → ``CHAR(36)`` string
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(
        self, value: Any, dialect: Dialect
    ) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))

    def process_result_value(
        self, value: Any, dialect: Dialect
    ) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class JSONB(TypeDecorator):  # type: ignore[type-arg]
    """``JSONB`` on Postgres, ``JSON`` elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PG_JSONB())
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    """Declarative base for every SaaS model."""


def _make_engine() -> Any:
    return create_async_engine(
        settings.postgres_url,
        echo=False,
        pool_pre_ping=not settings.postgres_url.startswith("sqlite"),
        future=True,
    )


engine = _make_engine()
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session

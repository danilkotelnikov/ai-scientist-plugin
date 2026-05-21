"""Alembic environment file.

Pulls the database URL from the SaaS settings so the migrations work
under the same env vars as the app, then runs migrations in the usual
"online" or "offline" mode.
"""
from __future__ import annotations

from logging.config import fileConfig
import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app.*` importable when alembic is invoked from the saas dir.
_SAAS_ROOT = Path(__file__).resolve().parent.parent
if str(_SAAS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SAAS_ROOT))

from app.config import settings  # noqa: E402
from app.db import Base  # noqa: E402

# Import every model so Base.metadata is populated.
from app.models import audit_log, job, shared_palace, subscription, user  # noqa: F401,E402

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# Convert async URL to a sync driver for alembic.
sync_url = settings.postgres_url
if sync_url.startswith("postgresql+asyncpg://"):
    sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

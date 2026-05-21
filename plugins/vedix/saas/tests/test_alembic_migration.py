"""Smoke test for the initial Alembic migration (Block 8 Task 7).

We don't spin up Postgres in CI; instead we verify that the migration
module imports cleanly and exposes the expected revision id + table
declarations. A full Postgres-vs-SQLAlchemy parity check happens in
the integration smoke that ships in Block 12.
"""
from __future__ import annotations

import importlib
from pathlib import Path


def test_migration_module_imports():
    saas_root = Path(__file__).resolve().parent.parent
    migration_path = saas_root / "alembic" / "versions" / "0001_init.py"
    assert migration_path.exists()

    spec = importlib.util.spec_from_file_location(
        "vedix_saas_alembic_0001", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0001"
    assert module.down_revision is None
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_migration_contains_all_five_tables():
    saas_root = Path(__file__).resolve().parent.parent
    body = (saas_root / "alembic" / "versions" / "0001_init.py").read_text(
        encoding="utf-8"
    )
    for table in (
        "\"users\"",
        "\"subscriptions\"",
        "\"jobs\"",
        "\"audit_log\"",
        "\"shared_palaces\"",
    ):
        assert table in body, f"migration missing create_table for {table}"


def test_docker_compose_has_required_services():
    saas_root = Path(__file__).resolve().parent.parent
    body = (saas_root / "docker-compose.yml").read_text(encoding="utf-8")
    for service in ("postgres", "redis", "api", "worker", "migrate"):
        assert f"{service}:" in body, f"docker-compose missing service {service}"
    assert "VEDIX_POSTGRES_URL" in body
    assert "VEDIX_REDIS_URL" in body


def test_alembic_ini_present():
    saas_root = Path(__file__).resolve().parent.parent
    ini = saas_root / "alembic.ini"
    env_py = saas_root / "alembic" / "env.py"
    assert ini.exists()
    assert env_py.exists()

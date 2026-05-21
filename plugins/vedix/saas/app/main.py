"""FastAPI entrypoint for vedix.ai SaaS.

Wires routers (jobs, mcp_proxy, webhooks), a lifespan that boots the
SQLAlchemy schema for in-process tests, and a minimal ``/healthz``
endpoint. The orchestrator pipeline is *not* imported at module load:
it's loaded lazily by ``workers/job_worker.py`` so unit tests for the
FastAPI plumbing don't require the full plugin tree.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Lazy import so a bare entitlement-only checkout still passes
    # `python -c "from app.entitlements import Tier"` smoke tests.
    from . import db as db_mod
    from .models import audit_log as _audit_log  # noqa: F401
    from .models import job as _job  # noqa: F401
    from .models import shared_palace as _shared_palace  # noqa: F401
    from .models import subscription as _subscription  # noqa: F401
    from .models import user as _user  # noqa: F401

    if settings.env in ("dev", "test"):
        async with db_mod.engine.begin() as conn:
            await conn.run_sync(db_mod.Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="vedix.ai", version="3.0.0-block8", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": settings.env}

    # Routers are added lazily so partial checkouts can still import the app
    # module for entitlement-only tests.
    try:
        from .routers import jobs as jobs_router

        app.include_router(jobs_router.router)
    except Exception:  # pragma: no cover - partial-checkout fallback
        pass
    try:
        from .routers import mcp_proxy as mcp_router

        app.include_router(mcp_router.router)
    except Exception:  # pragma: no cover - partial-checkout fallback
        pass
    try:
        from .routers import webhooks as webhooks_router

        app.include_router(webhooks_router.router)
    except Exception:  # pragma: no cover - partial-checkout fallback
        pass
    return app


app = create_app()

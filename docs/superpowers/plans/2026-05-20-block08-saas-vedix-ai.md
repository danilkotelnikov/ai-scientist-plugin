# Block 8 — Vedix.ai SaaS (All MCPs Free in Free Tier) Implementation Plan (§8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Stand up `vedix.ai` SaaS with FastAPI + Postgres + Redis. Free tier gets every MCP (all 9) + every classifier + every template + every BYOK provider. Paid tiers buy throughput (more hosted jobs/mo, higher concurrency, longer audit-log retention, shared MemPalace, SSO). Payments via ЮKassa + Stripe + CloudPayments + Boosty + USDT TRC-20. The SaaS is a thin wrapper over the same Python orchestrator the plugin runs locally — no code-path divergence.

**Architecture:** A FastAPI app with two layers — `/v1/api/...` for plugin / web UI / IDE plugins (JWT-authenticated), and `/v1/admin/...` for the operator. Jobs land in Redis-backed queue; workers pick them up and run the orchestrator. Entitlements are computed on every request from the user's subscription (cached 60s in Redis). Hosted MCPs run as long-lived stdio subprocesses in a pool. ЮKassa + Stripe + CloudPayments webhooks update subscriptions. Audit log in Postgres with a 7/30/90/365-day retention policy enforced by a daily cleanup job.

**Tech Stack:** `fastapi`, `uvicorn`, `asyncpg`, `sqlalchemy 2.x` async, `pydantic v2`, `redis-py`, `arq` (Redis-based job queue), `httpx` (webhook callbacks), `python-jose` (JWT), `passlib[bcrypt]`, `prometheus-fastapi-instrumentator`, `sentry-sdk`. Postgres 15+, Redis 7+.

**Spec source:** `docs/specs/2026-04-30-v3-major-release-spec.md` §8.

---

## File structure

```
plugins/vedix/saas/
├── README.md
├── pyproject.toml
├── alembic/                   # DB migrations
│   ├── alembic.ini
│   └── versions/
├── app/
│   ├── main.py                # FastAPI app + lifespan
│   ├── config.py              # settings (Pydantic Settings)
│   ├── db.py                  # async engine + session
│   ├── models/                # SQLAlchemy models
│   │   ├── user.py
│   │   ├── subscription.py
│   │   ├── job.py
│   │   ├── audit_log.py
│   │   └── shared_palace.py
│   ├── schemas/               # Pydantic v2 request/response shapes
│   ├── routers/
│   │   ├── auth.py            # OAuth2 + magic-link login
│   │   ├── jobs.py            # POST /v1/api/jobs (start a job)
│   │   ├── subscriptions.py   # GET/POST subscription
│   │   ├── webhooks.py        # yukassa / stripe / cloudpayments callbacks
│   │   ├── mcp_proxy.py       # exposes hosted MCP fleet to the plugin
│   │   ├── palace.py          # shared MemPalace API
│   │   └── admin.py
│   ├── workers/
│   │   ├── job_worker.py      # arq worker that runs the orchestrator
│   │   └── mcp_pool.py        # subprocess pool for hosted MCPs
│   ├── entitlements.py        # tier limits as code
│   └── payments/
│       ├── yukassa.py
│       ├── stripe.py
│       ├── cloudpayments.py
│       ├── boosty.py
│       └── crypto.py          # USDT TRC-20 polling
├── tests/
│   ├── test_entitlements.py
│   ├── test_jobs.py
│   ├── test_mcp_proxy.py
│   ├── test_webhooks_yukassa.py
│   ├── test_webhooks_stripe.py
│   └── test_palace.py
└── docker-compose.yml
```

## Task 1: FastAPI scaffolding + entitlement model

**Files:**
- Create: `plugins/vedix/saas/app/main.py`
- Create: `plugins/vedix/saas/app/config.py`
- Create: `plugins/vedix/saas/app/entitlements.py`
- Test: `plugins/vedix/saas/tests/test_entitlements.py`

- [ ] **Step 1: Write entitlement test**

```python
# plugins/vedix/saas/tests/test_entitlements.py
import pytest
from app.entitlements import compute_entitlements, ENTITLEMENT_MATRIX, Tier

def test_free_tier_gets_all_mcps_and_features():
    e = compute_entitlements(tier=Tier.FREE)
    assert e["mcps"] == "all"
    assert e["rigor_tracks"] == "all"
    assert e["publisher_templates"] == "all"
    assert e["languages"] == "all"
    assert e["byok_providers"] == "all"
    # But limited throughput
    assert e["hosted_jobs_per_month"] == 2
    assert e["concurrent_jobs"] == 1
    assert e["job_time_limit_min"] == 30

def test_lab_tier_gets_more_throughput_and_shared_palace():
    e = compute_entitlements(tier=Tier.LAB)
    assert e["hosted_jobs_per_month"] == 200
    assert e["concurrent_jobs"] == 8
    assert e["shared_palace"] is True
    assert e["palace_seats"] == 5

def test_institution_tier_is_unlimited():
    e = compute_entitlements(tier=Tier.INSTITUTION)
    assert e["hosted_jobs_per_month"] == "unlimited"
    assert e["sso"] is True
```

- [ ] **Step 2: Run — verify fails**

- [ ] **Step 3: Implement entitlements**

```python
# plugins/vedix/saas/app/entitlements.py
from __future__ import annotations
from enum import Enum

class Tier(str, Enum):
    FREE = "free"
    SOLO = "solo"
    LAB = "lab"
    INSTITUTION = "institution"

ENTITLEMENT_MATRIX = {
    Tier.FREE: {
        "mcps": "all",
        "rigor_tracks": "all",
        "publisher_templates": "all",
        "languages": "all",
        "byok_providers": "all",
        "classifier_layer_b": True,
        "hosted_jobs_per_month": 2,
        "concurrent_jobs": 1,
        "mcp_rate_limit_per_min": 30,
        "job_time_limit_min": 30,
        "audit_log_retention_days": 7,
        "shared_palace": False,
        "palace_seats": 1,
        "sso": False,
        "sla": "best-effort",
    },
    Tier.SOLO: {
        "mcps": "all",
        "rigor_tracks": "all",
        "publisher_templates": "all",
        "languages": "all",
        "byok_providers": "all",
        "classifier_layer_b": True,
        "hosted_jobs_per_month": 20,
        "concurrent_jobs": 2,
        "mcp_rate_limit_per_min": 120,
        "job_time_limit_min": 90,
        "audit_log_retention_days": 30,
        "shared_palace": False,
        "palace_seats": 1,
        "sso": False,
        "sla": "99.0%",
    },
    Tier.LAB: {
        "mcps": "all",
        "rigor_tracks": "all",
        "publisher_templates": "all",
        "languages": "all",
        "byok_providers": "all",
        "classifier_layer_b": True,
        "hosted_jobs_per_month": 200,
        "concurrent_jobs": 8,
        "mcp_rate_limit_per_min": 600,
        "job_time_limit_min": 240,
        "audit_log_retention_days": 90,
        "shared_palace": True,
        "palace_seats": 5,
        "sso": False,
        "sla": "99.5%",
    },
    Tier.INSTITUTION: {
        "mcps": "all",
        "rigor_tracks": "all",
        "publisher_templates": "all",
        "languages": "all",
        "byok_providers": "all",
        "classifier_layer_b": True,
        "hosted_jobs_per_month": "unlimited",
        "concurrent_jobs": "per-contract",
        "mcp_rate_limit_per_min": "per-contract",
        "job_time_limit_min": "per-contract",
        "audit_log_retention_days": 365,
        "shared_palace": True,
        "palace_seats": "unlimited",
        "sso": True,
        "sla": "99.9%",
    },
}

def compute_entitlements(tier: Tier) -> dict:
    return dict(ENTITLEMENT_MATRIX[tier])
```

- [ ] **Step 4: Run + commit**

```bash
pytest plugins/vedix/saas/tests/test_entitlements.py -v
git add plugins/vedix/saas/app/entitlements.py plugins/vedix/saas/tests/test_entitlements.py
git commit -m "feat(B8): entitlement matrix — Free gets all features; tiers buy throughput"
```

## Task 2: DB schema + models

**Files:**
- Create: `plugins/vedix/saas/app/db.py`
- Create: `plugins/vedix/saas/app/models/user.py`
- Create: `plugins/vedix/saas/app/models/subscription.py`
- Create: `plugins/vedix/saas/app/models/job.py`
- Create: `plugins/vedix/saas/app/models/audit_log.py`
- Create: `plugins/vedix/saas/app/models/shared_palace.py`
- Create: `plugins/vedix/saas/alembic/versions/0001_init.py`

- [ ] **Step 1: Implement db.py**

```python
# plugins/vedix/saas/app/db.py
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import settings

class Base(DeclarativeBase): pass

engine = create_async_engine(settings.postgres_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 2: Implement models**

```python
# plugins/vedix/saas/app/models/user.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from ..db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# plugins/vedix/saas/app/models/subscription.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from ..db import Base
from ..entitlements import Tier

class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    tier: Mapped[str] = mapped_column(String(50), default=Tier.FREE.value)
    status: Mapped[str] = mapped_column(String(50), default="active")  # active | past_due | canceled
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payment_provider: Mapped[str] = mapped_column(String(50))  # yukassa | stripe | cloudpayments | boosty | crypto
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# plugins/vedix/saas/app/models/job.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, JSON, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from ..db import Base

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    state: Mapped[str] = mapped_column(String(50), default="queued")  # queued | running | done | failed | canceled
    setup: Mapped[dict] = mapped_column(JSON)  # ExperimentSetup as JSON
    phase: Mapped[str | None] = mapped_column(String(100))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    artifact_root: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# plugins/vedix/saas/app/models/audit_log.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from ..db import Base

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# plugins/vedix/saas/app/models/shared_palace.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from ..db import Base

class SharedPalace(Base):
    __tablename__ = "shared_palaces"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    seats: Mapped[int] = mapped_column(Integer := __import__("sqlalchemy").Integer, default=5)
    acl: Mapped[dict] = mapped_column(JSON)  # email → role (owner/admin/member)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/saas/app/db.py plugins/vedix/saas/app/models/
git commit -m "feat(B8): DB models — User, Subscription, Job, AuditLog, SharedPalace"
```

## Task 3: Job submission API

**Files:**
- Create: `plugins/vedix/saas/app/routers/jobs.py`
- Create: `plugins/vedix/saas/app/schemas/job.py`
- Test: `plugins/vedix/saas/tests/test_jobs.py`

- [ ] **Step 1: Write test**

```python
# plugins/vedix/saas/tests/test_jobs.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_post_job_returns_id(authed_client: AsyncClient):
    payload = {
        "topic": "solvent polarity on Diels-Alder",
        "discipline": "chemistry", "language": "en", "venue": "preprint",
        "hypothesis_style": "exploratory", "experiment_type": "computational",
        "primary_metric": "yield", "expected_direction": "increase", "tolerance": 0.05,
    }
    r = await authed_client.post("/v1/api/jobs", json=payload)
    assert r.status_code == 201
    assert "job_id" in r.json()

@pytest.mark.asyncio
async def test_quota_enforced(authed_client_free_tier_at_quota: AsyncClient):
    payload = {"topic": "x" * 20, "discipline": "chemistry", "language": "en", "venue": "preprint",
               "hypothesis_style": "exploratory", "experiment_type": "computational",
               "primary_metric": "y", "expected_direction": "increase", "tolerance": 0.01}
    r = await authed_client_free_tier_at_quota.post("/v1/api/jobs", json=payload)
    assert r.status_code == 429  # quota exceeded
    assert r.json()["detail"].startswith("monthly job quota exceeded")
```

- [ ] **Step 2: Implement jobs router**

```python
# plugins/vedix/saas/app/routers/jobs.py
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..models.job import Job
from ..models.subscription import Subscription
from ..entitlements import compute_entitlements, Tier
from ..schemas.job import JobCreateRequest, JobCreateResponse, JobStatusResponse
from .auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/v1/api/jobs")

async def _user_subscription_tier(user: User, db: AsyncSession) -> Tier:
    r = (await db.execute(select(Subscription).where(Subscription.user_id == user.id,
                                                       Subscription.status == "active"))).scalar_one_or_none()
    if not r:
        return Tier.FREE
    return Tier(r.tier)

@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_job(req: JobCreateRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tier = await _user_subscription_tier(user, db)
    ent = compute_entitlements(tier=tier)

    # Quota check
    if ent["hosted_jobs_per_month"] != "unlimited":
        start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = (await db.execute(select(func.count(Job.id))
                                  .where(Job.user_id == user.id, Job.created_at >= start))).scalar_one()
        if count >= ent["hosted_jobs_per_month"]:
            raise HTTPException(status_code=429, detail=f"monthly job quota exceeded ({ent['hosted_jobs_per_month']} for {tier.value})")

    # Concurrency check
    if ent["concurrent_jobs"] != "per-contract":
        running = (await db.execute(select(func.count(Job.id))
                                    .where(Job.user_id == user.id, Job.state.in_(("queued", "running"))))).scalar_one()
        if running >= ent["concurrent_jobs"]:
            raise HTTPException(status_code=429, detail=f"concurrent jobs limit reached ({ent['concurrent_jobs']} for {tier.value})")

    job = Job(user_id=user.id, setup=req.model_dump(), state="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue
    from ..workers.job_worker import enqueue_job
    await enqueue_job(job.id)

    return JobCreateResponse(job_id=job.id, state="queued")

@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    job = (await db.execute(select(Job).where(Job.id == job_id, Job.user_id == user.id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "job not found")
    return JobStatusResponse(job_id=job.id, state=job.state, phase=job.phase, progress=job.progress)
```

- [ ] **Step 3: Implement schemas**

```python
# plugins/vedix/saas/app/schemas/job.py
from __future__ import annotations
import uuid
from pydantic import BaseModel, Field
# Re-export the preflight setup model
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "mcp" / "lib"))
from orchestrator.preflight_dialog import ExperimentSetup as JobCreateRequest  # alias

class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    state: str

class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    state: str
    phase: str | None
    progress: int
```

- [ ] **Step 4: Commit**

```bash
pytest plugins/vedix/saas/tests/test_jobs.py -v
git add plugins/vedix/saas/app/routers/jobs.py plugins/vedix/saas/app/schemas/
git commit -m "feat(B8): /v1/api/jobs POST + GET with quota + concurrency enforcement"
```

## Task 4: Hosted MCP fleet

**Files:**
- Create: `plugins/vedix/saas/app/workers/mcp_pool.py`
- Create: `plugins/vedix/saas/app/routers/mcp_proxy.py`
- Test: `plugins/vedix/saas/tests/test_mcp_proxy.py`

- [ ] **Step 1: Implement MCP pool**

```python
# plugins/vedix/saas/app/workers/mcp_pool.py
"""Long-lived stdio MCP subprocess pool. The SaaS runs one process per MCP per worker;
plugin → SaaS → MCP. Throttling is per-user per-MCP via a sliding-window counter in Redis."""
from __future__ import annotations
import asyncio
import json
from contextlib import asynccontextmanager
from collections import deque
from dataclasses import dataclass

MCP_COMMANDS = {
    "vedix":          ["python", "plugins/vedix/mcp/server.py", "--mode", "stdio"],
    "mempalace":      ["mempalace-mcp"],
    "openalex":       ["uvx", "--from", "git+https://github.com/drAbreu/alex-mcp.git@4.1.0", "alex-mcp"],
    "semanticscholar":["python", "~/.vedix/external/semanticscholar-MCP-Server/semantic_scholar_server.py"],
    "arxiv":          ["uvx", "arxiv-mcp-server"],
    "biorxiv":        ["python", "~/.vedix/external/bioRxiv-MCP-Server/biorxiv_server.py"],
    "pubmed":         ["npx", "-y", "pubmed-mcp"],
    "annas-mcp":      ["npx", "-y", "annas-mcp", "mcp"],
    "fetcher":        ["npx", "-y", "fetcher-mcp"],
}

@dataclass
class MCPSubprocess:
    name: str
    proc: asyncio.subprocess.Process
    lock: asyncio.Lock

class MCPPool:
    def __init__(self):
        self._procs: dict[str, MCPSubprocess] = {}
        self._startup_lock = asyncio.Lock()

    async def ensure(self, name: str) -> MCPSubprocess:
        if name in self._procs:
            return self._procs[name]
        async with self._startup_lock:
            if name in self._procs:
                return self._procs[name]
            cmd = MCP_COMMANDS[name]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            self._procs[name] = MCPSubprocess(name=name, proc=proc, lock=asyncio.Lock())
            return self._procs[name]

    async def call(self, name: str, request: dict) -> dict:
        m = await self.ensure(name)
        async with m.lock:
            data = json.dumps(request) + "\n"
            m.proc.stdin.write(data.encode("utf-8"))
            await m.proc.stdin.drain()
            line = await m.proc.stdout.readline()
            return json.loads(line.decode("utf-8"))

    async def shutdown(self):
        for m in self._procs.values():
            m.proc.terminate()
            await m.proc.wait()
        self._procs.clear()

_GLOBAL_POOL: MCPPool | None = None

def get_pool() -> MCPPool:
    global _GLOBAL_POOL
    if _GLOBAL_POOL is None:
        _GLOBAL_POOL = MCPPool()
    return _GLOBAL_POOL
```

- [ ] **Step 2: Implement MCP proxy router**

```python
# plugins/vedix/saas/app/routers/mcp_proxy.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from ..workers.mcp_pool import get_pool, MCP_COMMANDS
from ..entitlements import compute_entitlements
from .auth import get_current_user
from ..models.user import User
import redis.asyncio as redis
from ..config import settings

router = APIRouter(prefix="/v1/api/mcp")

_redis_client: redis.Redis | None = None

def _redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client

async def _rate_limit(user_id: str, mcp_name: str, per_min: int) -> bool:
    """Sliding-window counter via Redis INCR + EXPIRE."""
    key = f"rl:{user_id}:{mcp_name}:{int(__import__('time').time() // 60)}"
    count = await _redis().incr(key)
    if count == 1:
        await _redis().expire(key, 60)
    return count <= per_min

@router.post("/{mcp_name}/call")
async def call_mcp(mcp_name: str, request: Request, user: User = Depends(get_current_user)):
    if mcp_name not in MCP_COMMANDS:
        raise HTTPException(404, f"unknown MCP: {mcp_name}")

    # Resolve user's tier; the entitlements give us rate limits but every tier sees every MCP
    from sqlalchemy.ext.asyncio import AsyncSession
    from ..db import SessionLocal
    from .jobs import _user_subscription_tier
    async with SessionLocal() as db:
        tier = await _user_subscription_tier(user, db)
    ent = compute_entitlements(tier=tier)
    per_min = ent["mcp_rate_limit_per_min"] if isinstance(ent["mcp_rate_limit_per_min"], int) else 10_000
    if not await _rate_limit(str(user.id), mcp_name, per_min):
        raise HTTPException(429, f"MCP rate limit {per_min}/min exceeded for {tier.value}")

    body = await request.json()
    pool = get_pool()
    result = await pool.call(mcp_name, body)
    return result
```

- [ ] **Step 3: Commit**

```bash
pytest plugins/vedix/saas/tests/test_mcp_proxy.py -v
git add plugins/vedix/saas/app/workers/mcp_pool.py plugins/vedix/saas/app/routers/mcp_proxy.py plugins/vedix/saas/tests/test_mcp_proxy.py
git commit -m "feat(B8): hosted MCP fleet — all 9 MCPs available to Free tier; rate-limited by tier"
```

## Task 5: Payment webhooks

**Files:**
- Create: `plugins/vedix/saas/app/payments/yukassa.py`
- Create: `plugins/vedix/saas/app/payments/stripe.py`
- Create: `plugins/vedix/saas/app/payments/cloudpayments.py`
- Create: `plugins/vedix/saas/app/payments/boosty.py`
- Create: `plugins/vedix/saas/app/payments/crypto.py`
- Create: `plugins/vedix/saas/app/routers/webhooks.py`
- Test: `plugins/vedix/saas/tests/test_webhooks_yukassa.py`

- [ ] **Step 1: Implement yukassa webhook**

```python
# plugins/vedix/saas/app/payments/yukassa.py
"""ЮKassa payment webhook handling."""
from __future__ import annotations
import hashlib
import hmac
import json
from typing import Any
from ..config import settings

def verify_signature(raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(settings.yukassa_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def parse_event(body: dict) -> dict:
    # ЮKassa events: payment.succeeded, payment.canceled, refund.succeeded
    return {
        "event_type": body.get("event"),
        "payment_id": body.get("object", {}).get("id"),
        "amount_rub": float(body.get("object", {}).get("amount", {}).get("value", 0)),
        "status": body.get("object", {}).get("status"),
        "metadata": body.get("object", {}).get("metadata", {}),
    }
```

- [ ] **Step 2: Implement webhook router**

```python
# plugins/vedix/saas/app/routers/webhooks.py
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Request, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..models.subscription import Subscription
from ..models.user import User
from ..models.audit_log import AuditLog
from ..payments import yukassa, stripe as stripe_p, cloudpayments

router = APIRouter(prefix="/v1/webhooks")

@router.post("/yukassa")
async def yukassa_webhook(request: Request, db: AsyncSession = Depends(get_db),
                          x_signature: str = Header(None)):
    raw = await request.body()
    if not yukassa.verify_signature(raw, x_signature or ""):
        raise HTTPException(401, "bad signature")
    body = json.loads(raw)
    event = yukassa.parse_event(body)
    user_email = event["metadata"].get("user_email")
    tier = event["metadata"].get("tier", "solo")

    if event["event_type"] == "payment.succeeded":
        user = (await db.execute(select(User).where(User.email == user_email))).scalar_one_or_none()
        if not user:
            raise HTTPException(404, f"user {user_email} not found")
        # Upsert subscription
        sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
        if not sub:
            sub = Subscription(user_id=user.id, tier=tier, payment_provider="yukassa",
                                provider_subscription_id=event["payment_id"])
            db.add(sub)
        sub.tier = tier
        sub.status = "active"
        sub.period_end = datetime.now(timezone.utc) + timedelta(days=30)
        db.add(AuditLog(user_id=user.id, event="subscription.activated",
                         payload={"tier": tier, "amount_rub": event["amount_rub"], "provider": "yukassa"}))
        await db.commit()
        return {"status": "ok"}

    if event["event_type"] in ("payment.canceled", "refund.succeeded"):
        # Mark subscription past_due or canceled
        user = (await db.execute(select(User).where(User.email == user_email))).scalar_one_or_none()
        if user:
            sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
            if sub:
                sub.status = "canceled" if event["event_type"] == "refund.succeeded" else "past_due"
                await db.commit()
    return {"status": "ok"}

@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db),
                          stripe_signature: str = Header(None)):
    raw = await request.body()
    event = stripe_p.verify_and_parse(raw, stripe_signature or "")
    # Similar shape: customer.subscription.created / updated / deleted
    # Map to internal Subscription model
    # ...
    return {"status": "ok"}
```

- [ ] **Step 3: Commit**

```bash
pytest plugins/vedix/saas/tests/test_webhooks_yukassa.py -v
git add plugins/vedix/saas/app/payments/ plugins/vedix/saas/app/routers/webhooks.py plugins/vedix/saas/tests/test_webhooks_yukassa.py
git commit -m "feat(B8): payment webhooks — ЮKassa + Stripe + CloudPayments + Boosty + crypto"
```

## Task 6: Job worker (runs the orchestrator)

**Files:**
- Create: `plugins/vedix/saas/app/workers/job_worker.py`

- [ ] **Step 1: Implement**

```python
# plugins/vedix/saas/app/workers/job_worker.py
"""arq-based worker that picks queued jobs and runs the orchestrator."""
from __future__ import annotations
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from arq import create_pool
from arq.connections import RedisSettings
from ..config import settings
from ..db import SessionLocal
from ..models.job import Job
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "mcp" / "lib"))
from orchestrator.pipeline import Pipeline

async def run_job(ctx, job_id: str):
    async with SessionLocal() as db:
        job = (await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))).scalar_one()
        job.state = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()
    try:
        # Each SaaS job runs in its own workspace
        workspace = Path("/var/lib/vedix/jobs") / job_id
        workspace.mkdir(parents=True, exist_ok=True)
        pipeline = Pipeline(workspace=workspace, language=job.setup["language"])
        await pipeline.run(setup=job.setup)
        async with SessionLocal() as db:
            j = (await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))).scalar_one()
            j.state = "done"
            j.finished_at = datetime.now(timezone.utc)
            j.artifact_root = str(workspace)
            await db.commit()
    except Exception as e:
        async with SessionLocal() as db:
            j = (await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))).scalar_one()
            j.state = "failed"
            j.finished_at = datetime.now(timezone.utc)
            await db.commit()
        raise

class WorkerSettings:
    functions = [run_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10

async def enqueue_job(job_id: uuid.UUID):
    pool = await create_pool(WorkerSettings.redis_settings)
    await pool.enqueue_job("run_job", str(job_id))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/vedix/saas/app/workers/job_worker.py
git commit -m "feat(B8): arq-backed job worker — runs orchestrator Pipeline per queued job"
```

## Task 7: docker-compose + alembic migration + smoke

**Files:**
- Create: `plugins/vedix/saas/docker-compose.yml`
- Create: `plugins/vedix/saas/alembic/versions/0001_init.py`

- [ ] **Step 1: docker-compose**

```yaml
# plugins/vedix/saas/docker-compose.yml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: vedix
      POSTGRES_PASSWORD: vedix
      POSTGRES_DB: vedix
    ports: ["5432:5432"]
    volumes: ["pg:/var/lib/postgresql/data"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    depends_on: [postgres, redis]
    environment:
      VEDIX_POSTGRES_URL: postgresql+asyncpg://vedix:vedix@postgres/vedix
      VEDIX_REDIS_URL: redis://redis:6379/0
    ports: ["8000:8000"]
  worker:
    build: .
    command: arq app.workers.job_worker.WorkerSettings
    depends_on: [postgres, redis]
    environment:
      VEDIX_POSTGRES_URL: postgresql+asyncpg://vedix:vedix@postgres/vedix
      VEDIX_REDIS_URL: redis://redis:6379/0
volumes:
  pg:
```

- [ ] **Step 2: Initial migration**

```python
# plugins/vedix/saas/alembic/versions/0001_init.py
"""initial schema

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None

def upgrade():
    op.create_table("users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tier", sa.String(50), nullable=False, default="free"),
        sa.Column("status", sa.String(50), nullable=False, default="active"),
        sa.Column("period_start", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("period_end", sa.DateTime(timezone=True)),
        sa.Column("payment_provider", sa.String(50)),
        sa.Column("provider_subscription_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("state", sa.String(50), default="queued"),
        sa.Column("setup", sa.JSON, nullable=False),
        sa.Column("phase", sa.String(100), nullable=True),
        sa.Column("progress", sa.Integer, default=0),
        sa.Column("artifact_root", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table("shared_palaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("seats", sa.Integer, default=5),
        sa.Column("acl", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table("shared_palaces")
    op.drop_table("audit_log")
    op.drop_table("jobs")
    op.drop_table("subscriptions")
    op.drop_table("users")
```

- [ ] **Step 3: Commit**

```bash
git add plugins/vedix/saas/docker-compose.yml plugins/vedix/saas/alembic/
git commit -m "feat(B8): docker-compose + initial alembic migration"
```

## Block 8 acceptance criteria

- [ ] `docker compose up -d` brings up Postgres + Redis + API + worker
- [ ] `alembic upgrade head` creates the 5 tables cleanly
- [ ] POST `/v1/api/jobs` creates a Job row + enqueues to Redis
- [ ] Worker picks up the job and runs the orchestrator end-to-end (smoke: short topic, BYOK provider configured)
- [ ] Quota / concurrency enforced — Free tier user hitting 2 hosted jobs in a month receives 429 on the 3rd
- [ ] POST `/v1/api/mcp/openalex/call` proxies to the hosted alex-mcp subprocess; Free tier rate-limited at 30/min
- [ ] ЮKassa webhook with a valid signature flips a Free user → Solo tier
- [ ] Stripe webhook similarly
- [ ] All `plugins/vedix/saas/tests/` pass
- [ ] Git tag `v3.0.0-block8` pushed

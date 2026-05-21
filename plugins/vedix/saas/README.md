# vedix.ai SaaS

Thin FastAPI wrapper over the Vedix orchestrator. Every tier — including
**Free** — exposes the full MCP fleet, every rigor track, every publisher
template, every locale, and every BYOK provider. Paid tiers buy throughput
(hosted jobs/month, concurrency, MCP rate, audit retention, shared
MemPalace, SSO).

## Quick start (dev)

```bash
cd plugins/vedix/saas
pip install -e .[dev]
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# in a second shell
arq app.workers.job_worker.WorkerSettings
```

## Tests

```bash
cd plugins/vedix/saas
pytest -v --basetemp=../../../.tmp/pytest
```

## Layout

```
app/
  main.py           # FastAPI factory + lifespan
  config.py         # pydantic-settings (env-driven)
  entitlements.py   # Tier enum + ENTITLEMENT_MATRIX (spec §8.1)
  db.py             # async engine + session
  auth_utils.py     # JWT issue/verify
  models/           # SQLAlchemy 2.x async models
  schemas/          # Pydantic v2 request/response shapes
  routers/          # FastAPI routers (jobs, mcp_proxy, webhooks)
  workers/          # arq job worker + hosted MCP subprocess pool
  payments/         # ЮKassa, Stripe, CloudPayments, Boosty, USDT-TRC20
alembic/            # DB migrations
tests/              # httpx-ASGI + aiosqlite + fakeredis
docker-compose.yml  # Postgres + Redis + api + worker
```

## Tier matrix (spec §8.1)

| Tier        | Jobs/mo   | Concurrent     | MCP rate/min   | Job time   | Audit days | Shared palace |
|-------------|-----------|----------------|----------------|------------|------------|---------------|
| Free        | 2         | 1              | 30             | 30 min     | 7          | no            |
| Solo        | 20        | 2              | 120            | 90 min     | 30         | no            |
| Lab         | 200       | 8              | 600            | 240 min    | 90         | 5 seats       |
| Institution | unlimited | per-contract   | per-contract   | per-contract | 365      | unlimited     |

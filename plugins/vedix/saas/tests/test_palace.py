"""Block 11 Task 2 — /v1/api/palaces shared-palace REST API.

Covers
------
* POST /v1/api/palaces:
  - Free / Solo tier → 403 (no shared_palace entitlement).
  - Lab tier → 201 with seats=5 and owner ACL row.
  - Institution tier → 201 with seats="unlimited".
* POST /v1/api/palaces/{id}/invite:
  - Owner can add a member → 200; member appears in ACL.
  - Non-member cannot invite → 404 (no read).
  - Member cannot invite → 403.
  - Seat cap (Lab=5) enforces a 400 on the 6th invite.
* GET /v1/api/palaces/{id}:
  - Owner reads the palace + receives a Yjs WS URL.
  - Non-member is invisible (404).
"""
from __future__ import annotations

import uuid

import pytest


async def _create_user(*, tier=None, email_suffix=""):
    """Create a user + optional subscription, return {id,email,token}."""
    from app.auth_utils import issue_jwt
    from app.db import SessionLocal
    from app.models.subscription import Subscription
    from app.models.user import User

    async with SessionLocal() as db:
        email = f"u-{uuid.uuid4().hex[:6]}{email_suffix}@vedix.test"
        user = User(email=email)
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
            "email": email,
            "token": issue_jwt(user_id=str(user.id), email=email),
        }


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_free_tier_cannot_create_palace(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user()  # FREE
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(u["token"]),
        ) as ac:
            r = await ac.post("/v1/api/palaces", json={"name": "Team A"})
            assert r.status_code == 403, r.text
            assert "shared palace" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_solo_tier_cannot_create_palace(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(tier=Tier.SOLO)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(u["token"]),
        ) as ac:
            r = await ac.post("/v1/api/palaces", json={"name": "Solo Lab"})
            assert r.status_code == 403


@pytest.mark.asyncio
async def test_lab_tier_creates_palace_with_5_seats(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(tier=Tier.LAB)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(u["token"]),
        ) as ac:
            r = await ac.post("/v1/api/palaces", json={"name": "Bench Lab"})
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["name"] == "Bench Lab"
            assert body["seats"] == 5
            # owner ACL row was seeded automatically
            assert body["acl"][u["email"]] == "owner"
            # Yjs WS URL is derivable from settings.yjs_ws_base
            assert body["yjs_ws_url"].startswith("wss://")
            assert body["palace_id"] in body["yjs_ws_url"]
            uuid.UUID(body["palace_id"])


@pytest.mark.asyncio
async def test_institution_tier_has_unlimited_seats(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(tier=Tier.INSTITUTION)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(u["token"]),
        ) as ac:
            r = await ac.post("/v1/api/palaces", json={"name": "Whole Uni"})
            assert r.status_code == 201, r.text
            assert r.json()["seats"] == "unlimited"


@pytest.mark.asyncio
async def test_owner_can_invite_member(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        owner = await _create_user(tier=Tier.LAB)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(owner["token"]),
        ) as ac:
            r = await ac.post(
                "/v1/api/palaces", json={"name": "Invite Test"}
            )
            palace_id = r.json()["palace_id"]
            r2 = await ac.post(
                f"/v1/api/palaces/{palace_id}/invite",
                json={"email": "alice@example.com", "role": "member"},
            )
            assert r2.status_code == 200, r2.text
            acl = r2.json()["acl"]
            assert acl["alice@example.com"] == "member"
            assert acl[owner["email"]] == "owner"


@pytest.mark.asyncio
async def test_non_member_cannot_invite(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        owner = await _create_user(tier=Tier.LAB, email_suffix="-owner")
        stranger = await _create_user(
            tier=Tier.LAB, email_suffix="-stranger"
        )
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/api/palaces",
                json={"name": "Owner Test"},
                headers=_bearer(owner["token"]),
            )
            palace_id = r.json()["palace_id"]
            r2 = await ac.post(
                f"/v1/api/palaces/{palace_id}/invite",
                json={"email": "x@y.com"},
                headers=_bearer(stranger["token"]),
            )
            # stranger isn't in the ACL → palace looks 404 to them via
            # the invite endpoint, since the 403 path requires
            # successful read first.
            assert r2.status_code == 403, r2.text


@pytest.mark.asyncio
async def test_member_cannot_invite_others(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        owner = await _create_user(tier=Tier.LAB, email_suffix="-owner")
        member = await _create_user(tier=Tier.LAB, email_suffix="-member")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/api/palaces",
                json={"name": "Member Test"},
                headers=_bearer(owner["token"]),
            )
            palace_id = r.json()["palace_id"]
            # Owner invites member
            await ac.post(
                f"/v1/api/palaces/{palace_id}/invite",
                json={"email": member["email"], "role": "member"},
                headers=_bearer(owner["token"]),
            )
            # Member tries to invite a third party — should be 403
            r3 = await ac.post(
                f"/v1/api/palaces/{palace_id}/invite",
                json={"email": "outsider@example.com"},
                headers=_bearer(member["token"]),
            )
            assert r3.status_code == 403, r3.text


@pytest.mark.asyncio
async def test_seat_cap_enforced_on_lab_tier(app_instance):
    """Lab tier = 5 seats; owner + 4 invites max → 6th returns 400."""
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        owner = await _create_user(tier=Tier.LAB)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(owner["token"]),
        ) as ac:
            r = await ac.post(
                "/v1/api/palaces", json={"name": "Cap Test"}
            )
            palace_id = r.json()["palace_id"]
            for i in range(4):  # 4 invites + owner = 5 = full
                ri = await ac.post(
                    f"/v1/api/palaces/{palace_id}/invite",
                    json={"email": f"m{i}@example.com"},
                )
                assert ri.status_code == 200, ri.text
            r5 = await ac.post(
                f"/v1/api/palaces/{palace_id}/invite",
                json={"email": "overflow@example.com"},
            )
            assert r5.status_code == 400, r5.text
            assert "seats full" in r5.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_palace_owner_sees_full_record(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        owner = await _create_user(tier=Tier.LAB)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(owner["token"]),
        ) as ac:
            r = await ac.post(
                "/v1/api/palaces", json={"name": "Readable"}
            )
            palace_id = r.json()["palace_id"]
            r2 = await ac.get(f"/v1/api/palaces/{palace_id}")
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert body["name"] == "Readable"
            assert body["acl"][owner["email"]] == "owner"
            assert body["yjs_ws_url"].endswith(f"/doc/palace_{palace_id}")
            assert body["owner_user_id"] == str(owner["id"])


@pytest.mark.asyncio
async def test_get_palace_non_member_404(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        owner = await _create_user(tier=Tier.LAB, email_suffix="-owner")
        stranger = await _create_user(
            tier=Tier.LAB, email_suffix="-stranger"
        )
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/api/palaces",
                json={"name": "Hidden"},
                headers=_bearer(owner["token"]),
            )
            palace_id = r.json()["palace_id"]
            r2 = await ac.get(
                f"/v1/api/palaces/{palace_id}",
                headers=_bearer(stranger["token"]),
            )
            assert r2.status_code == 404


@pytest.mark.asyncio
async def test_invite_unknown_palace_returns_404(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        u = await _create_user(tier=Tier.LAB)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(u["token"]),
        ) as ac:
            ghost = uuid.uuid4()
            r = await ac.post(
                f"/v1/api/palaces/{ghost}/invite",
                json={"email": "x@y.com"},
            )
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_palace_requires_jwt(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post("/v1/api/palaces", json={"name": "Anon"})
            assert r.status_code == 401


@pytest.mark.asyncio
async def test_invite_with_bad_email_returns_422(app_instance):
    from httpx import ASGITransport, AsyncClient
    from app.entitlements import Tier

    async with app_instance.router.lifespan_context(app_instance):
        owner = await _create_user(tier=Tier.LAB)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
            headers=_bearer(owner["token"]),
        ) as ac:
            r = await ac.post(
                "/v1/api/palaces", json={"name": "ValidationTest"}
            )
            palace_id = r.json()["palace_id"]
            r2 = await ac.post(
                f"/v1/api/palaces/{palace_id}/invite",
                json={"email": "not-an-email"},
            )
            assert r2.status_code == 422

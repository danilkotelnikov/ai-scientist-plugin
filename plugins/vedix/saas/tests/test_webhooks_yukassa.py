"""Webhook tests for ЮKassa (Block 8 Task 5).

* Valid HMAC + ``payment.succeeded`` flips a Free user to Solo.
* Bad signature returns 401.
* Unknown user yields 404.
* ``refund.succeeded`` flips an active subscription to canceled.
* ``payment.canceled`` flips active → past_due.

The other providers (Stripe, CloudPayments, Boosty, crypto) share the
same state-machine path through ``_apply_event``; this file covers the
representative ЮKassa flow plus a stripe-signature shape test.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import pytest


def _yukassa_payload(
    event: str, *, user_email: str, tier: str, payment_id: str | None = None
) -> dict[str, Any]:
    return {
        "event": event,
        "object": {
            "id": payment_id or str(uuid.uuid4()),
            "status": "succeeded" if event == "payment.succeeded" else "canceled",
            "amount": {"value": "1490.00", "currency": "RUB"},
            "metadata": {"user_email": user_email, "tier": tier},
        },
    }


def _yukassa_sign(raw: bytes, secret: str = "yukassa-test-secret") -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


async def _create_user(email: str = "alice@vedix.test"):
    from app.db import SessionLocal
    from app.models.user import User

    async with SessionLocal() as db:
        user = User(email=email)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _current_subscription(user_id):
    from app.db import SessionLocal
    from app.models.subscription import Subscription
    from sqlalchemy import select

    async with SessionLocal() as db:
        return (
            await db.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
        ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_yukassa_payment_succeeded_creates_active_solo_sub(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        user = await _create_user("alice@vedix.test")
        payload = _yukassa_payload(
            "payment.succeeded", user_email="alice@vedix.test", tier="solo"
        )
        raw = json.dumps(payload).encode("utf-8")
        sig = _yukassa_sign(raw)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw,
                headers={
                    "X-Signature": sig,
                    "Content-Type": "application/json",
                },
            )
            assert r.status_code == 200, r.text
            assert r.json()["tier"] == "solo"
            assert r.json()["subscription_status"] == "active"

        sub = await _current_subscription(user.id)
        assert sub is not None
        assert sub.tier == "solo"
        assert sub.status == "active"
        assert sub.payment_provider == "yukassa"
        assert sub.period_end is not None


@pytest.mark.asyncio
async def test_yukassa_bad_signature_returns_401(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        await _create_user("alice@vedix.test")
        payload = _yukassa_payload(
            "payment.succeeded", user_email="alice@vedix.test", tier="solo"
        )
        raw = json.dumps(payload).encode("utf-8")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw,
                headers={"X-Signature": "deadbeef"},
            )
            assert r.status_code == 401
            assert "bad yukassa signature" in r.json()["detail"]


@pytest.mark.asyncio
async def test_yukassa_unknown_user_returns_404(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        payload = _yukassa_payload(
            "payment.succeeded", user_email="ghost@vedix.test", tier="solo"
        )
        raw = json.dumps(payload).encode("utf-8")
        sig = _yukassa_sign(raw)
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw,
                headers={"X-Signature": sig},
            )
            assert r.status_code == 404


@pytest.mark.asyncio
async def test_yukassa_upgrade_then_cancel_flips_to_past_due(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        user = await _create_user("alice@vedix.test")
        # First upgrade to Lab
        upgrade = _yukassa_payload(
            "payment.succeeded", user_email=user.email, tier="lab"
        )
        raw = json.dumps(upgrade).encode("utf-8")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw,
                headers={"X-Signature": _yukassa_sign(raw)},
            )
            assert r.status_code == 200
            sub = await _current_subscription(user.id)
            assert sub.tier == "lab" and sub.status == "active"

            # Then cancel
            cancel = _yukassa_payload(
                "payment.canceled", user_email=user.email, tier="lab"
            )
            raw2 = json.dumps(cancel).encode("utf-8")
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw2,
                headers={"X-Signature": _yukassa_sign(raw2)},
            )
            assert r.status_code == 200
            sub = await _current_subscription(user.id)
            assert sub.status == "past_due"


@pytest.mark.asyncio
async def test_yukassa_refund_flips_to_canceled(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        user = await _create_user("alice@vedix.test")
        # Bootstrap active sub by an upgrade event first.
        upgrade = _yukassa_payload(
            "payment.succeeded", user_email=user.email, tier="solo"
        )
        raw = json.dumps(upgrade).encode("utf-8")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            await ac.post(
                "/v1/webhooks/yukassa",
                content=raw,
                headers={"X-Signature": _yukassa_sign(raw)},
            )
            # Now refund
            refund = _yukassa_payload(
                "refund.succeeded", user_email=user.email, tier="solo"
            )
            raw2 = json.dumps(refund).encode("utf-8")
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw2,
                headers={"X-Signature": _yukassa_sign(raw2)},
            )
            assert r.status_code == 200
            sub = await _current_subscription(user.id)
            assert sub.status == "canceled"


@pytest.mark.asyncio
async def test_yukassa_writes_audit_log(app_instance):
    from app.db import SessionLocal
    from app.models.audit_log import AuditLog
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    async with app_instance.router.lifespan_context(app_instance):
        user = await _create_user("alice@vedix.test")
        payload = _yukassa_payload(
            "payment.succeeded", user_email=user.email, tier="lab"
        )
        raw = json.dumps(payload).encode("utf-8")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw,
                headers={"X-Signature": _yukassa_sign(raw)},
            )
            assert r.status_code == 200

        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(AuditLog).where(AuditLog.user_id == user.id)
                )
            ).scalars().all()
        assert any(r.event == "subscription.activated" for r in rows)


@pytest.mark.asyncio
async def test_yukassa_unknown_tier_rejected(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        await _create_user("alice@vedix.test")
        payload = _yukassa_payload(
            "payment.succeeded", user_email="alice@vedix.test", tier="diamond-tier"
        )
        raw = json.dumps(payload).encode("utf-8")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/yukassa",
                content=raw,
                headers={"X-Signature": _yukassa_sign(raw)},
            )
            assert r.status_code == 400
            assert "diamond-tier" in r.json()["detail"]


# ---- Stripe smoke (covers the shared state-machine path) ----------


def _stripe_sign(raw: bytes, secret: str = "whsec_test") -> str:
    ts = int(time.time())
    signed = f"{ts}.{raw.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


@pytest.mark.asyncio
async def test_stripe_subscription_created_activates(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        user = await _create_user("alice@vedix.test")
        body = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "amount": 1900,
                    "currency": "usd",
                    "status": "active",
                    "metadata": {"user_email": user.email, "tier": "solo"},
                }
            },
        }
        raw = json.dumps(body).encode("utf-8")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/stripe",
                content=raw,
                headers={"Stripe-Signature": _stripe_sign(raw)},
            )
            assert r.status_code == 200, r.text
            sub = await _current_subscription(user.id)
            assert sub.tier == "solo" and sub.status == "active"
            assert sub.payment_provider == "stripe"


@pytest.mark.asyncio
async def test_stripe_bad_signature_returns_401(app_instance):
    from httpx import ASGITransport, AsyncClient

    async with app_instance.router.lifespan_context(app_instance):
        await _create_user("alice@vedix.test")
        body = {"type": "customer.subscription.created", "data": {"object": {}}}
        raw = json.dumps(body).encode("utf-8")
        async with AsyncClient(
            transport=ASGITransport(app=app_instance),
            base_url="http://testserver",
        ) as ac:
            r = await ac.post(
                "/v1/webhooks/stripe",
                content=raw,
                headers={"Stripe-Signature": "t=1234,v1=deadbeef"},
            )
            assert r.status_code == 401

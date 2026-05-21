"""``/v1/webhooks/{provider}`` — payment callbacks.

Each provider's adapter normalizes its event payload into a shared
shape (``provider``, ``event_type`` ∈ {``payment.succeeded``,
``payment.canceled``, ``refund.succeeded``}, ``payment_id``,
``amount``, ``currency``, ``metadata``). This router runs the
verification check, looks up the user by email from metadata, and
walks the subscription state machine:

```
            payment.succeeded
free / past_due  ─────────────►  active(tier)
active  ─────payment.canceled────►  past_due
active  ─────refund.succeeded ───►  canceled
```

Every transition emits an ``AuditLog`` row.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..entitlements import Tier
from ..models.audit_log import AuditLog
from ..models.subscription import Subscription
from ..models.user import User
from ..payments import boosty, cloudpayments, crypto, stripe, yukassa

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


_VALID_EVENTS = {"payment.succeeded", "payment.canceled", "refund.succeeded"}


async def _apply_event(
    db: AsyncSession, event: dict[str, Any]
) -> dict[str, Any]:
    event_type = event.get("event_type")
    metadata = event.get("metadata", {}) or {}
    user_email = metadata.get("user_email")
    tier_str = metadata.get("tier", Tier.SOLO.value)

    if event_type not in _VALID_EVENTS:
        return {"status": "ignored", "reason": f"unhandled event {event_type}"}
    if not user_email:
        raise HTTPException(status_code=400, detail="metadata.user_email required")

    user = (
        await db.execute(select(User).where(User.email == user_email))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"user {user_email} not found")

    sub = (
        await db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
    ).scalar_one_or_none()

    if event_type == "payment.succeeded":
        try:
            Tier(tier_str)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"unknown tier {tier_str!r}"
            ) from exc
        if not sub:
            sub = Subscription(
                user_id=user.id,
                tier=tier_str,
                status="active",
                payment_provider=event["provider"],
                provider_subscription_id=event.get("payment_id"),
                period_end=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(sub)
        else:
            sub.tier = tier_str
            sub.status = "active"
            sub.payment_provider = event["provider"]
            sub.provider_subscription_id = event.get("payment_id")
            sub.period_end = datetime.now(timezone.utc) + timedelta(days=30)
        db.add(
            AuditLog(
                user_id=user.id,
                event="subscription.activated",
                payload={
                    "tier": tier_str,
                    "amount": event.get("amount"),
                    "currency": event.get("currency"),
                    "provider": event["provider"],
                    "payment_id": event.get("payment_id"),
                },
            )
        )
        await db.commit()
        return {"status": "ok", "tier": tier_str, "subscription_status": "active"}

    if event_type == "payment.canceled":
        if sub:
            sub.status = "past_due"
            db.add(
                AuditLog(
                    user_id=user.id,
                    event="subscription.past_due",
                    payload={
                        "provider": event["provider"],
                        "payment_id": event.get("payment_id"),
                    },
                )
            )
            await db.commit()
        return {"status": "ok", "subscription_status": "past_due"}

    if event_type == "refund.succeeded":
        if sub:
            sub.status = "canceled"
            db.add(
                AuditLog(
                    user_id=user.id,
                    event="subscription.canceled",
                    payload={
                        "provider": event["provider"],
                        "payment_id": event.get("payment_id"),
                        "amount": event.get("amount"),
                    },
                )
            )
            await db.commit()
        return {"status": "ok", "subscription_status": "canceled"}

    # Should be unreachable thanks to _VALID_EVENTS gate above.
    return {"status": "ignored"}


def _safe_json(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc


@router.post("/yukassa")
async def yukassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str = Header(default="", alias="X-Signature"),
) -> dict[str, Any]:
    raw = await request.body()
    if not yukassa.verify_signature(raw, x_signature):
        raise HTTPException(status_code=401, detail="bad yukassa signature")
    return await _apply_event(db, yukassa.parse_event(_safe_json(raw)))


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
) -> dict[str, Any]:
    raw = await request.body()
    if not stripe.verify_signature(raw, stripe_signature):
        raise HTTPException(status_code=401, detail="bad stripe signature")
    return await _apply_event(db, stripe.parse_event(_safe_json(raw)))


@router.post("/cloudpayments")
async def cloudpayments_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    content_hmac: str = Header(default="", alias="Content-HMAC"),
) -> dict[str, Any]:
    raw = await request.body()
    if not cloudpayments.verify_signature(raw, content_hmac):
        raise HTTPException(status_code=401, detail="bad cloudpayments signature")
    return await _apply_event(db, cloudpayments.parse_event(_safe_json(raw)))


@router.post("/boosty")
async def boosty_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_boosty_signature: str = Header(default="", alias="X-Boosty-Signature"),
) -> dict[str, Any]:
    raw = await request.body()
    if not boosty.verify_signature(raw, x_boosty_signature):
        raise HTTPException(status_code=401, detail="bad boosty signature")
    return await _apply_event(db, boosty.parse_event(_safe_json(raw)))


@router.post("/crypto")
async def crypto_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str = Header(default="", alias="X-Vedix-Crypto-Signature"),
) -> dict[str, Any]:
    raw = await request.body()
    if not crypto.verify_signature(raw, x_signature):
        raise HTTPException(status_code=401, detail="bad crypto signature")
    return await _apply_event(db, crypto.parse_event(_safe_json(raw)))

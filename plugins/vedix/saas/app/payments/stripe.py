"""Stripe webhook adapter (no external SDK — verify HMAC by hand).

Stripe sends ``Stripe-Signature: t=<unix>,v1=<hex>`` headers. We
recompute ``HMAC-SHA256(secret, f"{t}.{raw_body}")`` and compare to
``v1``. Events of interest:

* ``customer.subscription.created`` → ``payment.succeeded``
* ``customer.subscription.updated``
* ``customer.subscription.deleted`` → ``payment.canceled``
* ``invoice.payment_succeeded``
* ``invoice.payment_failed`` → ``payment.canceled``
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from ..config import settings


_TOLERANCE_SECONDS = 5 * 60


def _parse_signature_header(header: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for chunk in (header or "").split(","):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        pairs[k.strip()] = v.strip()
    return pairs


def verify_signature(raw_body: bytes, signature: str) -> bool:
    parsed = _parse_signature_header(signature)
    t = parsed.get("t")
    v1 = parsed.get("v1")
    if not t or not v1:
        return False
    try:
        ts = int(t)
    except ValueError:
        return False
    # Reject replays from far in the past.
    if abs(time.time() - ts) > _TOLERANCE_SECONDS:
        return False
    signed_payload = f"{t}.{raw_body.decode('utf-8', errors='replace')}".encode("utf-8")
    expected = hmac.new(
        settings.stripe_webhook_secret.encode(), signed_payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, v1)


_STRIPE_TO_INTERNAL: dict[str, str] = {
    "customer.subscription.created": "payment.succeeded",
    "customer.subscription.updated": "payment.succeeded",
    "customer.subscription.deleted": "payment.canceled",
    "invoice.payment_succeeded": "payment.succeeded",
    "invoice.payment_failed": "payment.canceled",
    "charge.refunded": "refund.succeeded",
}


def parse_event(body: dict[str, Any]) -> dict[str, Any]:
    raw_type = body.get("type", "")
    data_obj = (body.get("data", {}) or {}).get("object", {}) or {}
    metadata = data_obj.get("metadata", {}) or {}
    amount_cents = data_obj.get("amount", 0) or data_obj.get("amount_paid", 0) or 0
    return {
        "provider": "stripe",
        "event_type": _STRIPE_TO_INTERNAL.get(raw_type, raw_type),
        "payment_id": data_obj.get("id"),
        "amount": float(amount_cents) / 100.0,
        "currency": (data_obj.get("currency") or "usd").upper(),
        "status": data_obj.get("status"),
        "metadata": metadata,
    }


def verify_and_parse(raw_body: bytes, signature: str) -> dict[str, Any]:
    """Convenience wrapper used by the router."""
    if not verify_signature(raw_body, signature):
        raise ValueError("bad stripe signature")
    import json

    return parse_event(json.loads(raw_body or b"{}"))

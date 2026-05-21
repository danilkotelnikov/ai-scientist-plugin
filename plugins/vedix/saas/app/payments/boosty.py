"""Boosty webhook adapter.

Boosty's webhook protocol is HMAC-SHA256 over the raw body with a
shared secret, delivered in ``X-Boosty-Signature``. Boosty exposes a
"new subscription / cancellation" event payload with ``type`` ∈
{``subscription_created``, ``subscription_canceled``}.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from ..config import settings


_BOOSTY_TO_INTERNAL: dict[str, str] = {
    "subscription_created": "payment.succeeded",
    "subscription_renewed": "payment.succeeded",
    "subscription_canceled": "payment.canceled",
    "payment_refunded": "refund.succeeded",
}


def verify_signature(raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.boosty_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())


def parse_event(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "boosty",
        "event_type": _BOOSTY_TO_INTERNAL.get(body.get("type", ""), body.get("type")),
        "payment_id": body.get("payment_id") or body.get("id"),
        "amount": float(body.get("amount", 0) or 0),
        "currency": body.get("currency", "RUB"),
        "status": body.get("status"),
        "metadata": body.get("metadata", {}) or {},
    }

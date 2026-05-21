"""ЮKassa webhook adapter.

ЮKassa signs payloads with HMAC-SHA256 over the raw body using the
secret configured in the merchant dashboard. Events of interest:

* ``payment.succeeded`` — flip user to the purchased tier.
* ``payment.canceled`` — mark sub past_due.
* ``refund.succeeded`` — mark sub canceled.

The ``metadata`` dict on the payment object carries ``user_email`` and
``tier`` (set by the front-end at payment-creation time).
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from ..config import settings


def verify_signature(raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.yukassa_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())


def parse_event(body: dict[str, Any]) -> dict[str, Any]:
    obj = body.get("object", {}) or {}
    amount = obj.get("amount", {}) or {}
    return {
        "provider": "yukassa",
        "event_type": body.get("event"),
        "payment_id": obj.get("id"),
        "amount": float(amount.get("value", 0) or 0),
        "currency": amount.get("currency", "RUB"),
        "status": obj.get("status"),
        "metadata": obj.get("metadata", {}) or {},
    }

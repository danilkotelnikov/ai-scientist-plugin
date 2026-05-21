"""USDT TRC-20 polling adapter.

Crypto payments don't push webhooks; we poll the configured wallet
periodically (a cron task) and emit a synthetic ``payment.succeeded``
event when a transaction tagged with the user's ``memo`` lands.

The webhook router accepts a self-signed body from the polling job
that uses ``X-Vedix-Crypto-Signature`` with HMAC-SHA256 over the raw
body using ``settings.jwt_secret`` as the key (the polling job lives
inside the same process / cluster).
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from ..config import settings


def verify_signature(raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.jwt_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())


def parse_event(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "crypto",
        "event_type": body.get("event", "payment.succeeded"),
        "payment_id": body.get("tx_hash"),
        "amount": float(body.get("amount_usdt", 0) or 0),
        "currency": "USDT",
        "status": "succeeded",
        "metadata": body.get("metadata", {}) or {},
    }

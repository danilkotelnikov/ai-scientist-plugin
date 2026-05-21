"""CloudPayments webhook adapter.

CloudPayments uses ``Content-HMAC: <base64(hmac_sha256)>`` over the
raw request body, with the API secret as the key. Events of interest:

* ``Pay`` — successful charge → ``payment.succeeded``
* ``Refund`` → ``refund.succeeded``
* ``Cancel`` → ``payment.canceled``
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

from ..config import settings


_CP_TO_INTERNAL: dict[str, str] = {
    "Pay": "payment.succeeded",
    "Refund": "refund.succeeded",
    "Cancel": "payment.canceled",
}


def verify_signature(raw_body: bytes, signature: str) -> bool:
    digest = hmac.new(
        settings.cloudpayments_secret.encode(), raw_body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, (signature or "").strip())


def parse_event(body: dict[str, Any]) -> dict[str, Any]:
    event_raw = body.get("Type") or body.get("event") or ""
    data = body.get("Data") or body
    return {
        "provider": "cloudpayments",
        "event_type": _CP_TO_INTERNAL.get(event_raw, event_raw),
        "payment_id": data.get("TransactionId") or data.get("Id"),
        "amount": float(data.get("Amount", 0) or 0),
        "currency": data.get("Currency", "RUB"),
        "status": data.get("Status"),
        "metadata": data.get("Data", {}) or {},
    }

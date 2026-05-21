"""Payment provider integrations (Block 8 Task 5).

Each module exposes:

* ``verify_signature(raw_body, signature) -> bool`` — HMAC check.
* ``parse_event(body) -> NormalizedEvent`` — extracts our internal
  shape: ``event_type``, ``provider``, ``payment_id``, ``amount``,
  ``status``, ``metadata``.

The router (``routers/webhooks.py``) feeds the normalized events into
the subscription state machine.
"""

from . import boosty, cloudpayments, crypto, stripe, yukassa  # noqa: F401

"""``/v1/api/palaces`` — federated MemPalace REST API (§5.10).

A *shared palace* is a multi-seat MemPalace bundle. Its rows live in
the ``shared_palaces`` table (one row per palace) with an ACL keyed by
email → role (``owner`` | ``admin`` | ``member``). Federated reads /
writes go over the Yjs WebSocket server (``app.workers.yjs_server``)
through the URL returned in :func:`get_palace`.

Endpoints
---------
* ``POST /v1/api/palaces`` — create a new shared palace
  (requires the ``shared_palace`` entitlement; today that maps to the
  Lab and Institution tiers).
* ``POST /v1/api/palaces/{id}/invite`` — owner/admin adds an email to
  the ACL (within ``seats``).
* ``GET /v1/api/palaces/{id}`` — return the palace + the Yjs
  WebSocket URL to subscribe to its CRDT room.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..auth_utils import get_current_user
from ..config import settings
from ..db import get_db
from ..entitlements import compute_entitlements
from ..models.shared_palace import SharedPalace
from ..models.user import User
from .jobs import _user_subscription_tier

router = APIRouter(prefix="/v1/api/palaces", tags=["palaces"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class PalaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class PalaceCreateResponse(BaseModel):
    palace_id: str
    name: str
    seats: int | str  # "unlimited" for Institution tier
    acl: dict[str, str]
    yjs_ws_url: str


class PalaceInviteRequest(BaseModel):
    # We validate the email format with a regex rather than EmailStr so
    # the SaaS stays slim on the `email-validator` dependency. The
    # pattern matches the practical subset of RFC 5322 we actually need.
    email: str = Field(
        ...,
        min_length=3,
        max_length=320,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    )
    role: str = Field("member", pattern="^(owner|admin|member)$")


class PalaceInviteResponse(BaseModel):
    palace_id: str
    acl: dict[str, str]


class PalaceGetResponse(BaseModel):
    palace_id: str
    name: str
    seats: int | str
    acl: dict[str, str]
    yjs_ws_url: str
    owner_user_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _yjs_ws_url_for(palace_id: uuid.UUID) -> str:
    """Compose the Yjs WS URL for a palace's CRDT room.

    Honors ``settings.yjs_ws_base`` so deployments can override the
    public host (e.g. ``wss://collab.vedix.ai``) without code changes.
    """
    base = getattr(settings, "yjs_ws_base", None) or "wss://collab.vedix.ai"
    base = base.rstrip("/")
    return f"{base}/doc/palace_{palace_id}"


def _can_invite(palace: SharedPalace, email: str) -> bool:
    return palace.acl.get(email) in ("owner", "admin")


def _seats_value_for(ent: dict[str, Any]) -> int | str:
    val = ent.get("palace_seats", 1)
    if isinstance(val, int):
        return val
    return str(val)  # "unlimited"


def _seats_limit(palace: SharedPalace) -> int | None:
    """Return the seat cap, or None for unlimited palaces."""
    try:
        return int(palace.seats)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=PalaceCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_palace(
    req: PalaceCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PalaceCreateResponse:
    tier = await _user_subscription_tier(user, db)
    ent = compute_entitlements(tier=tier)
    if not ent.get("shared_palace"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"shared palace requires Lab tier or above "
                f"(you are {tier.value})"
            ),
        )

    seats_val = ent.get("palace_seats", 5)
    # store an int if the tier carries an int quota; for "unlimited"
    # fall back to a generous int marker (we use 2**31-1 so the seat
    # check effectively never trips). The string form is exposed in the
    # response body separately.
    seats_stored = (
        seats_val if isinstance(seats_val, int) else 2**31 - 1
    )

    palace = SharedPalace(
        owner_user_id=user.id,
        name=req.name,
        seats=seats_stored,
        acl={user.email: "owner"},
    )
    db.add(palace)
    await db.commit()
    await db.refresh(palace)
    return PalaceCreateResponse(
        palace_id=str(palace.id),
        name=palace.name,
        seats=_seats_value_for(ent),
        acl=dict(palace.acl),
        yjs_ws_url=_yjs_ws_url_for(palace.id),
    )


@router.post(
    "/{palace_id}/invite",
    response_model=PalaceInviteResponse,
)
async def invite_to_palace(
    palace_id: uuid.UUID,
    req: PalaceInviteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PalaceInviteResponse:
    palace = (
        await db.execute(
            select(SharedPalace).where(SharedPalace.id == palace_id)
        )
    ).scalar_one_or_none()
    if palace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="palace not found"
        )
    if not _can_invite(palace, user.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only owner/admin can invite",
        )
    seat_cap = _seats_limit(palace)
    if seat_cap is not None and len(palace.acl) >= seat_cap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"seats full ({seat_cap})",
        )
    # Cannot demote / overwrite the owner row.
    if palace.acl.get(req.email) == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot overwrite the palace owner role",
        )
    # Mutate then flag the column dirty (SQLAlchemy needs this for
    # in-place JSON mutations).
    palace.acl = {**palace.acl, req.email: req.role}
    flag_modified(palace, "acl")
    await db.commit()
    await db.refresh(palace)
    return PalaceInviteResponse(
        palace_id=str(palace.id), acl=dict(palace.acl)
    )


@router.get(
    "/{palace_id}",
    response_model=PalaceGetResponse,
)
async def get_palace(
    palace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PalaceGetResponse:
    palace = (
        await db.execute(
            select(SharedPalace).where(SharedPalace.id == palace_id)
        )
    ).scalar_one_or_none()
    if palace is None or user.email not in palace.acl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="palace not found"
        )
    # The seat string ("unlimited") is recoverable from the tier — we
    # re-derive it so the response matches the entitlement view.
    tier = await _user_subscription_tier(user, db)
    ent = compute_entitlements(tier=tier)
    return PalaceGetResponse(
        palace_id=str(palace.id),
        name=palace.name,
        seats=_seats_value_for(ent),
        acl=dict(palace.acl),
        yjs_ws_url=_yjs_ws_url_for(palace.id),
        owner_user_id=str(palace.owner_user_id),
    )

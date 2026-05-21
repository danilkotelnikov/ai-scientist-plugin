"""JWT helpers + the ``get_current_user`` FastAPI dependency.

Tokens are HS256 with the secret pulled from ``settings.jwt_secret``;
the payload carries ``sub`` (user UUID), ``email``, ``iat``, ``exp``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_db
from .models.user import User


_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/api/auth/token", auto_error=False)


def issue_jwt(*, user_id: str, email: str, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes or settings.jwt_expires_minutes
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:  # pragma: no cover - exercised via 401 path
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_jwt(token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token missing sub")
    try:
        user_uuid = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid sub") from exc
    user = (
        await db.execute(select(User).where(User.id == user_uuid))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="user inactive")
    return user

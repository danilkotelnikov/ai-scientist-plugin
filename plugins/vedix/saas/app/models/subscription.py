"""``subscriptions`` table — tier + payment-provider state per user."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import GUID, Base
from ..entitlements import Tier


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(
        String(50), default=Tier.FREE.value, nullable=False
    )
    # active | past_due | canceled
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # yukassa | stripe | cloudpayments | boosty | crypto | None (free)
    payment_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

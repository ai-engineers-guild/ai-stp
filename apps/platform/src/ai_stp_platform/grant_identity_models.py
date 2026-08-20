"""Recipient identity persistence for direct access grants."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class OAuthIdentityAlias(Base):
    """Normalized provider username bound to one stable OAuth identity."""

    __tablename__ = "oauth_identity_alias"
    __table_args__ = (
        UniqueConstraint("provider", "normalized_value", name="uq_oauth_identity_alias_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    oauth_identity_id: Mapped[int] = mapped_column(
        ForeignKey("oauth_identity.id", ondelete="CASCADE"), unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    normalized_value: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GrantRecipientReference(Base):
    """The explicit identifier kind/value selected when a grant was created."""

    __tablename__ = "grant_recipient_reference"

    grant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("access_grant.id", ondelete="CASCADE"), primary_key=True
    )
    identifier_kind: Mapped[str] = mapped_column(String(32))
    identifier_value: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

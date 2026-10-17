"""ORM models.

Every table carries ``account_id`` and every query filters on it (see
``test_tenant_isolation.py``).

The fact tables are append-only. Attribution is a *view* over them, computed on
request, so changing the model never rewrites stored data - which is the whole
point of comparing models side by side.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from channeltruth.db import Base


def utcnow() -> datetime:
    """Naive UTC. Timestamps are stored naive and converted at the edges."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(30), default="growth", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Touchpoint(Base):
    """A marketing exposure: an impression or a click, on a channel."""

    __tablename__ = "touchpoints"
    __table_args__ = (
        UniqueConstraint("account_id", "event_uid", name="uq_touch_account_event"),
        Index("ix_touch_account_visitor_time", "account_id", "visitor_id", "occurred_at"),
        Index("ix_touch_account_time", "account_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_uid: Mapped[str] = mapped_column(String(90), nullable=False)
    visitor_id: Mapped[str] = mapped_column(String(90), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="click", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Conversion(Base):
    __tablename__ = "conversions"
    __table_args__ = (
        UniqueConstraint("account_id", "event_uid", name="uq_conversion_account_event"),
        Index("ix_conversion_account_time", "account_id", "occurred_at"),
        Index("ix_conversion_account_visitor", "account_id", "visitor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_uid: Mapped[str] = mapped_column(String(90), nullable=False)
    visitor_id: Mapped[str] = mapped_column(String(90), nullable=False)
    revenue_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ChannelSpend(Base):
    """Daily spend per channel, used to turn attributed revenue into ROAS."""

    __tablename__ = "channel_spend"
    __table_args__ = (
        UniqueConstraint("account_id", "channel", "day", name="uq_spend_account_channel_day"),
        Index("ix_spend_account_day", "account_id", "day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    spend_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["Account", "ChannelSpend", "Conversion", "Touchpoint", "utcnow"]

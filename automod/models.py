"""SQLAlchemy 2 async ORM models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_THRESHOLDS: dict[str, str] = {
    "high": "delete_and_mute",
    "medium": "delete",
    "low": "warn",
}


class Base(DeclarativeBase):
    pass


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(Text, default="")
    owner_user_id: Mapped[int] = mapped_column(BigInteger)
    plan: Mapped[str] = mapped_column(Text, default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rules_text: Mapped[str] = mapped_column(Text, default="")
    action_thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: dict(DEFAULT_THRESHOLDS))
    mute_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str] = mapped_column(Text, default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, default="member")
    warn_count: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    message_text: Mapped[str] = mapped_column(Text, default="")
    verdict_category: Mapped[str] = mapped_column(String(32), default="ok")
    verdict_severity: Mapped[str] = mapped_column(String(16), default="none")
    verdict_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verdict_reason: Mapped[str] = mapped_column(Text, default="")
    action_taken: Mapped[str] = mapped_column(String(32), default="noop")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class StripeEvent(Base):
    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

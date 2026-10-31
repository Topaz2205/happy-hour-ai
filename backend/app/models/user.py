"""
Accounts, workspaces and the AI usage ledger.

TENANCY MODEL
-------------
A `Company` is a workspace: the unit that owns events. A `User` reaches a
workspace only through a `CompanyMembership`. Today every new user gets one
personal workspace (Company.is_personal = True) and is its owner; later, several
users can be given memberships in the same company workspace without any change
to how events are scoped — events belong to the workspace, never to the user.

Catalogue data (cocktails, ingredients, products, suppliers, listings) is global
and has no company_id on purpose.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Always stored lower-cased and stripped, so uniqueness is case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Platform administrator: may edit the GLOBAL catalogue (mappings, prices).
    # Never granted through the API — set it in the database by hand.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # The workspace used when a request does not name one.
    default_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["CompanyMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class CompanyMembership(Base, TimestampMixin):
    __tablename__ = "company_memberships"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_membership"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="owner")  # owner|admin|member

    user: Mapped["User"] = relationship(back_populates="memberships")
    company: Mapped["Company"] = relationship(back_populates="memberships")  # type: ignore


class UsageCounter(Base):
    """
    A durable counter keyed by (scope, period), e.g.
        ("ai:user:<uuid>", "2026-10-23")   – AI requests by one user today
        ("ai:global",      "2026-10-23")   – AI requests by everyone today
        ("login_fail:<email>", "2026-10-23T14") – failed logins this hour

    It lives in PostgreSQL rather than process memory so the limits hold across
    restarts and across several API instances. Increments are a single atomic
    INSERT … ON CONFLICT DO UPDATE … RETURNING.
    """
    __tablename__ = "usage_counters"

    scope: Mapped[str] = mapped_column(String(160), primary_key=True)
    period: Mapped[str] = mapped_column(String(20), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

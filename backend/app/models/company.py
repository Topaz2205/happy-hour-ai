import uuid
from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    """
    A workspace — the tenant that owns events.

    Before multi-user support this table held free-text client company names
    typed into the event form, looked up by name. Those legacy rows have no
    memberships, so nobody can reach them or their events until an operator
    assigns them (see scripts/assign_legacy_events.py). The free-text name now
    lives on Event.client_company_name.
    """
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # True for the workspace created automatically for one user at sign-up.
    is_personal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false")

    memberships: Mapped[list["CompanyMembership"]] = relationship(  # type: ignore
        back_populates="company", cascade="all, delete-orphan")

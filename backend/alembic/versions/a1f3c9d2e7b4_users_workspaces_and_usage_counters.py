"""users, workspaces (company memberships) and usage counters

Revision ID: a1f3c9d2e7b4
Revises: 082021ca8d7f
Create Date: 2026-10-23

PURELY ADDITIVE — safe to run against the live database:
  * creates users, company_memberships, usage_counters
  * adds companies.is_personal       (NOT NULL, default false)
  * adds events.client_company_name  (nullable) and backfills it from the
    legacy free-text company the event pointed at
  * indexes events.company_id

Nothing is dropped, renamed or rewritten. Existing events keep their existing
company_id. Those legacy companies have no members, so their events become
invisible to everyone (the safe default) until an operator assigns them to a
workspace with scripts/assign_legacy_events.py.

downgrade() removes only what upgrade() added.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1f3c9d2e7b4"
down_revision: Union[str, Sequence[str], None] = "082021ca8d7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("is_personal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "company_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_membership"),
    )
    op.create_index("ix_company_memberships_company_id", "company_memberships", ["company_id"])
    op.create_index("ix_company_memberships_user_id", "company_memberships", ["user_id"])

    op.create_table(
        "usage_counters",
        sa.Column("scope", sa.String(length=160), primary_key=True),
        sa.Column("period", sa.String(length=20), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.add_column("events", sa.Column("client_company_name", sa.String(length=255), nullable=True))
    op.create_index("ix_events_company_id", "events", ["company_id"])

    # Keep the client name that legacy events showed via their company row.
    op.execute(
        """
        UPDATE events e
           SET client_company_name = c.name
          FROM companies c
         WHERE e.company_id = c.id
           AND e.client_company_name IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_events_company_id", table_name="events")
    op.drop_column("events", "client_company_name")
    op.drop_table("usage_counters")
    op.drop_index("ix_company_memberships_user_id", table_name="company_memberships")
    op.drop_index("ix_company_memberships_company_id", table_name="company_memberships")
    op.drop_table("company_memberships")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_column("companies", "is_personal")

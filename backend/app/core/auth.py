"""
Authentication and tenant authorization — the one place both are decided.

    get_current_user        Bearer token  → active User            (401 otherwise)
    get_auth_context        User          → AuthContext(workspace) (membership-checked)
    require_event_access    path event_id → EventAccess            (404 unless owned)
    require_admin           AuthContext   → platform admin only    (403 otherwise)
    get_event_for_context   helper for code that has an id but no route

RULES THIS MODULE ENFORCES
--------------------------
* The workspace is resolved on the server from memberships. Nothing the client
  sends — body field, query string, token claim — can choose a workspace the
  user is not a member of. The optional X-Workspace-Id header only *selects*
  among the caller's own memberships, for future multi-company use.
* An event the caller cannot reach is reported as 404 "Event not found",
  exactly like an id that does not exist, so a UUID reveals nothing.
* Every route under /api/events/{event_id}/… must declare
  `Depends(require_event_access)`. tests/test_tenant_isolation.py walks the
  router and fails if one does not.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Company, CompanyMembership, Event, User

_NOT_FOUND = HTTPException(status_code=404, detail="Event not found")
_UNAUTHENTICATED = HTTPException(
    status_code=401, detail="Please sign in to continue.",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class AuthContext:
    user: User
    workspace_id: uuid.UUID
    role: str

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id


@dataclass(frozen=True)
class EventAccess:
    """Proof that the caller's workspace owns this event."""
    event_id: uuid.UUID
    ctx: AuthContext


# ── Workspace provisioning ───────────────────────────────────────────────────

def personal_workspace_name(user: User) -> str:
    label = (user.display_name or "").strip() or user.email.split("@")[0]
    return f"{label[:100]} Workspace"


async def ensure_personal_workspace(db: AsyncSession, user: User) -> CompanyMembership:
    """
    Return the user's default membership, creating a personal workspace and an
    owner membership if they have none. Idempotent.
    """
    if user.default_company_id is not None:
        m = (await db.execute(
            select(CompanyMembership).where(
                CompanyMembership.user_id == user.id,
                CompanyMembership.company_id == user.default_company_id,
            )
        )).scalar_one_or_none()
        if m is not None:
            return m

    # Any existing membership becomes the default before inventing a new one.
    m = (await db.execute(
        select(CompanyMembership)
        .where(CompanyMembership.user_id == user.id)
        .order_by(CompanyMembership.created_at)
        .limit(1)
    )).scalar_one_or_none()
    if m is None:
        company = Company(name=personal_workspace_name(user), is_personal=True, active=True)
        db.add(company)
        await db.flush()
        m = CompanyMembership(company_id=company.id, user_id=user.id, role="owner")
        db.add(m)
        await db.flush()
    user.default_company_id = m.company_id
    await db.flush()
    return m


# ── Dependencies ─────────────────────────────────────────────────────────────

async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHENTICATED
    user_id = decode_access_token(authorization.split(" ", 1)[1].strip())
    if user_id is None:
        raise _UNAUTHENTICATED
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


async def get_auth_context(
    user: User = Depends(get_current_user),
    x_workspace_id: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if x_workspace_id:
        try:
            wid = uuid.UUID(x_workspace_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Workspace not found")
        m = (await db.execute(
            select(CompanyMembership)
            .join(Company, Company.id == CompanyMembership.company_id)
            .where(CompanyMembership.user_id == user.id,
                   CompanyMembership.company_id == wid,
                   Company.active == True)  # noqa: E712
        )).scalar_one_or_none()
        if m is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
    else:
        m = await ensure_personal_workspace(db, user)
    return AuthContext(user=user, workspace_id=m.company_id, role=m.role)


def require_admin(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if not ctx.user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only a platform administrator can change the shared catalogue.",
        )
    return ctx


def _parse_event_id(event_id: str | uuid.UUID) -> uuid.UUID:
    if isinstance(event_id, uuid.UUID):
        return event_id
    try:
        return uuid.UUID(str(event_id))
    except ValueError:
        # Same answer as "not yours": a malformed id reveals nothing either.
        raise _NOT_FOUND


async def get_event_for_context(
    db: AsyncSession, ctx: AuthContext, event_id: str | uuid.UUID, *options,
) -> Event:
    """The event, if it belongs to the caller's workspace; 404 otherwise."""
    uid = _parse_event_id(event_id)
    q = select(Event).where(Event.id == uid, Event.company_id == ctx.workspace_id)
    if options:
        q = q.options(*options)
    event = (await db.execute(q)).scalar_one_or_none()
    if event is None:
        raise _NOT_FOUND
    return event


async def require_event_access(
    event_id: str = Path(...),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> EventAccess:
    """Route dependency: the path's {event_id} must belong to the caller."""
    uid = _parse_event_id(event_id)
    owned = (await db.execute(
        select(Event.id).where(Event.id == uid, Event.company_id == ctx.workspace_id)
    )).scalar_one_or_none()
    if owned is None:
        raise _NOT_FOUND
    return EventAccess(event_id=uid, ctx=ctx)

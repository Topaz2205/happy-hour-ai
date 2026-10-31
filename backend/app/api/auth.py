"""
Sign-up, sign-in and "who am I".

sign up → User → personal workspace (Company, is_personal) → owner membership
        → default workspace → access token
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, ensure_personal_workspace, get_auth_context
from app.core.config import settings
from app.core.security import (
    burn_password_check, create_access_token, hash_password, verify_password,
)
from app.db.session import get_db
from app.models import Company, CompanyMembership, User
from app.services import usage

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BAD_LOGIN = HTTPException(status_code=401, detail="Incorrect email or password.")


def _normalise_email(value: str) -> str:
    value = (value or "").strip().lower()
    if len(value) > 320 or not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address.")
    return value


class SignupRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=120)

    _email = field_validator("email")(lambda cls, v: _normalise_email(v))


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=1, max_length=128)

    _email = field_validator("email")(lambda cls, v: _normalise_email(v))


def client_ip(request: Request) -> str:
    # Set by the hosting edge (Cloudflare in front of Render) and not
    # forwardable by the client through it; fall back to the socket address.
    for header in ("cf-connecting-ip", "true-client-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _session_payload(db: AsyncSession, user: User, workspace_id, role: str) -> dict:
    company = (await db.execute(select(Company).where(Company.id == workspace_id))).scalar_one()
    memberships = (await db.execute(
        select(CompanyMembership, Company)
        .join(Company, Company.id == CompanyMembership.company_id)
        .where(CompanyMembership.user_id == user.id)
        .order_by(CompanyMembership.created_at)
    )).all()
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": bool(user.is_admin),
        },
        "workspace": {
            "id": str(company.id),
            "name": company.name,
            "is_personal": bool(company.is_personal),
            "role": role,
        },
        "workspaces": [
            {"id": str(c.id), "name": c.name, "role": m.role, "is_personal": bool(c.is_personal)}
            for m, c in memberships
        ],
        "ai_usage": await usage.ai_usage(user.id),
    }


async def _token_response(db: AsyncSession, user: User) -> dict:
    membership = await ensure_personal_workspace(db, user)
    token, expires = create_access_token(user.id)
    payload = await _session_payload(db, user, membership.company_id, membership.role)
    return {"access_token": token, "token_type": "bearer",
            "expires_at": expires.isoformat(), **payload}


@router.post("/signup", status_code=201)
async def signup(body: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.ALLOW_SIGNUP:
        raise HTTPException(status_code=403, detail="Sign-ups are currently closed.")

    if await usage.count_signup(client_ip(request)) > settings.SIGNUP_DAILY_LIMIT_PER_IP:
        raise HTTPException(status_code=429,
                            detail="Too many accounts created from this network today.")

    exists = (await db.execute(select(User.id).where(User.email == body.email))).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=(body.display_name or "").strip() or None,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")

    response = await _token_response(db, user)
    await db.commit()
    return response


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    if await usage.login_failures(body.email) >= settings.LOGIN_FAILURES_PER_HOUR:
        raise HTTPException(status_code=429,
                            detail="Too many failed sign-in attempts. Try again in an hour.")

    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None:
        burn_password_check(body.password)
        await usage.record_login_failure(body.email)
        raise _BAD_LOGIN
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        await usage.record_login_failure(body.email)
        raise _BAD_LOGIN

    user.last_login_at = datetime.now(timezone.utc)
    response = await _token_response(db, user)
    await db.commit()
    return response


@router.get("/me")
async def me(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    return await _session_payload(db, ctx.user, ctx.workspace_id, ctx.role)

"""
Durable usage counters and the AI quota built on them.

Every counter lives in the `usage_counters` table and is changed with one atomic
upsert, in its own short transaction. Two consequences:

* the limits hold across restarts and across any number of API instances;
* no row lock is held while a slow LLM call is in flight.

The AI quota is consumed BEFORE the provider is called (so parallel requests
cannot all slip under the limit) and refunded if the provider fails, so a
user is not charged for an answer they never got.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update, func

from app.core.config import settings
from app.db import session as db_session
from app.models import UsageCounter


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _this_hour() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def _insert_for(dialect: str):
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise RuntimeError(f"Unsupported database dialect for counters: {dialect}")
    return insert


async def increment(scope: str, period: str, by: int = 1) -> int:
    """Atomically add `by` and return the new value."""
    async with db_session.AsyncSessionLocal() as s:
        insert = _insert_for(s.bind.dialect.name)
        stmt = insert(UsageCounter).values(scope=scope, period=period, count=by)
        stmt = stmt.on_conflict_do_update(
            index_elements=[UsageCounter.scope, UsageCounter.period],
            set_={"count": UsageCounter.count + by, "updated_at": func.now()},
        ).returning(UsageCounter.count)
        value = (await s.execute(stmt)).scalar_one()
        await s.commit()
        return int(value)


async def decrement(scope: str, period: str) -> None:
    async with db_session.AsyncSessionLocal() as s:
        await s.execute(
            update(UsageCounter)
            .where(UsageCounter.scope == scope, UsageCounter.period == period,
                   UsageCounter.count > 0)
            .values(count=UsageCounter.count - 1)
        )
        await s.commit()


async def current(scope: str, period: str) -> int:
    async with db_session.AsyncSessionLocal() as s:
        value = (await s.execute(
            select(UsageCounter.count)
            .where(UsageCounter.scope == scope, UsageCounter.period == period)
        )).scalar_one_or_none()
        return int(value or 0)


# ── AI quota ─────────────────────────────────────────────────────────────────

@dataclass
class AIQuotaTicket:
    """Proof that one AI request was counted; pass it to refund() on failure."""
    user_scope: str
    period: str
    counted_global: bool
    used: int
    limit: int


def _user_scope(user_id: uuid.UUID) -> str:
    return f"ai:user:{user_id}"


async def consume_ai_request(user_id: uuid.UUID) -> AIQuotaTicket:
    """Count one AI request for this user, or raise 429 if over the limit."""
    period = _today()
    limit = settings.AI_DAILY_REQUEST_LIMIT
    scope = _user_scope(user_id)

    used = await increment(scope, period)
    if used > limit:
        await decrement(scope, period)
        raise HTTPException(
            status_code=429,
            detail=(f"You've used all {limit} AI requests for today in the public beta. "
                    f"The limit resets at midnight UTC. Everything else — menus, "
                    f"quantities, shopping lists, prep — keeps working without AI."),
            headers={"Retry-After": "3600"},
        )

    counted_global = False
    if settings.AI_GLOBAL_DAILY_REQUEST_LIMIT > 0:
        total = await increment("ai:global", period)
        counted_global = True
        if total > settings.AI_GLOBAL_DAILY_REQUEST_LIMIT:
            await decrement("ai:global", period)
            await decrement(scope, period)
            raise HTTPException(
                status_code=429,
                detail=("The public beta has reached today's AI capacity. Please try "
                        "again tomorrow — everything except the AI assistant still works."),
                headers={"Retry-After": "3600"},
            )

    return AIQuotaTicket(scope, period, counted_global, used, limit)


async def refund(ticket: AIQuotaTicket | None) -> None:
    if ticket is None:
        return
    await decrement(ticket.user_scope, ticket.period)
    if ticket.counted_global:
        await decrement("ai:global", ticket.period)


async def ai_usage(user_id: uuid.UUID) -> dict:
    used = await current(_user_scope(user_id), _today())
    limit = settings.AI_DAILY_REQUEST_LIMIT
    return {"used": used, "limit": limit, "remaining": max(0, limit - used),
            "resets": "00:00 UTC"}


# ── Auth throttles ───────────────────────────────────────────────────────────

async def login_failures(email: str) -> int:
    return await current(f"login_fail:{email}", _this_hour())


async def record_login_failure(email: str) -> None:
    await increment(f"login_fail:{email}", _this_hour())


async def count_signup(ip: str) -> int:
    return await increment(f"signup_ip:{ip}", _today())

"""
Shared fixtures for the API-level tests (tenant isolation, auth, AI quota).

DATABASE
--------
Set TEST_DATABASE_URL to a disposable PostgreSQL database to run these against
the production engine, e.g.

    TEST_DATABASE_URL=postgresql+asyncpg://happyhour:happyhour@localhost:5432/happyhour_test pytest -q

Without it they use a throw-away SQLite file, so `pytest -q` works anywhere.
THE TEST DATABASE IS WIPED. Never point TEST_DATABASE_URL at real data.

The pure-engine tests in this folder do not use any of this.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="hh-tests-"))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{_TMP / 'test.db'}"

# Must be set before anything imports app.core.config.
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["AUTH_SECRET_KEY"] = "test-secret-" + "x" * 40
os.environ["ENVIRONMENT"] = "test"
os.environ["AI_DAILY_REQUEST_LIMIT"] = "3"
os.environ["AI_GLOBAL_DAILY_REQUEST_LIMIT"] = "1000"
os.environ["SIGNUP_DAILY_LIMIT_PER_IP"] = "1000"
os.environ["LOGIN_FAILURES_PER_HOUR"] = "5"

import sys  # noqa: E402

sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from sqlalchemy.sql.sqltypes import Date, DateTime  # noqa: E402

import app.db.session as db_session  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401

# NullPool: each test runs in its own event loop, and pooled asyncpg
# connections cannot cross loops.
_engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
db_session.engine = _engine
db_session.AsyncSessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

SEED = json.loads((BACKEND / "scripts" / "public_data" / "public_seed.json").read_text(encoding="utf-8"))
TABLE_ORDER = [
    "ingredients", "cocktails", "products", "suppliers", "cocktail_ingredients",
    "ingredient_aliases", "supplier_products", "ingredient_product_mapping",
]


def _convert(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(column.type, Date) and isinstance(value, str):
        return date.fromisoformat(value)
    if getattr(column.type, "as_uuid", False) and isinstance(value, str):
        return uuid.UUID(value)
    return value


async def _build_database() -> None:
    async with _engine.begin() as conn:
        if _engine.dialect.name == "postgresql":
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        else:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for name in TABLE_ORDER:
            table = Base.metadata.tables[name]
            rows = [
                {k: _convert(table.c[k], v) for k, v in row.items() if k in table.c}
                for row in SEED.get(name, [])
            ]
            if rows:
                await conn.execute(table.insert(), rows)


@pytest.fixture(scope="session", autouse=True)
def database():
    asyncio.run(_build_database())
    yield
    asyncio.run(_engine.dispose())


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    import httpx
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def signup(client, label: str) -> dict:
    """A brand-new user; returns {headers, user, workspace, email, password}."""
    email = f"{label}-{uuid.uuid4().hex[:10]}@example.com"
    password = "correct horse battery"
    r = await client.post("/api/auth/signup", json={
        "email": email, "password": password, "display_name": label,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    return {
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "user": body["user"],
        "workspace": body["workspace"],
        "email": email,
        "password": password,
    }


async def create_costed_event(client, who: dict, name: str, budget: float = 3000) -> str:
    """An event with a two-cocktail menu, calculated — the normal UI flow."""
    r = await client.post("/api/events", headers=who["headers"], json={
        "name": name, "guest_count": 30, "budget": budget, "company_name": "Acme Ltd",
    })
    assert r.status_code == 201, r.text
    event_id = r.json()["id"]

    cocktails = (await client.get("/api/cocktails?page_size=200", headers=who["headers"])).json()["items"]
    by_name = {c["name"]: c["id"] for c in cocktails}
    menu = [
        {"cocktail_id": by_name["Margarita"], "allocation_pct": 0.5},
        {"cocktail_id": by_name["Mojito"], "allocation_pct": 0.5},
    ]
    r = await client.put(f"/api/events/{event_id}/menu", headers=who["headers"], json={"menu": menu})
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/events/{event_id}/calculate", headers=who["headers"])
    assert r.status_code == 200, r.text
    return event_id

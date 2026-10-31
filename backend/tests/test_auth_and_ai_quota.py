"""
Sign-up / sign-in, workspace provisioning, and the database-backed AI quota.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

import app.db.session as db_session
from app.core.config import settings
from app.models import Company, CompanyMembership, User
from conftest import create_costed_event, signup

pytestmark = pytest.mark.asyncio


# ── Authentication ───────────────────────────────────────────────────────────

async def test_api_requires_a_token(client):
    for method, path in [("GET", "/api/events"), ("GET", "/api/cocktails"),
                         ("GET", "/api/suppliers"), ("POST", "/api/events"),
                         ("GET", f"/api/events/{uuid.uuid4()}"), ("POST", "/api/agent/chat"),
                         ("POST", "/api/event-builder/advice"), ("GET", "/api/events/stats")]:
        r = await client.request(method, path, json={})
        assert r.status_code == 401, f"{method} {path} → {r.status_code}"


async def test_bad_or_forged_tokens_are_rejected(client):
    import jwt
    forged = jwt.encode({"sub": str(uuid.uuid4()), "iat": 0, "exp": 9999999999,
                         "iss": "happy-hour-ai", "typ": "access"}, "wrong-key", algorithm="HS256")
    for token in ("garbage", forged):
        r = await client.get("/api/events", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


async def test_health_stays_public(client):
    assert (await client.get("/api/health")).status_code == 200


async def test_signup_creates_user_personal_workspace_and_owner_membership(client):
    who = await signup(client, "dana")
    assert who["workspace"]["is_personal"] is True
    assert who["workspace"]["role"] == "owner"
    assert who["workspace"]["name"] == "dana Workspace"

    async with db_session.AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == who["email"]))).scalar_one()
        assert user.password_hash.startswith("scrypt$") and "correct horse" not in user.password_hash
        assert str(user.default_company_id) == who["workspace"]["id"]
        n = (await db.execute(select(func.count()).select_from(CompanyMembership)
                              .where(CompanyMembership.user_id == user.id))).scalar_one()
        assert n == 1
        company = (await db.execute(select(Company).where(Company.id == user.default_company_id))).scalar_one()
        assert company.is_personal


async def test_login_returns_the_same_workspace(client):
    who = await signup(client, "erin")
    r = await client.post("/api/auth/login", json={"email": who["email"].upper(), "password": who["password"]})
    assert r.status_code == 200, r.text
    assert r.json()["workspace"]["id"] == who["workspace"]["id"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["user"]["email"] == who["email"]


async def test_wrong_password_and_unknown_email_look_the_same(client):
    who = await signup(client, "frank")
    wrong = await client.post("/api/auth/login", json={"email": who["email"], "password": "nope-nope"})
    unknown = await client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_repeated_failed_logins_are_throttled(client):
    who = await signup(client, "gina")
    for _ in range(settings.LOGIN_FAILURES_PER_HOUR):
        await client.post("/api/auth/login", json={"email": who["email"], "password": "bad-guess"})
    r = await client.post("/api/auth/login", json={"email": who["email"], "password": who["password"]})
    assert r.status_code == 429


async def test_duplicate_signup_is_refused(client):
    who = await signup(client, "hank")
    r = await client.post("/api/auth/signup", json={"email": who["email"], "password": "another-password"})
    assert r.status_code == 409


async def test_short_password_and_bad_email_are_refused(client):
    assert (await client.post("/api/auth/signup", json={"email": "x@example.com", "password": "short"})).status_code == 422
    assert (await client.post("/api/auth/signup", json={"email": "not-an-email", "password": "long-enough-1"})).status_code == 422


async def test_users_can_later_share_a_company_workspace(client):
    """Design check: a second membership makes the same events visible to both."""
    owner = await signup(client, "ivy")
    teammate = await signup(client, "jack")
    event_id = await create_costed_event(client, owner, "Team event")

    async with db_session.AsyncSessionLocal() as db:
        db.add(CompanyMembership(company_id=uuid.UUID(owner["workspace"]["id"]),
                                 user_id=uuid.UUID(teammate["user"]["id"]), role="member"))
        await db.commit()

    shared = {**teammate["headers"], "X-Workspace-Id": owner["workspace"]["id"]}
    assert (await client.get(f"/api/events/{event_id}", headers=shared)).status_code == 200
    # Without selecting it, the teammate is still in their own personal workspace.
    assert (await client.get(f"/api/events/{event_id}", headers=teammate["headers"])).status_code == 404


# ── AI quota ─────────────────────────────────────────────────────────────────

class _OK:
    async def chat(self, system, messages, tools):
        from app.services.llm import Reply
        return Reply(text='{"message": "Sounds good", "updates": {}, "recommended_cocktails": ["Margarita"]}',
                     tool_calls=[], stop_reason="end_turn")


class _Down:
    async def chat(self, system, messages, tools):
        from app.services.llm import LLMError
        raise LLMError("provider down", 502)


@pytest.fixture
def llm(monkeypatch):
    from app.api import agent as agent_api, event_builder
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    state = {"provider": _OK()}
    monkeypatch.setattr(agent_api, "build_provider", lambda *a, **k: state["provider"])
    monkeypatch.setattr(event_builder, "OpenAICompatProvider", lambda **k: state["provider"])
    return state


async def _usage(client, who) -> dict:
    return (await client.get("/api/auth/me", headers=who["headers"])).json()["ai_usage"]


async def test_daily_ai_limit_is_enforced_per_user(client, llm):
    limit = settings.AI_DAILY_REQUEST_LIMIT
    a = await signup(client, "kim")
    b = await signup(client, "lee")
    for i in range(limit):
        r = await client.post("/api/event-builder/advice", headers=a["headers"],
                              json={"message": f"30 guests #{i}"})
        assert r.status_code == 200, r.text
        assert r.json()["ai_usage"]["remaining"] == limit - i - 1
    r = await client.post("/api/event-builder/advice", headers=a["headers"], json={"message": "one more"})
    assert r.status_code == 429
    assert (await _usage(client, a))["used"] == limit

    # Someone else's quota is untouched.
    r = await client.post("/api/event-builder/advice", headers=b["headers"], json={"message": "hi"})
    assert r.status_code == 200
    assert (await _usage(client, b))["used"] == 1


async def test_agent_chat_counts_against_the_same_quota(client, llm):
    a = await signup(client, "max")
    event_id = await create_costed_event(client, a, "Quota event")
    for _ in range(settings.AI_DAILY_REQUEST_LIMIT):
        r = await client.post("/api/agent/chat", headers=a["headers"], json={
            "event_id": event_id, "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 200, r.text
    r = await client.post("/api/agent/chat", headers=a["headers"], json={
        "event_id": event_id, "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 429


async def test_failed_ai_calls_are_refunded(client, llm):
    a = await signup(client, "ned")
    event_id = await create_costed_event(client, a, "Refund event")
    llm["provider"] = _Down()
    r = await client.post("/api/agent/chat", headers=a["headers"], json={
        "event_id": event_id, "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 502
    r = await client.post("/api/event-builder/advice", headers=a["headers"], json={"message": "hi"})
    assert r.status_code == 502
    assert (await _usage(client, a))["used"] == 0


async def test_normal_browsing_does_not_consume_ai_quota(client, llm):
    a = await signup(client, "olga")
    event_id = await create_costed_event(client, a, "Browse event")
    for path in ("/api/events", "/api/events/stats", "/api/cocktails", "/api/suppliers",
                 f"/api/events/{event_id}", f"/api/events/{event_id}/shopping-list",
                 f"/api/events/{event_id}/prep-sheet", f"/api/events/{event_id}/messages"):
        assert (await client.get(path, headers=a["headers"])).status_code == 200, path
    await client.post(f"/api/events/{event_id}/calculate", headers=a["headers"])
    assert (await _usage(client, a))["used"] == 0


async def test_global_daily_cap_protects_total_spend(client, llm, monkeypatch):
    from app.services import usage
    monkeypatch.setattr(settings, "AI_GLOBAL_DAILY_REQUEST_LIMIT",
                        await usage.current("ai:global", usage._today()) + 1)
    a = await signup(client, "pia")
    b = await signup(client, "quinn")
    assert (await client.post("/api/event-builder/advice", headers=a["headers"],
                              json={"message": "hi"})).status_code == 200
    r = await client.post("/api/event-builder/advice", headers=b["headers"], json={"message": "hi"})
    assert r.status_code == 429
    assert (await _usage(client, b))["used"] == 0, "a refused request is not charged to the user"


async def test_quota_counter_is_atomic_under_concurrency(client):
    import asyncio
    from app.services import usage
    scope = f"test:{uuid.uuid4()}"
    results = await asyncio.gather(*[usage.increment(scope, "p") for _ in range(25)])
    assert sorted(results) == list(range(1, 26))

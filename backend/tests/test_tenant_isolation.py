"""
Two users, two workspaces, and nothing crosses between them.

These run the real FastAPI app against a real database (see conftest.py) with
the real public catalogue loaded, so a passing run means the HTTP surface —
not a mock of it — keeps each workspace's events private.

Every inaccessible event must answer 404 "Event not found", exactly like an id
that does not exist, so knowing a UUID reveals nothing.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.routing import APIRoute

from app.core.auth import get_auth_context, require_event_access
from conftest import SEED, create_costed_event, signup

pytestmark = pytest.mark.asyncio

NOT_FOUND = {"detail": "Event not found"}


@pytest.fixture
async def two_tenants(client):
    a = await signup(client, "alice")
    b = await signup(client, "bob")
    a["event"] = await create_costed_event(client, a, "Alice offsite")
    b["event"] = await create_costed_event(client, b, "Bob launch party", budget=5000)
    return a, b


# ── Lists and dashboard ──────────────────────────────────────────────────────

async def _list_ids(client, who) -> set[str]:
    r = await client.get("/api/events", headers=who["headers"])
    assert r.status_code == 200, r.text
    return {e["id"] for e in r.json()["items"]}


async def test_each_user_lists_only_their_own_events(client, two_tenants):
    a, b = two_tenants
    a_ids, b_ids = await _list_ids(client, a), await _list_ids(client, b)
    assert a["event"] in a_ids and b["event"] not in a_ids
    assert b["event"] in b_ids and a["event"] not in b_ids


async def test_dashboard_statistics_are_isolated(client, two_tenants):
    a, b = two_tenants
    # A second, uncosted event for Alice only.
    r = await client.post("/api/events", headers=a["headers"],
                          json={"name": "Alice draft", "guest_count": 10, "budget": 1000})
    assert r.status_code == 201

    sa = (await client.get("/api/events/stats", headers=a["headers"])).json()
    sb = (await client.get("/api/events/stats", headers=b["headers"])).json()

    # Each figure matches what that user's own event list implies…
    for who, stats in ((a, sa), (b, sb)):
        items = (await client.get("/api/events", headers=who["headers"])).json()["items"]
        assert stats["events"] == len(items)
        assert stats["costed"] == sum(1 for e in items
                                      if e["estimated_cost"] is not None and not e["cost_is_partial"])
        assert stats["drafts"] == sum(1 for e in items
                                      if e["menu_count"] == 0 or e["estimated_cost"] is None)
    # …and nothing of the other user's leaks in.
    assert sa["events"] == 2 and sa["drafts"] == 1 and sa["avg_budget"] == 2000.0
    assert sb["events"] == 1 and sb["drafts"] == 0 and sb["avg_budget"] == 5000.0


async def test_new_user_starts_with_an_empty_workspace(client, two_tenants):
    c = await signup(client, "carol")
    assert await _list_ids(client, c) == set()
    assert (await client.get("/api/events/stats", headers=c["headers"])).json()["events"] == 0


# ── Direct access by UUID ────────────────────────────────────────────────────

async def test_owner_can_open_their_event(client, two_tenants):
    a, b = two_tenants
    assert (await client.get(f"/api/events/{a['event']}", headers=a["headers"])).status_code == 200
    assert (await client.get(f"/api/events/{b['event']}", headers=b["headers"])).status_code == 200


async def test_get_other_users_event_is_404(client, two_tenants):
    a, b = two_tenants
    r = await client.get(f"/api/events/{b['event']}", headers=a["headers"])
    assert r.status_code == 404 and r.json() == NOT_FOUND
    r = await client.get(f"/api/events/{a['event']}", headers=b["headers"])
    assert r.status_code == 404 and r.json() == NOT_FOUND


async def test_foreign_and_nonexistent_events_are_indistinguishable(client, two_tenants):
    a, b = two_tenants
    foreign = await client.get(f"/api/events/{b['event']}", headers=a["headers"])
    missing = await client.get(f"/api/events/{uuid.uuid4()}", headers=a["headers"])
    malformed = await client.get("/api/events/not-a-uuid", headers=a["headers"])
    assert foreign.status_code == missing.status_code == malformed.status_code == 404
    assert foreign.json() == missing.json() == malformed.json() == NOT_FOUND


async def test_patch_other_users_event_is_404_and_changes_nothing(client, two_tenants):
    a, b = two_tenants
    r = await client.patch(f"/api/events/{b['event']}", headers=a["headers"],
                           json={"name": "hijacked", "guest_count": 999})
    assert r.status_code == 404 and r.json() == NOT_FOUND
    ev = (await client.get(f"/api/events/{b['event']}", headers=b["headers"])).json()
    assert ev["name"] == "Bob launch party"


async def test_delete_other_users_event_is_404_and_event_survives(client, two_tenants):
    a, b = two_tenants
    r = await client.delete(f"/api/events/{b['event']}", headers=a["headers"])
    assert r.status_code == 404 and r.json() == NOT_FOUND
    assert (await client.get(f"/api/events/{b['event']}", headers=b["headers"])).status_code == 200


async def test_owner_can_delete_their_event(client, two_tenants):
    a, _ = two_tenants
    assert (await client.delete(f"/api/events/{a['event']}", headers=a["headers"])).status_code == 200
    assert (await client.get(f"/api/events/{a['event']}", headers=a["headers"])).status_code == 404


async def test_calculate_other_users_event_is_404(client, two_tenants):
    a, b = two_tenants
    r = await client.post(f"/api/events/{b['event']}/calculate", headers=a["headers"])
    assert r.status_code == 404 and r.json() == NOT_FOUND


async def test_shopping_list_and_purchase_plan_of_other_user_are_404(client, two_tenants):
    a, b = two_tenants
    for path in ("shopping-list", "purchase-plan", "cost", "compare-shops"):
        r = await client.get(f"/api/events/{b['event']}/{path}", headers=a["headers"])
        assert r.status_code == 404, path
        assert r.json() == NOT_FOUND, path


async def test_prep_and_equipment_of_other_user_are_404(client, two_tenants):
    a, b = two_tenants
    for path in ("prep-sheet", "equipment", "equipment-shop", "overrides"):
        r = await client.get(f"/api/events/{b['event']}/{path}", headers=a["headers"])
        assert r.status_code == 404 and r.json() == NOT_FOUND, path
    r = await client.put(f"/api/events/{b['event']}/workshop", headers=a["headers"],
                         json={"is_workshop": True, "people_per_station": 1})
    assert r.status_code == 404


async def test_messages_of_other_user_are_404(client, two_tenants):
    a, b = two_tenants
    r = await client.get(f"/api/events/{b['event']}/messages", headers=a["headers"])
    assert r.status_code == 404 and r.json() == NOT_FOUND
    r = await client.delete(f"/api/events/{b['event']}/messages", headers=a["headers"])
    assert r.status_code == 404 and r.json() == NOT_FOUND


# ── Every event route, automatically ─────────────────────────────────────────

def _event_routes():
    from app.main import app
    for route in app.routes:
        if isinstance(route, APIRoute) and "{event_id}" in route.path:
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, route.path


def _sample_ids() -> dict:
    margarita = next(c for c in SEED["cocktails"] if c["name"] == "Margarita")
    line = next(ci for ci in SEED["cocktail_ingredients"] if ci["cocktail_id"] == margarita["id"])
    product = next(m for m in SEED["ingredient_product_mapping"] if m["ingredient_id"] == line["ingredient_id"])
    return {"cocktail_id": margarita["id"], "ingredient_id": line["ingredient_id"],
            "product_id": product["product_id"]}


def _depends_on(dependant, target) -> bool:
    return any(d.call is target or _depends_on(d, target) for d in dependant.dependencies)


def test_every_event_route_declares_the_ownership_check():
    """A new /{event_id} route without require_event_access fails here."""
    from app.main import app
    missing = [
        f"{sorted(r.methods)} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute) and "{event_id}" in r.path
        and not _depends_on(r.dependant, require_event_access)
    ]
    assert missing == []


def test_every_api_route_except_auth_and_health_requires_sign_in():
    from app.main import app
    public = {"/api/health"}
    missing = [
        r.path for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/")
        and not r.path.startswith("/api/auth/") and r.path not in public
        and not _depends_on(r.dependant, get_auth_context)
    ]
    assert missing == []


async def test_every_event_route_hides_other_users_events(client, two_tenants):
    a, b = two_tenants
    ids = _sample_ids()
    bodies = {
        "PUT /api/events/{event_id}/menu": {"menu": [{"cocktail_id": ids["cocktail_id"], "allocation_pct": 1.0}]},
        "PATCH /api/events/{event_id}": {"name": "x"},
        "PUT /api/events/{event_id}/ingredients/{ingredient_id}/product": {"product_id": ids["product_id"]},
        "PUT /api/events/{event_id}/workshop": {"is_workshop": True, "people_per_station": 2},
    }
    checked = 0
    for method, path in _event_routes():
        url = path.format(event_id=b["event"], **ids)
        if "{servings}" in url:
            url = url.format(servings=10)
        if path.endswith("/batch"):
            url += "?servings=10"
        r = await client.request(method, url, headers=a["headers"], json=bodies.get(f"{method} {path}"))
        assert r.status_code == 404, f"{method} {path} → {r.status_code} {r.text[:200]}"
        assert r.json() == NOT_FOUND, f"{method} {path}"
        checked += 1
    assert checked >= 20
    # And Bob's event is untouched.
    assert (await client.get(f"/api/events/{b['event']}", headers=b["headers"])).json()["name"] == "Bob launch party"


# ── Ownership cannot be supplied by the client ──────────────────────────────

async def test_client_supplied_company_id_cannot_override_ownership(client, two_tenants):
    a, b = two_tenants
    r = await client.post("/api/events", headers=a["headers"], json={
        "name": "Sneaky", "guest_count": 5, "budget": 100,
        "company_id": b["workspace"]["id"], "workspace_id": b["workspace"]["id"],
        "company_name": b["workspace"]["name"],
    })
    assert r.status_code == 201
    sneaky = r.json()["id"]
    assert sneaky in await _list_ids(client, a)
    assert sneaky not in await _list_ids(client, b)
    assert (await client.get(f"/api/events/{sneaky}", headers=b["headers"])).status_code == 404


async def test_workspace_header_for_a_foreign_workspace_is_rejected(client, two_tenants):
    a, b = two_tenants
    hdrs = {**a["headers"], "X-Workspace-Id": b["workspace"]["id"]}
    assert (await client.get("/api/events", headers=hdrs)).status_code == 404
    assert (await client.get(f"/api/events/{b['event']}", headers=hdrs)).status_code == 404
    assert (await client.post("/api/events", headers=hdrs,
                              json={"name": "x", "guest_count": 1, "budget": 1})).status_code == 404


async def test_company_name_is_display_text_not_a_tenant(client, two_tenants):
    """Two users typing the same client company never share anything."""
    a, b = two_tenants
    for who in (a, b):
        r = await client.post("/api/events", headers=who["headers"],
                              json={"name": "Same client", "guest_count": 5, "budget": 10,
                                    "company_name": "Wix"})
        assert r.status_code == 201
    assert len([1 for _ in await _list_ids(client, a)]) == 2
    assert len([1 for _ in await _list_ids(client, b)]) == 2


# ── AI agent ─────────────────────────────────────────────────────────────────

class _FakeLLM:
    calls = 0

    async def chat(self, system, messages, tools):
        from app.services.llm import Reply
        _FakeLLM.calls += 1
        return Reply(text="Here is your plan.", tool_calls=[], stop_reason="end_turn")


@pytest.fixture
def fake_llm(monkeypatch):
    from app.api import agent as agent_api
    from app.core.config import settings
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(agent_api, "build_provider", lambda *a, **k: _FakeLLM())
    _FakeLLM.calls = 0
    return _FakeLLM


async def test_agent_cannot_open_other_users_event(client, two_tenants, fake_llm):
    a, b = two_tenants
    r = await client.post("/api/agent/chat", headers=a["headers"], json={
        "event_id": b["event"], "messages": [{"role": "user", "content": "make it cheaper"}],
    })
    assert r.status_code == 404 and r.json() == NOT_FOUND
    assert fake_llm.calls == 0
    me = (await client.get("/api/auth/me", headers=a["headers"])).json()
    assert me["ai_usage"]["used"] == 0, "a refused request must not spend quota"


async def test_agent_works_on_own_event_and_messages_stay_private(client, two_tenants, fake_llm):
    a, b = two_tenants
    r = await client.post("/api/agent/chat", headers=a["headers"], json={
        "event_id": a["event"], "messages": [{"role": "user", "content": "hello"}],
    })
    assert r.status_code == 200, r.text
    msgs = (await client.get(f"/api/events/{a['event']}/messages", headers=a["headers"])).json()["messages"]
    assert sorted(m["role"] for m in msgs) == ["assistant", "user"]
    assert (await client.get(f"/api/events/{a['event']}/messages", headers=b["headers"])).status_code == 404


async def test_agent_tools_refuse_an_event_outside_the_authorised_one(client, two_tenants):
    """Even if code passed the wrong event object, tools do nothing."""
    from sqlalchemy import select
    from app.api.agent import dispatch_tool
    from app.core.auth import AuthContext, EventAccess
    import app.db.session as db_session
    from app.models import Event, User

    a, b = two_tenants
    async with db_session.AsyncSessionLocal() as db:
        ev_b = (await db.execute(select(Event).where(Event.id == uuid.UUID(b["event"])))).scalar_one()
        user_a = (await db.execute(select(User).where(User.id == uuid.UUID(a["user"]["id"])))).scalar_one()
        access_a = EventAccess(uuid.UUID(a["event"]),
                               AuthContext(user_a, uuid.UUID(a["workspace"]["id"]), "owner"))
        out = await dispatch_tool("get_event_details", {}, ev_b, db, access_a)
        assert out == {"error": "Event not found", "tool": "get_event_details"}
        out = await dispatch_tool("get_event_details", {}, ev_b, db, None)
        assert out["error"] == "Event not found"


# ── Shared catalogue ─────────────────────────────────────────────────────────

async def test_global_catalogue_is_shared_by_everyone(client, two_tenants):
    a, b = two_tenants
    for who in (a, b):
        cocktails = await client.get("/api/cocktails?page_size=200", headers=who["headers"])
        assert cocktails.status_code == 200 and cocktails.json()["total"] == 30
        one = cocktails.json()["items"][0]["id"]
        assert (await client.get(f"/api/cocktails/{one}", headers=who["headers"])).status_code == 200
        assert (await client.get("/api/cocktails/themes", headers=who["headers"])).status_code == 200
        suppliers = await client.get("/api/suppliers", headers=who["headers"])
        assert suppliers.status_code == 200 and len(suppliers.json()["suppliers"]) > 0
        for path in ("/api/mappings/coverage", "/api/mappings/mapped", "/api/mappings/unmapped"):
            assert (await client.get(path, headers=who["headers"])).status_code == 200, path


async def test_only_admins_can_change_the_shared_catalogue(client, two_tenants):
    a, _ = two_tenants
    ids = _sample_ids()
    r = await client.post("/api/mappings", headers=a["headers"],
                          json={"ingredient_id": ids["ingredient_id"], "product_id": ids["product_id"]})
    assert r.status_code == 403
    r = await client.delete(f"/api/mappings/{uuid.uuid4()}", headers=a["headers"])
    assert r.status_code == 403
    r = await client.post("/api/mappings/price", headers=a["headers"], json={})
    assert r.status_code == 403


# ── The whole working product, inside one workspace ──────────────────────────

async def test_owner_keeps_every_existing_feature(client, two_tenants):
    a, _ = two_tenants
    e, h = a["event"], a["headers"]
    ids = _sample_ids()

    ev = (await client.get(f"/api/events/{e}", headers=h)).json()
    assert ev["guest_count"] == 30

    calc = (await client.post(f"/api/events/{e}/calculate", headers=h)).json()
    assert calc  # deterministic engine ran

    for path in ("shopping-list", "purchase-plan", "cost", "prep-sheet", "compare-shops",
                 "equipment", "equipment-shop", "overrides", "messages"):
        r = await client.get(f"/api/events/{e}/{path}", headers=h)
        assert r.status_code == 200, f"{path}: {r.text[:300]}"

    cost = (await client.get(f"/api/events/{e}/cost", headers=h)).json()
    assert "budget" in str(cost)

    r = await client.get(f"/api/events/{e}/ingredients/{ids['ingredient_id']}/alternatives", headers=h)
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/events/{e}/cocktails/{ids['cocktail_id']}/batch?servings=20", headers=h)
    assert r.status_code == 200, r.text
    r = await client.put(f"/api/events/{e}/workshop", headers=h, json={"is_workshop": True, "people_per_station": 2})
    assert r.status_code == 200, r.text
    r = await client.patch(f"/api/events/{e}", headers=h, json={"guest_count": 40})
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/events/{e}", headers=h)).json()["guest_count"] == 40


async def test_one_shot_plan_lands_in_the_callers_workspace(client, two_tenants):
    a, b = two_tenants
    r = await client.post("/api/plan", headers=a["headers"],
                          json={"description": "40 people, margaritas, 4000 shekels"})
    assert r.status_code == 201, r.text
    created = r.json().get("event_id") or r.json().get("id") or r.json().get("event", {}).get("id")
    assert created in await _list_ids(client, a)
    assert created not in await _list_ids(client, b)

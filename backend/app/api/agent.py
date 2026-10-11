"""
AI Agent endpoint — Claude + tool calling.

Architecture rule: Claude NEVER performs math.
All quantities, costs, and allocations come from the deterministic engine.
Claude's job: understand intent, pick cocktails, set allocations, interpret results.
"""
import json
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.services.llm import (
    build_provider, describe_config, LLMError, Message, ToolCall,
)
from app.db.session import get_db
from app.models import (
    Cocktail, CocktailIngredient, Ingredient, Event, EventMenuItem, Product,
    EventMessage,
)
from app.api.events import _build_engine_inputs, _format_calc_result
from app.engine.calculator import calculate_event, MenuAllocation

router = APIRouter()


# ── Agent request/response ────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AgentChatRequest(BaseModel):
    event_id: str
    messages: list[ChatMessage]
    # Which workspace tab the person is looking at. "Make it cheaper" means
    # something different from Shopping than it does from Menu, and the tab is
    # the cheapest possible way to carry that — a single word, rather than the
    # frontend shipping data the backend can already read.
    current_tab: str | None = None


# ── Tool definitions (Claude function calling) ────────────────────────────────

TOOLS = [
    {
        "name": "search_cocktails",
        "description": (
            "Search the cocktail database for cocktails matching criteria. "
            "Returns cocktail names and IDs for use in propose_menu."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {
                    "type": "string",
                    "description": "Filter by cocktail theme, e.g. 'classic'",
                },
                "alcoholic": {
                    "type": "boolean",
                    "description": "Filter for alcoholic (true) or non-alcoholic (false)",
                },
                "search": {
                    "type": "string",
                    "description": "Partial name search",
                },
            },
        },
    },
    {
        "name": "get_cocktail_details",
        "description": (
            "Get full recipe details for one or more cocktails including ingredients, "
            "technique, glass, and garnish."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cocktail_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of cocktail UUIDs to fetch details for",
                },
            },
            "required": ["cocktail_ids"],
        },
    },
    {
        "name": "get_event_details",
        "description": "Get the current event parameters (guests, budget, theme, etc.)",
        # no arguments: the event is bound by the request
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_menu",
        "description": (
            "Propose a cocktail menu for the event. Provide cocktail IDs and "
            "allocation percentages (must sum to 1.0). "
            "After proposing, the engine will calculate quantities and costs. "
            "IMPORTANT: You must not perform any math yourself — the engine does all calculations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "menu": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cocktail_id": {"type": "string"},
                            "allocation_pct": {
                                "type": "number",
                                "description": "Share of total drinks (0.0 to 1.0). All must sum to 1.0.",
                            },
                            "rationale": {
                                "type": "string",
                                "description": "Why this cocktail is included in the menu.",
                            },
                        },
                        "required": ["cocktail_id", "allocation_pct", "rationale"],
                    },
                },
            },
            "required": ["menu"],
        },
    },
    {
        "name": "calculate_event_cost",
        "description": (
            "Run the deterministic calculation engine on the current or proposed menu. "
            "Returns ingredient requirements, package counts, costs, and budget status. "
            "ALL math is done by the Python engine — do NOT perform calculations yourself."
        ),
        # no arguments: the event is bound by the request
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_shopping_list",
        "description": (
            "Get the current shopping list (purchase items with quantities and prices) "
            "for the event after calculation."
        ),
        # no arguments: the event is bound by the request
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_spirit_options",
        "description": (
            "For an event that has already been costed, list every spirit that has "
            "cheaper or dearer alternatives available, with the exact effect on the "
            "event total for each one. USE THIS FIRST whenever someone asks to make "
            "an event cheaper or more premium. Changing the bottle keeps the menu the "
            "person asked for; dropping or swapping a cocktail does not. Every figure "
            "is computed by the engine — never estimate a saving yourself."
        ),
        # no arguments: the event is bound by the request
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "apply_product_alternative",
        "description": (
            "Switch one ingredient to a different product FOR THIS EVENT ONLY and "
            "recalculate. Use after list_spirit_options has shown the real cost "
            "impact. The house recommendation for every other event is untouched. "
            "Never call this with a product you have not seen in list_spirit_options "
            "output — the saving must be a number the engine produced, never one "
            "you worked out."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredient_id": {"type": "string"},
                "product_id": {"type": "string"},
                "reason": {
                    "type": "string",
                    "description": "Why, in one short sentence, for the person's record.",
                },
            },
            "required": ["ingredient_id", "product_id"],
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

async def tool_search_cocktails(inputs: dict, db: AsyncSession) -> dict:
    q = select(Cocktail).where(Cocktail.active == True)
    if "theme" in inputs and inputs["theme"]:
        q = q.where(Cocktail.theme == inputs["theme"])
    if "alcoholic" in inputs and inputs["alcoholic"] is not None:
        q = q.where(Cocktail.alcoholic == inputs["alcoholic"])
    if "search" in inputs and inputs["search"]:
        q = q.where(Cocktail.name.ilike(f"%{inputs['search']}%"))
    q = q.order_by(Cocktail.name)

    result = await db.execute(q)
    cocktails = result.scalars().all()

    # Deliberately narrow. This is a browse result, not a record: the model
    # needs an id to propose with, a name to reason about, and enough to judge
    # fit. Glass, garnish and technique come from get_cocktail_details when a
    # shortlist exists — returning them for all 30 cost ~1,750 tokens a call and
    # was the single largest item in a request that Groq's free tier rejected
    # outright at 8,888 tokens against an 8,000 limit.
    return {
        "count": len(cocktails),
        "note": "Names and ids only. Call get_cocktail_details for recipes.",
        "cocktails": [
            {
                "id": str(c.id),
                "name": c.name,
                "alcoholic": c.alcoholic,
                "complexity": c.complexity,
            }
            for c in cocktails
        ],
    }


async def tool_get_cocktail_details(inputs: dict, db: AsyncSession) -> dict:
    cocktail_ids = [uuid.UUID(cid) for cid in inputs["cocktail_ids"]]
    result = await db.execute(
        select(Cocktail)
        .options(
            selectinload(Cocktail.ingredients).selectinload(CocktailIngredient.ingredient)
        )
        .where(Cocktail.id.in_(cocktail_ids))
    )
    cocktails = result.scalars().all()

    details = []
    for c in cocktails:
        ings = [
            {
                "name": ci.ingredient.canonical_name,
                "amount": float(ci.amount) if ci.amount else "to taste",
                "unit": ci.unit,
                "category": ci.ingredient.category,
                "alcoholic": ci.ingredient.alcoholic,
            }
            for ci in sorted(c.ingredients, key=lambda x: x.sort_order or 0)
        ]
        details.append({
            "id": str(c.id),
            "name": c.name,
            "theme": c.theme,
            "technique": c.technique,
            "glass_type": c.glass_type,
            "garnish": c.garnish,
            "ingredients": ings,
            "non_alc_variant": c.non_alc_variant,
            "comments": c.comments,
        })

    return {"cocktails": details}


async def tool_get_event_details(inputs: dict, event: Event, db: AsyncSession) -> dict:
    """
    The event the person is looking at — not one they had to name.

    This used to read inputs["event_id"], which the model had no way of knowing:
    it is a UUID that appears nowhere in the conversation. The model did the only
    sensible thing and asked the person to paste it, which made the panel look
    broken while it was in fact working exactly as written. The event is bound to
    the request; asking for it again was the bug.
    """
    uid = event.id
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.menu_items).selectinload(EventMenuItem.cocktail))
        .where(Event.id == uid)
    )
    event = result.scalar_one_or_none()
    if event is None:
        return {"error": "Event not found"}

    return {
        "id": str(event.id),
        "name": event.name,
        "guest_count": event.guest_count,
        # Both nullable, and both reached the model as a crash before this:
        # asking the agent anything about an event with no budget took the
        # whole panel down. A missing budget is reported as missing so the
        # model says so rather than inventing a figure.
        "budget_ils": float(event.budget) if event.budget is not None else None,
        "budget_per_guest_ils": (
            round(float(event.budget) / event.guest_count, 2)
            if event.budget is not None and event.guest_count else None
        ),
        "budget_note": (
            None if event.budget is not None
            else "No budget set. Report costs without an over/under verdict, "
                 "and never invent a target."
        ),
        "duration_hours": float(event.duration_hours),
        "drinks_per_guest": float(event.expected_drinks_per_guest),
        "non_alcoholic_pct": float(event.non_alcoholic_pct),
        "waste_buffer_pct": float(event.waste_buffer_pct),
        "theme": event.theme,
        "ai_request": event.ai_request,
        "status": event.status,
        "current_menu": [
            {
                "cocktail_id": str(mi.cocktail_id),
                "cocktail_name": mi.cocktail.name if mi.cocktail else None,
                "allocation_pct": float(mi.allocation_pct),
            }
            for mi in event.menu_items
        ],
    }


async def tool_propose_menu(inputs: dict, event: Event, db: AsyncSession) -> dict:
    menu_items = inputs["menu"]
    total_alloc = sum(item["allocation_pct"] for item in menu_items)

    if abs(total_alloc - 1.0) > 0.02:
        return {
            "error": f"Allocations sum to {total_alloc:.3f}, not 1.0. Please adjust.",
            "total_allocation": total_alloc,
        }

    # Validate IDs
    cocktail_ids = [uuid.UUID(item["cocktail_id"]) for item in menu_items]
    result = await db.execute(
        select(Cocktail.id).where(Cocktail.id.in_(cocktail_ids))
    )
    found = {str(r[0]) for r in result.all()}
    missing = [item["cocktail_id"] for item in menu_items if item["cocktail_id"] not in found]
    if missing:
        return {"error": f"Cocktail IDs not found: {missing}"}

    # Clear and set new menu
    old_items_result = await db.execute(
        select(EventMenuItem).where(EventMenuItem.event_id == event.id)
    )
    for mi in old_items_result.scalars().all():
        await db.delete(mi)

    for item in menu_items:
        db.add(EventMenuItem(
            event_id=event.id,
            cocktail_id=uuid.UUID(item["cocktail_id"]),
            allocation_pct=item["allocation_pct"],
            ai_rationale=item.get("rationale", ""),
        ))

    event.status = "MENU_PROPOSED"
    await db.flush()

    return {
        "status": "Menu set successfully",
        "menu_count": len(menu_items),
        "total_allocation": total_alloc,
        "note": "Call calculate_event_cost to get quantities and prices.",
    }


async def tool_calculate_event(inputs: dict, event: Event, db: AsyncSession) -> dict:
    # Reload event with menu items
    result = await db.execute(
        select(Event)
        .options(
            selectinload(Event.menu_items).selectinload(EventMenuItem.cocktail),
            selectinload(Event.menu_items),
        )
        .where(Event.id == event.id)
    )
    event_fresh = result.scalar_one_or_none()

    if not event_fresh.menu_items:
        return {"error": "No menu set. Use propose_menu first."}

    menu_allocs, recipes, ingredient_products = await _build_engine_inputs(db, event_fresh)

    calc = calculate_event(
        guests=event_fresh.guest_count,
        drinks_per_guest=float(event_fresh.expected_drinks_per_guest),
        non_alcoholic_pct=float(event_fresh.non_alcoholic_pct),
        waste_buffer_pct=float(event_fresh.waste_buffer_pct),
        menu=menu_allocs,
        recipes=recipes,
        ingredient_products=ingredient_products,
        budget=float(event_fresh.budget) if event_fresh.budget is not None else None,
    )

    # Build a concise summary for the AI (full details are in the DB)
    summary = {
        "total_drinks": calc.total_drinks,
        "alcoholic_drinks": calc.alcoholic_drinks,
        "non_alcoholic_drinks": calc.non_alcoholic_drinks,
        "total_cost_ils": calc.total_cost,
        "cost_per_guest_ils": round(calc.cost_per_guest, 2) if calc.cost_per_guest else None,
        "budget_ils": calc.budget,
        "budget_variance_ils": round(calc.budget_variance, 2) if calc.budget_variance is not None else None,
        "budget_status": calc.budget_status.value if calc.budget_status else None,
        "has_missing_prices": calc.has_missing_prices,
        "has_missing_mappings": calc.has_missing_mappings,
        "cost_by_category": calc.cost_by_category,
        "warnings": calc.warnings[:5] if calc.warnings else [],
        "top_ingredients_by_cost": sorted(
            [
                {"name": item.canonical_name, "total_price": item.total_price, "packages": item.packages_required}
                for item in calc.purchase_items if item.total_price is not None
            ],
            key=lambda x: x["total_price"],
            reverse=True,
        )[:8],
    }

    # Save to DB (persist full results)
    from datetime import datetime, timezone
    from app.models import EventRequirement, EventPurchaseItem

    now = datetime.now(timezone.utc)
    old_req = await db.execute(select(EventRequirement).where(EventRequirement.event_id == event.id))
    for r in old_req.scalars().all():
        await db.delete(r)
    old_pi = await db.execute(select(EventPurchaseItem).where(EventPurchaseItem.event_id == event.id))
    for pi in old_pi.scalars().all():
        await db.delete(pi)

    for req in calc.ingredient_requirements:
        db.add(EventRequirement(
            event_id=event.id,
            ingredient_id=uuid.UUID(req.ingredient_id),
            required_amount=req.required_amount,
            unit=req.unit,
            calculated_at=now,
        ))
    for item in calc.purchase_items:
        db.add(EventPurchaseItem(
            event_id=event.id,
            ingredient_id=uuid.UUID(item.ingredient_id),
            product_id=uuid.UUID(item.product_id) if item.product_id else None,
            required_amount=item.required_amount,
            required_unit=item.unit,
            packages_required=item.packages_required,
            package_size=item.package_size,
            package_unit=item.package_unit,
            unit_price=item.unit_price,
            total_price=item.total_price,
            status=item.status.value,
            supplier_id=uuid.UUID(item.supplier_id) if item.supplier_id else None,
            product_url=item.product_url,
        ))

    event.status = "COSTED"
    await db.flush()

    return summary


async def tool_get_shopping_list(inputs: dict, event: Event, db: AsyncSession) -> dict:
    from app.models import EventPurchaseItem, Ingredient, Product, Supplier
    uid = event.id

    result = await db.execute(
        select(EventPurchaseItem)
        .options(
            selectinload(EventPurchaseItem.ingredient),
            selectinload(EventPurchaseItem.product),
        )
        .where(EventPurchaseItem.event_id == uid)
        .order_by(EventPurchaseItem.status)
    )
    items = result.scalars().all()
    if not items:
        return {"error": "No shopping list found. Run calculate_event_cost first."}

    return {
        "items": [
            {
                "ingredient": item.ingredient.canonical_name if item.ingredient else "UNKNOWN",
                "product": item.product.name if item.product else "PRODUCT_MAPPING_REQUIRED",
                "packages": item.packages_required,
                "package_size": float(item.package_size) if item.package_size else None,
                "package_unit": item.package_unit,
                "price_per_package": float(item.unit_price) if item.unit_price else None,
                "total_price": float(item.total_price) if item.total_price else None,
                "status": item.status,
            }
            for item in items
        ],
        "total_known_cost": sum(float(i.total_price) for i in items if i.total_price is not None),
    }


async def tool_list_spirit_options(inputs: dict, event: Event, db: AsyncSession) -> dict:
    """
    What each alternative bottle would do to this event's total.

    The saving is not price_difference × volume. Drink is bought in whole
    bottles, so a cheaper bottle in a different size can cost MORE once the
    ceiling is applied — 3 × 700ml beats 2 × 1000ml on shelf price and loses on
    total. The only honest way to answer is to re-run the package arithmetic for
    each option, which is what happens below.
    """
    from app.models.product import IngredientProductMapping
    from app.models.supplier import SupplierProduct
    from app.models.event import EventPurchaseItem
    import math

    items = (await db.execute(
        select(EventPurchaseItem).where(EventPurchaseItem.event_id == event.id)
    )).scalars().all()
    if not items:
        return {"error": "This event has not been costed yet. Run calculate_event_cost first."}

    slots = []
    for item in items:
        alts = (await db.execute(
            select(Product, SupplierProduct)
            .join(IngredientProductMapping, IngredientProductMapping.product_id == Product.id)
            .join(SupplierProduct, SupplierProduct.product_id == Product.id)
            .where(IngredientProductMapping.ingredient_id == item.ingredient_id,
                   IngredientProductMapping.substitution_allowed == True,  # noqa: E712
                   SupplierProduct.price_after_vat.isnot(None),
                   SupplierProduct.available == True)  # noqa: E712
        )).all()
        if not alts:
            continue

        ing = (await db.execute(
            select(Ingredient).where(Ingredient.id == item.ingredient_id)
        )).scalar_one_or_none()

        need = float(item.required_amount)
        current_total = float(item.total_price) if item.total_price is not None else None

        # One row per (product, supplier listing) comes back from the join, so the
        # same bottle appears once per shop that stocks it — and twice more if an
        # earlier import created a second Product row under the same name. Showing
        # a customer "Gordon's" four times, at two different prices, reads as a
        # bug even though every row is real. Collapse to one entry per bottle at
        # the lowest price actually available, which is what they would pay.
        best: dict[str, tuple] = {}
        for prod, listing in alts:
            size = float(prod.package_size) if prod.package_size else None
            price = float(listing.price_after_vat)
            if not size or size <= 0:
                continue          # cannot be costed; never shown at a guessed price
            key = f"{(prod.brand or prod.name).strip().lower()}|{size:g}"
            if key not in best or price < best[key][1]:
                best[key] = (prod, price, size)

        options = []
        for prod, price, size in best.values():
            packs = math.ceil(need / size)
            total = round(packs * price, 2)
            options.append({
                "product_id": str(prod.id),
                "product": prod.brand or prod.name,
                "hebrew_name": prod.name,
                "bottle_size_ml": size,
                "bottle_price": price,
                "bottles_needed": packs,
                "event_total_for_this_ingredient": total,
                "change_vs_current": (round(total - current_total, 2)
                                      if current_total is not None else None),
            })
        if not options:
            continue
        options.sort(key=lambda o: o["event_total_for_this_ingredient"])
        slots.append({
            # apply_product_alternative needs this. Without it the agent can
            # describe a saving and then has no way to act on it.
            "ingredient_id": str(item.ingredient_id),
            "ingredient": ing.canonical_name if ing else str(item.ingredient_id),
            "recipe_calls_for": item.product_id and str(item.product_id),
            "currently_costs": current_total,
            "amount_needed_ml": round(need, 1),
            "options": options,
        })

    return {
        "event_id": str(event.id),
        "slots_with_alternatives": len(slots),
        "slots": slots,
        "note": ("Bottle prices differ by size, so the cheapest bottle is not always "
                 "the cheapest outcome — compare event_total_for_this_ingredient, "
                 "not bottle_price. Present the choice; do not apply it silently."),
    }


async def tool_apply_product_alternative(inputs: dict, event: Event, db: AsyncSession) -> dict:
    """
    Apply a product choice to this event, then recalculate.

    Reuses the same API path a person clicking "use this one" would take, so
    there is exactly one code path that can change what an event buys — and
    therefore exactly one place where the guard lives that stops gin being put
    in the tequila slot.
    """
    from app.api.events import set_event_product, ProductOverrideIn

    result = await set_event_product(
        str(event.id), inputs["ingredient_id"],
        ProductOverrideIn(product_id=inputs["product_id"],
                          reason=inputs.get("reason") or "Applied by the agent"),
        db,
    )
    return {
        "applied": True,
        "ingredient": result.get("ingredient_name"),
        "now_costs": result.get("current_total"),
        "note": ("The event has been recalculated. Report the new figure from this "
                 "result — do not restate a saving you calculated yourself."),
    }


# ── Tool dispatcher ───────────────────────────────────────────────────────────

async def dispatch_tool(
    tool_name: str,
    tool_input: dict,
    event: Event,
    db: AsyncSession,
) -> Any:
    """
    Run one tool and always return something the model can read.

    A tool that raises must not become a 500. Models get arguments wrong —
    omitting a required field, passing a string where an ID belongs — and the
    smaller models more often. Handing the failure back as a tool result lets
    the model see what it did and correct itself on the next turn, which is the
    whole point of the loop. Raising instead ends the conversation with a
    traceback and tells the person nothing.

    The rollback matters: a half-applied tool would otherwise poison every
    later query on this session with a broken transaction.
    """
    try:
        return await _dispatch(tool_name, tool_input, event, db)
    except Exception as e:
        await db.rollback()
        return {
            "error": f"{type(e).__name__}: {e}",
            "tool": tool_name,
            "arguments_received": tool_input,
            "hint": "Check the tool's required arguments and call it again.",
        }


async def _dispatch(
    tool_name: str,
    tool_input: dict,
    event: Event,
    db: AsyncSession,
) -> Any:
    if tool_name == "search_cocktails":
        return await tool_search_cocktails(tool_input, db)
    elif tool_name == "get_cocktail_details":
        return await tool_get_cocktail_details(tool_input, db)
    elif tool_name == "get_event_details":
        return await tool_get_event_details(tool_input, event, db)
    elif tool_name == "propose_menu":
        return await tool_propose_menu(tool_input, event, db)
    elif tool_name == "calculate_event_cost":
        return await tool_calculate_event(tool_input, event, db)
    elif tool_name == "apply_product_alternative":
        return await tool_apply_product_alternative(tool_input, event, db)
    elif tool_name == "list_spirit_options":
        return await tool_list_spirit_options(tool_input, event, db)
    elif tool_name == "get_shopping_list":
        return await tool_get_shopping_list(tool_input, event, db)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Happy Hour AI — cocktail event planner for Israeli HR teams, office managers, People Ops.
Tone: professional, warm, knows cocktails. Israeli context (₪, Hebrew supplier names).

Tools (none need an event id — you are already working on one specific event):
1. search_cocktails — the active catalogue
2. get_cocktail_details — full recipe
3. get_event_details — this event's parameters and current menu
4. propose_menu — set this event's menu
5. calculate_event_cost — engine computes quantities, packages, costs
6. get_shopping_list — this event's list in ₪
7. list_spirit_options — cheaper/dearer bottles for the SAME menu

When asked to make it cheaper or more premium, call list_spirit_options FIRST.
Changing the bottle keeps the menu the person asked for; dropping a cocktail
does not, and is almost never what they meant.

CRITICAL RULES — NEVER VIOLATE:
- NEVER perform arithmetic yourself. All quantities, costs, package counts, totals come from the calculation engine.
- NEVER invent prices, package sizes, product details. Missing data → flag explicitly.
- PRICE_MISSING or PRODUCT_MAPPING_REQUIRED in results → report honestly.
- ALWAYS call calculate_event_cost after proposing a menu, to get real numbers.
- Budget in Israeli Shekels (₪). Never guess or estimate costs.

Workflow:
1. Get event details — guests, budget, theme, preferences
2. Search cocktails matching theme
3. Review details, pick
4. propose_menu, sensible allocations (spirits-forward classics vs lighter florals)
5. calculate_event_cost — real cost from engine
6. Over budget → adjust menu, recalculate
7. Present final shopping list

Menu balance: mix of styles (shaken, stirred, built); non-alcoholic guests (event settings control %); seasonal fit; bar-team complexity; guest count and consumption.

Always transparent about data gaps. Never fabricate.
"""


async def build_system_prompt(event: Event, db: AsyncSession,
                              current_tab: str | None = None) -> str:
    """
    The base prompt plus the event actually on screen.

    Without this the model knows a great deal about cocktails and nothing about
    which event it is looking at, so it asks the person for a UUID — a string
    that appears nowhere they can see. Binding the event in the endpoint and
    then not telling the model about it was the whole bug.

    The catalogue size is counted here rather than written into the prompt. It
    was previously based on a fixed recipe count; the public dataset has since been
    retired, so the model was being told about cocktails it could not order. A
    number that has to be remembered eventually becomes a lie.
    """
    active = (await db.execute(
        select(func.count()).select_from(Cocktail).where(Cocktail.active == True)  # noqa: E712
    )).scalar_one()

    menu = (await db.execute(
        select(Cocktail.name)
        .join(EventMenuItem, EventMenuItem.cocktail_id == Cocktail.id)
        .where(EventMenuItem.event_id == event.id)
    )).scalars().all()

    lines = [
        SYSTEM_PROMPT,
        "",
        "── THE EVENT YOU ARE WORKING ON ──",
        "You already have it. Never ask the person for an event id, and never ask",
        "them to tell you what is on screen — call get_event_details instead.",
        "",
        f"Name: {event.name}",
        f"Guests: {event.guest_count}",
        f"Duration: {event.duration_hours} hours",
    ]
    lines.append(
        f"Budget: ₪{event.budget:,.0f}" if event.budget is not None
        else "Budget: none set — report costs without an over/under verdict, and do not invent one."
    )
    lines.append(f"Status: {event.status}")
    lines.append(
        "Current menu: " + (", ".join(menu) if menu else "empty — nothing chosen yet")
    )
    lines.append(f"Catalogue: {active} active cocktails.")

    if current_tab:
        # One word, and it disambiguates most of what people actually type.
        # "Make it cheaper" from Shopping is about which bottles are being
        # bought; the same words from Menu are about which drinks are on it.
        hint = {
            "overview": "the event as a whole",
            "menu": "which cocktails are on the menu",
            "quantities": "how much of each ingredient is needed",
            "prep": "making the drinks — batches, recipes, method",
            "shopping": "what is being bought and from where",
            "suppliers": "which shops the order is split across",
            "costs": "what the event costs and against what budget",
        }.get(current_tab, current_tab)
        lines += [
            "",
            f"The person is looking at the {current_tab.upper()} tab — {hint}.",
            "Read an ambiguous request in that light. If they say 'make it cheaper'",
            "from SHOPPING they almost certainly mean cheaper products, not a",
            "smaller menu. Ask only if it is genuinely unclear.",
        ]
    return "\n".join(lines)


# How many recent tool results keep their full body. Older ones are replaced by
# a one-line stub naming the tool that produced them, so the model still sees
# that the call happened and can repeat it if it genuinely needs the detail.
KEEP_FULL_TOOL_RESULTS = 3
STUB_ABOVE_CHARS = 400


def trim_history(messages: list[Message]) -> list[Message]:
    """
    Keep the conversation from growing past what a provider will accept.

    Every iteration resends the whole history, so one large tool result is
    billed again on every remaining turn. A 6,000-character cocktail list that
    the model has already chosen from is pure weight — and it is what pushed a
    request to 8,888 tokens against Groq's 8,000-per-minute free tier.

    Only tool results are trimmed, and only ones that are both old and large.
    Never the person's messages, and never the model's own replies: those carry
    the reasoning the next turn depends on, and dropping them makes the agent
    forget what it just decided.
    """
    tool_positions = [i for i, m in enumerate(messages) if m.role == "tool"]
    keep = set(tool_positions[-KEEP_FULL_TOOL_RESULTS:])

    out: list[Message] = []
    for i, m in enumerate(messages):
        if m.role == "tool" and i not in keep and len(m.content) > STUB_ABOVE_CHARS:
            out.append(Message(
                role="tool",
                tool_call_id=m.tool_call_id,
                content=('{"note": "Earlier result omitted to keep the request '
                         'small. Call the tool again if you need it."}'),
            ))
        else:
            out.append(m)
    return out


# ── Main chat endpoint ────────────────────────────────────────────────────────


@router.post("/chat")
async def agent_chat(body: AgentChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Agentic chat. The model orchestrates; the Python engine does all the maths.

    Which model is a configuration choice (see app/services/llm.py) and does not
    affect any number produced here: every quantity and price still comes from
    app/engine/calculator.py through the tools below.
    """
    problem = describe_config(
        settings.LLM_PROVIDER, settings.resolved_llm_key, settings.resolved_llm_model
    )
    if problem:
        # 503, not 500: the service is fine, it just isn't configured yet.
        raise HTTPException(status_code=503, detail=problem)

    try:
        uid = uuid.UUID(body.event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    result = await db.execute(select(Event).where(Event.id == uid))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    try:
        llm = build_provider(
            settings.LLM_PROVIDER,
            settings.resolved_llm_key,
            settings.resolved_llm_model,
            settings.LLM_BASE_URL,
        )
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.message)

    messages = [Message(role=m.role, content=m.content) for m in body.messages]
    system = await build_system_prompt(event, db, body.current_tab)

    MAX_ITERATIONS = 10
    final_text = ""
    iteration = 0

    for iteration in range(MAX_ITERATIONS):
        try:
            reply = await llm.chat(
                system=system, messages=trim_history(messages), tools=TOOLS)
        except LLMError as e:
            raise HTTPException(status_code=e.status, detail=e.message)

        messages.append(Message(
            role="assistant", content=reply.text, tool_calls=reply.tool_calls,
        ))

        if not reply.tool_calls:
            final_text = reply.text
            break

        for tc in reply.tool_calls:
            output = await dispatch_tool(tc.name, tc.arguments, event, db)
            messages.append(Message(
                role="tool", tool_call_id=tc.id, content=json.dumps(output),
            ))

        # The tools write to the event, so persist before the next turn reads it.
        await db.commit()
        refreshed = await db.execute(select(Event).where(Event.id == uid))
        event = refreshed.scalar_one_or_none()

        # Some models keep calling tools and never write a closing message. Keep
        # the last text they did produce rather than returning an empty reply.
        if reply.text:
            final_text = reply.text
    else:
        final_text = final_text or (
            "I reached the maximum number of planning steps. Check the event "
            "details and try again."
        )

    # Persist this exchange so the event still has its conversation tomorrow.
    # Only the person's last turn and the answer: the earlier turns are already
    # stored from when they happened, and re-saving them would duplicate the
    # history on every request.
    try:
        last_user = next((m for m in reversed(body.messages) if m.role == "user"), None)
        if last_user is not None:
            db.add(EventMessage(event_id=uid, role="user",
                                content=last_user.content, tab=body.current_tab))
        db.add(EventMessage(event_id=uid, role="assistant",
                            content=final_text or "Done.", tab=body.current_tab))
        await db.commit()
    except Exception:
        # A conversation that fails to save must not fail the answer the person
        # is waiting for. Losing a transcript line is a much smaller harm than
        # losing the reply that took ten seconds and real money to produce.
        await db.rollback()

    return {
        "response": final_text or "Done.",
        "event_id": body.event_id,
        "event_status": event.status if event else None,
        "iterations": iteration + 1,
        "provider": settings.LLM_PROVIDER,
        "model": settings.resolved_llm_model,
    }

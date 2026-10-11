"""
One-shot planning: a sentence in, a complete costed plan out.

This is the front door. Someone types "50 אנשים, מרגריטות, 5000 שקל" and gets
back the menu, each recipe, the exact quantities to buy, and where to buy them
— without creating an event, picking a menu and pressing Calculate by hand.

It works with no Anthropic API key. The deterministic parser reads the
description and the engine does the maths; the LLM, when a key is present,
only improves *which cocktails get chosen*. It never touches a number, exactly
as everywhere else in this system.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models import (
    Event, EventMenuItem, EventRequirement, EventPurchaseItem,
    Cocktail, CocktailIngredient, Ingredient,
    IngredientProductMapping, SupplierProduct,
)
from app.engine.calculator import calculate_event
from app.services.describe_parser import parse as parse_description
from app.services.purchase_links import (
    resolve_purchase_link, RETAILERS, DEFAULT_RETAILER_KEY, LinkKind,
)
from app.api.events import _build_engine_inputs, _BLOCKED_REASONS, _order_line

router = APIRouter()

# Reliable crowd-pleasers, used to fill a menu when the description didn't name
# enough drinks. Ordered by how well they suit a mixed company event.
FALLBACK_MENU = [
    "Margarita", "Mojito", "Aperol Spritz", "Gin Gimlet",
    "Whiskey Sour", "Daiquiri", "Negroni", "Moscow Mule",
]

DEFAULT_MENU_SIZE = 3

# No arbitrary ceiling on menu size. Ask for ten cocktails and you get ten, as
# far as the library of costable drinks allows. The only bound is what actually
# exists — a limit of fact, not of policy.


class PlanRequest(BaseModel):
    description: str = Field(..., min_length=2, max_length=2000)
    event_name: Optional[str] = None
    retailer: Optional[str] = None


async def _costable_cocktail_ids(db: AsyncSession) -> set[str]:
    """
    Cocktails whose every ingredient maps to a product that has a price.

    Preferring these means the plan comes back with real numbers instead of a
    list of gaps — important while 26 ingredients are still unmapped.
    """
    priced_ing = (
        select(IngredientProductMapping.ingredient_id)
        .join(SupplierProduct,
              SupplierProduct.product_id == IngredientProductMapping.product_id)
        .where(SupplierProduct.price_after_vat.isnot(None),
               SupplierProduct.available == True)
    )

    result = await db.execute(
        select(
            CocktailIngredient.cocktail_id,
            func.count().label("total"),
            func.count().filter(CocktailIngredient.ingredient_id.in_(priced_ing)).label("ok"),
        ).group_by(CocktailIngredient.cocktail_id)
    )
    return {str(cid) for cid, total, ok in result.all() if total > 0 and total == ok}


async def _choose_menu(
    db: AsyncSession,
    wanted_names: list[str],
    size: int,
) -> tuple[list[Cocktail], list[str]]:
    """
    Resolve requested names to cocktails, then top up to `size`.

    Returns (chosen, notes). Notes explain any substitution, so nothing about
    the selection is silent.
    """
    notes: list[str] = []

    name_r = await db.execute(select(Cocktail).where(Cocktail.active == True))
    all_cocktails = name_r.scalars().all()
    by_name = {c.name.lower(): c for c in all_cocktails}
    costable = await _costable_cocktail_ids(db)

    chosen: list[Cocktail] = []
    for want in wanted_names:
        c = by_name.get(want.lower())
        if c is None:
            notes.append(f"“{want}” isn’t in the cocktail library — skipped.")
            continue
        if c.id in [x.id for x in chosen]:
            continue
        chosen.append(c)
        if str(c.id) not in costable:
            notes.append(
                f"{c.name} is on the menu, but some of its ingredients have no "
                f"price yet — its cost is missing from the total."
            )
        if len(chosen) >= size:
            break

    # Top up with reliable, fully-costable classics
    if len(chosen) < size:
        chosen_ids = {c.id for c in chosen}
        added: list[str] = []
        for name in FALLBACK_MENU:
            if len(chosen) >= size:
                break
            c = by_name.get(name.lower())
            if c is None or c.id in chosen_ids or str(c.id) not in costable:
                continue
            chosen.append(c)
            chosen_ids.add(c.id)
            added.append(c.name)
        if added:
            notes.append("Added " + ", ".join(added) + " to round out the menu.")

    # Still short: any costable CLASSIC, in name order for stability.
    #
    # Deliberately excludes the 'private signature' set. Those are showpiece drinks built
    # on three tequilas, purées and whole chillies — fine when someone asks for
    # them by name, wrong to slip into a company happy hour unasked, and they
    # distort the budget badly.
    if len(chosen) < size:
        chosen_ids = {c.id for c in chosen}
        for c in sorted(all_cocktails, key=lambda x: x.name):
            if len(chosen) >= size:
                break
            if (c.id not in chosen_ids
                    and str(c.id) in costable
                    and (c.theme or "classic") == "classic"):
                chosen.append(c)
                chosen_ids.add(c.id)

    return chosen, notes


# A single line item swallowing most of the budget is nearly always a recipe
# quantity that means something other than what it says — not a real cost.
# Surfacing it beats printing a confident total nobody should trust.
_DOMINANCE_THRESHOLD = 0.35
_IMPLAUSIBLE_UNIT_COUNT = 200


def _sanity_warnings(purchase_items, total_cost: float | None) -> list[str]:
    out: list[str] = []

    # A share of an incomplete total is meaningless. When some items have no
    # price, the total is artificially small and every priced item looks
    # dominant — so the dominance check only runs on a complete cost.
    cost_is_complete = all(
        i.total_price is not None for i in purchase_items
    )

    for item in purchase_items:
        if item.total_price is None or not total_cost:
            continue
        share = item.total_price / total_cost
        if cost_is_complete and share >= _DOMINANCE_THRESHOLD:
            out.append(
                f"{item.canonical_name} is {share:.0%} of the total (₪{item.total_price:,.0f}). "
                f"That usually means the recipe amount is wrong — check it before ordering."
            )
        if (item.packages_required or 0) >= _IMPLAUSIBLE_UNIT_COUNT and \
                (item.package_unit or "") == "pieces":
            out.append(
                f"{item.canonical_name}: {item.packages_required} individual units looks "
                f"implausible for {item.required_amount:.0f} {item.unit} — worth checking "
                f"the recipe uses the unit you expect."
            )
    return out


@router.post("", status_code=201)
async def create_plan(body: PlanRequest, db: AsyncSession = Depends(get_db)):
    """Description in, complete costed plan out."""
    retailer_key = body.retailer or DEFAULT_RETAILER_KEY
    if retailer_key not in RETAILERS:
        raise HTTPException(status_code=400, detail=f"Unknown retailer '{retailer_key}'")

    parsed = parse_description(body.description)
    notes: list[str] = []

    # Naming drinks IS the menu. Padding a named request up to some default
    # size overrides what the person actually asked for — ask for margaritas
    # and a negroni and you should get exactly those two, not a third drink
    # chosen for you.
    if parsed.requested_count:
        size = parsed.requested_count
    elif parsed.named_cocktails:
        size = len(parsed.named_cocktails)
    else:
        size = max(DEFAULT_MENU_SIZE, len(parsed.requested_cocktails))
    size = max(1, size)

    chosen, menu_notes = await _choose_menu(db, parsed.requested_cocktails, size)
    notes.extend(menu_notes)

    if len(chosen) < size:
        notes.append(
            f"You asked for {size} cocktails; {len(chosen)} could be put together. "
            f"The rest of the library has ingredients without a price yet — see "
            f"the Mappings page."
        )

    if not chosen:
        raise HTTPException(
            status_code=422,
            detail="Could not put a menu together — no cocktails have complete "
                   "pricing yet. Map some ingredients on the Mapping screen first.",
        )

    # ── Create the event ──────────────────────────────────────────────────────
    event = Event(
        name=body.event_name or _derive_name(parsed.guests),
        guest_count=parsed.guests,
        budget=parsed.budget,
        duration_hours=settings.DEFAULT_DURATION_HOURS,
        expected_drinks_per_guest=parsed.drinks_per_guest or settings.DEFAULT_DRINKS_PER_GUEST,
        non_alcoholic_pct=settings.DEFAULT_NON_ALCOHOLIC_PCT,
        waste_buffer_pct=settings.DEFAULT_WASTE_BUFFER_PCT,
        ai_request=body.description,
        status="MENU_PROPOSED",
    )
    db.add(event)
    await db.flush()

    share = round(1.0 / len(chosen), 4)
    for i, c in enumerate(chosen):
        # Give the last one the remainder so the allocations sum to exactly 1.0
        pct = share if i < len(chosen) - 1 else round(1.0 - share * (len(chosen) - 1), 4)
        db.add(EventMenuItem(event_id=event.id, cocktail_id=c.id, allocation_pct=pct))
    await db.flush()

    # ── Run the deterministic engine ──────────────────────────────────────────
    menu_allocs, recipes, ingredient_products = await _build_engine_inputs(db, event)
    calc = calculate_event(
        guests=event.guest_count,
        drinks_per_guest=float(event.expected_drinks_per_guest),
        non_alcoholic_pct=float(event.non_alcoholic_pct),
        waste_buffer_pct=float(event.waste_buffer_pct),
        menu=menu_allocs,
        recipes=recipes,
        ingredient_products=ingredient_products,
        budget=float(event.budget) if event.budget is not None else None,
    )

    now = datetime.now(timezone.utc)
    for req in calc.ingredient_requirements:
        db.add(EventRequirement(
            event_id=event.id, ingredient_id=uuid.UUID(req.ingredient_id),
            required_amount=req.required_amount, unit=req.unit, calculated_at=now,
        ))
    for item in calc.purchase_items:
        db.add(EventPurchaseItem(
            event_id=event.id,
            ingredient_id=uuid.UUID(item.ingredient_id),
            product_id=uuid.UUID(item.product_id) if item.product_id else None,
            required_amount=item.required_amount, required_unit=item.unit,
            packages_required=item.packages_required,
            package_size=item.package_size, package_unit=item.package_unit,
            unit_price=item.unit_price, total_price=item.total_price,
            status=item.status.value,
            supplier_id=uuid.UUID(item.supplier_id) if item.supplier_id else None,
            product_url=item.product_url,
        ))
    mi_r = await db.execute(select(EventMenuItem).where(EventMenuItem.event_id == event.id))
    for mi in mi_r.scalars().all():
        cid = str(mi.cocktail_id)
        if cid in calc.cocktail_servings:
            mi.expected_servings = calc.cocktail_servings[cid]

    event.status = "COSTED"
    await db.commit()

    # ── Shape the response ────────────────────────────────────────────────────
    recipe_r = await db.execute(
        select(Cocktail)
        .options(selectinload(Cocktail.ingredients).selectinload(CocktailIngredient.ingredient))
        .where(Cocktail.id.in_([c.id for c in chosen]))
    )
    detailed = {str(c.id): c for c in recipe_r.scalars().all()}

    menu_out = []
    for c in chosen:
        cid = str(c.id)
        full = detailed.get(cid)
        servings = calc.cocktail_servings.get(cid, 0)
        menu_out.append({
            "cocktail_id": cid,
            "name": c.name,
            "servings": servings,
            "allocation_pct": round(1.0 / len(chosen), 4),
            "glass": full.glass_type if full else None,
            "technique": full.technique if full else None,
            "garnish": full.garnish if full else None,
            "recipe": [
                {
                    "ingredient": ci.ingredient.canonical_name if ci.ingredient else "?",
                    "amount": float(ci.amount) if ci.amount is not None else None,
                    "unit": ci.unit or "ml",
                    # What this one cocktail needs across the whole event
                    "total_for_event": (
                        round(float(ci.amount) * servings, 1)
                        if ci.amount is not None else None
                    ),
                }
                for ci in (full.ingredients if full else [])
            ],
        })

    groups: dict[str, dict] = {}
    blocked: list[dict] = []
    for item in calc.purchase_items:
        if item.status.value != "OK" or not item.packages_required:
            blocked.append({
                "ingredient_name": item.canonical_name,
                "required_amount": round(item.required_amount, 1),
                "unit": item.unit,
                "status": item.status.value,
                "reason": _BLOCKED_REASONS.get(item.status.value, "Not ready to order."),
            })
            continue

        link = resolve_purchase_link(
            direct_url=item.product_url,
            product_name=item.product_name,
            canonical_name=item.canonical_name,
            retailer_key=retailer_key,
        )
        key = f"retailer:{link.retailer_key or retailer_key}"
        g = groups.setdefault(key, {
            "store_name": link.retailer_name or retailer_key,
            "store_website": RETAILERS[retailer_key].website,
            "items": [], "subtotal": 0.0,
        })
        g["items"].append({
            "ingredient_name": item.canonical_name,
            "product_name": item.product_name,
            "order_line": _order_line(item.packages_required, item.package_size, item.package_unit),
            "packages_required": item.packages_required,
            "total_price": item.total_price,
            "purchase_link": link.as_dict(),
        })
        if item.total_price is not None:
            g["subtotal"] = round(g["subtotal"] + item.total_price, 2)

    for g in groups.values():
        g["items"].sort(key=lambda i: -(i["total_price"] or 0))

    return {
        "event_id": str(event.id),
        "event_name": event.name,
        "parsed": parsed.as_dict(),
        "totals": {
            "guests": calc.guests,
            "total_drinks": calc.total_drinks,
            "alcoholic_drinks": calc.alcoholic_drinks,
            "non_alcoholic_drinks": calc.non_alcoholic_drinks,
            "cost": calc.total_cost,
            "cost_per_guest": calc.cost_per_guest,
            "budget": float(event.budget) if event.budget is not None else None,
            "budget_status": calc.budget_status.value if calc.budget_status else None,
            "budget_variance": calc.budget_variance,
        },
        "menu": menu_out,
        "shopping": {
            "groups": sorted(groups.values(), key=lambda g: -g["subtotal"]),
            "blocked": blocked,
            "retailer": {
                "key": retailer_key,
                "name": RETAILERS[retailer_key].display_name,
                "search_linkable": RETAILERS[retailer_key].search_url_template is not None,
            },
            "available_retailers": [
                {"key": r.key, "name": r.display_name,
                 "search_linkable": r.search_url_template is not None}
                for r in RETAILERS.values()
            ],
        },
        "notes": notes,
        "engine_warnings": calc.warnings,
        "sanity_warnings": _sanity_warnings(calc.purchase_items, calc.total_cost),
    }


def _derive_name(guests: int) -> str:
    return f"Happy hour · {guests} guests"

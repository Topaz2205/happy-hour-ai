from urllib.parse import quote_plus
"""
Events API — create events, set menu, run the calculation engine.
"""
import uuid
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.services.module1_recipes import get_recipes
from app.services.module3_matching import to_engine_inputs

from app.db.session import get_db
from app.models import (
    EventIngredientProductOverride,
    EventMessage,
    Event,
    EventMenuItem,
    EventRequirement,
    EventPurchaseItem,
    Cocktail,
    CocktailIngredient,
    Ingredient,
    Product,
    IngredientProductMapping,
    SupplierProduct,
    Supplier,
    Company,
)

from app.engine.batch import scale_recipe, batch_to_dict

from app.engine.equipment import (
    plan_equipment,
    plan_to_dict,
    EquipmentPrice,
)

from app.engine.calculator import (
    calculate_event,
    MenuAllocation,
    CocktailRecipe,
    RecipeIngredient,
    IngredientWithProduct,
    ProductInfo,
    PurchaseStatus,
)

from app.services.purchase_links import (
    resolve_purchase_link,
    RETAILERS,
    DEFAULT_RETAILER_KEY,
    LinkKind,
)


router = APIRouter()


# ── Request/response schemas ──────────────────────────────────────────────────


class CreateEventRequest(BaseModel):
    name: str
    company_name: Optional[str] = None
    event_date: Optional[str] = None
    location: Optional[str] = None

    # Generous bounds, present only to reject obvious nonsense
    guest_count: int = Field(..., ge=1, le=100_000)

    budget: float = Field(..., ge=0)

    duration_hours: float = Field(
        2.5,
        ge=0.5,
        le=48,
    )

    expected_drinks_per_guest: float = Field(
        2.5,
        ge=0.5,
        le=50,
    )

    non_alcoholic_pct: float = Field(
        0.25,
        ge=0,
        le=1,
    )

    theme: Optional[str] = None

    ai_request: Optional[str] = None

    waste_buffer_pct: float = Field(
        0.08,
        ge=0,
        le=0.5,
    )


class UpdateEventRequest(BaseModel):
    name: Optional[str] = None
    event_date: Optional[str] = None
    location: Optional[str] = None
    guest_count: Optional[int] = Field(None, ge=1, le=100_000)
    budget: Optional[float] = Field(None, ge=0)


class MenuItemRequest(BaseModel):
    cocktail_id: str

    allocation_pct: float = Field(
        ...,
        gt=0,
        le=1,
    )

    ai_rationale: Optional[str] = None


class SetMenuRequest(BaseModel):
    menu: list[MenuItemRequest]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _fetch_or_create_company(
    db: AsyncSession,
    name: str,
) -> Company:

    result = await db.execute(
        select(Company).where(
            Company.name == name
        )
    )

    company = result.scalar_one_or_none()

    if company is None:

        company = Company(
            name=name
        )

        db.add(company)

        await db.flush()

    return company


async def _build_engine_inputs(
    db: AsyncSession,
    event: Event,
):
    """
    Build the three inputs required by the deterministic calculation engine.

    Flow:

        Event menu
        ↓
        Module 1 — canonical recipes
        ↓
        Module 3 — ingredient/product resolution
        ↓
        Module 2 — supplier price + actual package size

    Returns:

        (
            menu_allocations,
            recipes_dict,
            ingredient_products_dict
        )
    """

    # ---------------------------------------------------------
    # 1. Load menu items for this event
    # ---------------------------------------------------------

    menu_result = await db.execute(
        select(EventMenuItem).where(
            EventMenuItem.event_id == event.id
        )
    )

    menu_items = menu_result.scalars().all()

    # ---------------------------------------------------------
    # 2. Convert menu to calculator format
    # ---------------------------------------------------------

    menu_allocs = [
        MenuAllocation(
            cocktail_id=str(
                menu_item.cocktail_id
            ),
            allocation_pct=float(
                menu_item.allocation_pct
            ),
        )
        for menu_item in menu_items
    ]

    if not menu_items:

        return (
            menu_allocs,
            {},
            {},
        )

    # ---------------------------------------------------------
    # 3. MODULE 1 — recipes
    # ---------------------------------------------------------

    cocktail_ids = [
        menu_item.cocktail_id
        for menu_item in menu_items
    ]

    recipes = await get_recipes(
        db,
        cocktail_ids,
    )

    if not recipes:

        return (
            menu_allocs,
            {},
            {},
        )

    # ---------------------------------------------------------
    # 4. Collect all ingredients
    # ---------------------------------------------------------

    ingredient_ids: set[str] = set()

    for recipe in recipes.values():

        for ingredient in recipe.ingredients:

            ingredient_ids.add(
                ingredient.ingredient_id
            )

    if not ingredient_ids:

        return (
            menu_allocs,
            recipes,
            {},
        )

    # ---------------------------------------------------------
    # 5. MODULE 3 + MODULE 2
    #
    # Module 3:
    #
    # Event override
    # ↓
    # Preferred house mapping
    # ↓
    # Missing
    #
    # Module 2:
    #
    # Product
    # ↓
    # Supplier
    # ↓
    # Actual supplier package size
    # ↓
    # Price
    # ↓
    # Historical fallback
    # ---------------------------------------------------------

    ingredient_products = await to_engine_inputs(
        db,
        ingredient_ids,
        event.id,
    )

    # ---------------------------------------------------------
    # 6. Return exactly what calculator expects
    # ---------------------------------------------------------

    return (
        menu_allocs,
        recipes,
        ingredient_products,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=201,
)
async def create_event(
    body: CreateEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new event draft."""

    company_id = None

    if body.company_name:

        company = await _fetch_or_create_company(
            db,
            body.company_name,
        )

        company_id = company.id

    event_date = None

    if body.event_date:

        try:

            from datetime import date

            event_date = date.fromisoformat(
                body.event_date
            )

        except ValueError:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid event_date format. "
                    "Use YYYY-MM-DD."
                ),
            )

    event = Event(
        company_id=company_id,
        name=body.name,
        event_date=event_date,
        location=body.location,
        guest_count=body.guest_count,
        budget=body.budget,
        duration_hours=body.duration_hours,
        expected_drinks_per_guest=(
            body.expected_drinks_per_guest
        ),
        non_alcoholic_pct=(
            body.non_alcoholic_pct
        ),
        theme=body.theme,
        ai_request=body.ai_request,
        waste_buffer_pct=(
            body.waste_buffer_pct
        ),
        status="DRAFT",
    )

    db.add(event)

    await db.commit()

    await db.refresh(event)

    return {
        "id": str(event.id),
        "name": event.name,
        "status": event.status,
    }


@router.get("")
async def list_events(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    Every event, newest first, with just enough to render a list row.

    Estimated cost comes from saved purchase items.
    """

    result = await db.execute(
        select(Event)
        .order_by(
            Event.created_at.desc()
        )
        .limit(limit)
    )

    events = result.scalars().all()

    if not events:

        return {
            "count": 0,
            "items": [],
        }

    ids = [
        event.id
        for event in events
    ]

    menu_counts = dict(
        (
            await db.execute(
                select(
                    EventMenuItem.event_id,
                    func.count(),
                )
                .where(
                    EventMenuItem.event_id.in_(
                        ids
                    )
                )
                .group_by(
                    EventMenuItem.event_id
                )
            )
        ).all()
    )

    cost_rows = (
        await db.execute(
            select(
                EventPurchaseItem.event_id,
                func.coalesce(
                    func.sum(
                        EventPurchaseItem.total_price
                    ),
                    0,
                ),
                func.count(),
                func.count().filter(
                    EventPurchaseItem
                    .total_price
                    .is_(None)
                ),
            )
            .where(
                EventPurchaseItem.event_id.in_(
                    ids
                )
            )
            .group_by(
                EventPurchaseItem.event_id
            )
        )
    ).all()

    costs = {
        row[0]: (
            float(row[1]),
            row[2],
            row[3],
        )
        for row in cost_rows
    }

    items = []

    for event in events:

        total, n_items, n_unpriced = (
            costs.get(
                event.id,
                (0.0, 0, 0),
            )
        )

        items.append(
            {
                "id": str(event.id),

                "name": event.name,

                "status": event.status,

                "guest_count": (
                    event.guest_count
                ),

                "budget": (
                    float(event.budget)
                    if event.budget is not None
                    else None
                ),

                "location": event.location,

                "event_date": (
                    event.event_date.isoformat()
                    if event.event_date
                    else None
                ),

                "theme": event.theme,

                "menu_count": (
                    menu_counts.get(
                        event.id,
                        0,
                    )
                ),

                "estimated_cost": (
                    round(total, 2)
                    if n_items
                    else None
                ),

                "cost_is_partial": bool(
                    n_unpriced
                ),

                "created_at": (
                    event.created_at.isoformat()
                    if event.created_at
                    else None
                ),
            }
        )

    return {
        "count": len(items),
        "items": items,
    }


@router.patch("/{event_id}")
async def update_event(
    event_id: str,
    body: UpdateEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update the editable event details."""
    try:
        uid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = (
        await db.execute(
            select(Event).where(Event.id == uid)
        )
    ).scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    supplied = body.model_fields_set
    guest_count_changed = False

    if "name" in supplied:
        name = (body.name or "").strip()
        if not name:
            raise HTTPException(
                status_code=422,
                detail="Event name cannot be empty",
            )
        event.name = name

    if "location" in supplied:
        event.location = (
            body.location.strip()
            if body.location and body.location.strip()
            else None
        )

    if "event_date" in supplied:
        if body.event_date:
            try:
                event.event_date = datetime.fromisoformat(
                    body.event_date
                ).date()
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail="event_date must be YYYY-MM-DD",
                )
        else:
            event.event_date = None

    if "guest_count" in supplied:
        if body.guest_count is None:
            raise HTTPException(
                status_code=422,
                detail="guest_count cannot be empty",
            )

        guest_count_changed = (
            int(body.guest_count) != event.guest_count
        )
        event.guest_count = int(body.guest_count)

    if "budget" in supplied:
        event.budget = body.budget

    await db.flush()

    # Guest count changes quantities, so a previously costed event
    # must be recalculated rather than showing stale numbers.
    if guest_count_changed:
        menu_exists = (
            await db.execute(
                select(EventMenuItem.id)
                .where(EventMenuItem.event_id == uid)
                .limit(1)
            )
        ).first()

        if menu_exists:
            await _recalculate(uid, db)
        else:
            await db.commit()
    else:
        await db.commit()

    return {
        "id": str(event.id),
        "name": event.name,
        "guest_count": event.guest_count,
        "budget": (
            float(event.budget)
            if event.budget is not None
            else None
        ),
        "location": event.location,
        "event_date": (
            event.event_date.isoformat()
            if event.event_date
            else None
        ),
        "status": event.status,
    }


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete one event and its event-scoped data."""
    try:
        uid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = (
        await db.execute(
            select(Event).where(Event.id == uid)
        )
    ).scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # Explicit deletion keeps this safe even if a database relationship
    # does not have ON DELETE CASCADE configured.
    dependent_models = (
        EventMessage,
        EventIngredientProductOverride,
        EventPurchaseItem,
        EventRequirement,
        EventMenuItem,
    )

    for model in dependent_models:
        rows = (
            await db.execute(
                select(model).where(model.event_id == uid)
            )
        ).scalars().all()

        for row in rows:
            await db.delete(row)

    await db.delete(event)
    await db.commit()

    return {
        "deleted": True,
        "id": event_id,
    }


@router.get("/{event_id}")
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get event details and current menu."""

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    result = await db.execute(
        select(Event)
        .options(
            selectinload(
                Event.menu_items
            ).selectinload(
                EventMenuItem.cocktail
            )
        )
        .where(
            Event.id == uid
        )
    )

    event = result.scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    menu = [
        {
            "cocktail_id": str(
                menu_item.cocktail_id
            ),

            "cocktail_name": (
                menu_item.cocktail.name
                if menu_item.cocktail
                else None
            ),

            "allocation_pct": float(
                menu_item.allocation_pct
            ),

            "expected_servings": (
                menu_item.expected_servings
            ),

            "ai_rationale": (
                menu_item.ai_rationale
            ),
        }
        for menu_item in event.menu_items
    ]

    return {
        "id": str(event.id),

        "name": event.name,

        "event_date": (
            event.event_date.isoformat()
            if event.event_date
            else None
        ),

        "location": event.location,

        "guest_count": event.guest_count,

        "budget": (
            float(event.budget)
            if event.budget is not None
            else None
        ),

        "is_workshop": bool(
            event.is_workshop
        ),

        "people_per_station": int(
            event.people_per_station or 2
        ),

        "duration_hours": float(
            event.duration_hours
        ),

        "expected_drinks_per_guest": float(
            event.expected_drinks_per_guest
        ),

        "non_alcoholic_pct": float(
            event.non_alcoholic_pct
        ),

        "waste_buffer_pct": float(
            event.waste_buffer_pct
        ),

        "theme": event.theme,

        "status": event.status,

        "ai_request": event.ai_request,

        "menu": menu,
    }


@router.put("/{event_id}/menu")
async def set_menu(
    event_id: str,
    body: SetMenuRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set cocktail menu for event."""

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    result = await db.execute(
        select(Event).where(
            Event.id == uid
        )
    )

    event = result.scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    # Validate allocations

    total = sum(
        item.allocation_pct
        for item in body.menu
    )

    if abs(total - 1.0) > 0.02:

        raise HTTPException(
            status_code=422,
            detail=(
                "Menu allocations must sum "
                f"to 1.0 (100%). Got {total:.4f}."
            ),
        )

    # Validate cocktail IDs

    cocktail_ids = [
        uuid.UUID(
            item.cocktail_id
        )
        for item in body.menu
    ]

    result2 = await db.execute(
        select(
            Cocktail.id
        ).where(
            Cocktail.id.in_(
                cocktail_ids
            )
        )
    )

    found_ids = {
        str(row[0])
        for row in result2.all()
    }

    missing = [
        item
        for item in body.menu
        if item.cocktail_id not in found_ids
    ]

    if missing:

        raise HTTPException(
            status_code=404,
            detail=(
                "Cocktails not found: "
                f"{[m.cocktail_id for m in missing]}"
            ),
        )

    # Delete existing menu

    existing = await db.execute(
        select(
            EventMenuItem
        ).where(
            EventMenuItem.event_id == uid
        )
    )

    for menu_item in existing.scalars().all():

        await db.delete(
            menu_item
        )

    # Clear old requirements

    existing_req = await db.execute(
        select(
            EventRequirement
        ).where(
            EventRequirement.event_id == uid
        )
    )

    for requirement in (
        existing_req.scalars().all()
    ):

        await db.delete(
            requirement
        )

    # Clear old purchase items

    existing_pi = await db.execute(
        select(
            EventPurchaseItem
        ).where(
            EventPurchaseItem.event_id == uid
        )
    )

    for purchase_item in (
        existing_pi.scalars().all()
    ):

        await db.delete(
            purchase_item
        )

    # Add new menu

    for item in body.menu:

        db.add(
            EventMenuItem(
                event_id=uid,

                cocktail_id=uuid.UUID(
                    item.cocktail_id
                ),

                allocation_pct=(
                    item.allocation_pct
                ),

                ai_rationale=(
                    item.ai_rationale
                ),
            )
        )

    event.status = "MENU_PROPOSED"

    await db.commit()

    return {
        "status": "ok",
        "menu_item_count": len(
            body.menu
        ),
    }


@router.post("/{event_id}/calculate")
async def calculate(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Run deterministic calculation engine.

    All maths is performed by:
        app/engine/calculator.py
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    result = await db.execute(
        select(Event)
        .options(
            selectinload(
                Event.menu_items
            ).selectinload(
                EventMenuItem.cocktail
            ),

            selectinload(
                Event.menu_items
            ),
        )
        .where(
            Event.id == uid
        )
    )

    event = result.scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    if not event.menu_items:

        raise HTTPException(
            status_code=422,
            detail=(
                "Event has no menu items. "
                "Set a menu first."
            ),
        )

    # ---------------------------------------------------------
    # Fetch recipes + mapped products + prices
    # ---------------------------------------------------------

    (
        menu_allocs,
        recipes,
        ingredient_products,
    ) = await _build_engine_inputs(
        db,
        event,
    )

    # ---------------------------------------------------------
    # Deterministic calculation
    # ---------------------------------------------------------

    calc_result = calculate_event(
        guests=event.guest_count,

        drinks_per_guest=float(
            event.expected_drinks_per_guest
        ),

        non_alcoholic_pct=float(
            event.non_alcoholic_pct
        ),

        waste_buffer_pct=float(
            event.waste_buffer_pct
        ),

        menu=menu_allocs,

        recipes=recipes,

        ingredient_products=(
            ingredient_products
        ),

        budget=(
            float(event.budget)
            if event.budget is not None
            else None
        ),
    )

    now = datetime.now(
        timezone.utc
    )

    # ---------------------------------------------------------
    # Clear old results
    # ---------------------------------------------------------

    old_req = await db.execute(
        select(
            EventRequirement
        ).where(
            EventRequirement.event_id == uid
        )
    )

    for requirement in (
        old_req.scalars().all()
    ):

        await db.delete(
            requirement
        )

    old_pi = await db.execute(
        select(
            EventPurchaseItem
        ).where(
            EventPurchaseItem.event_id == uid
        )
    )

    for purchase_item in (
        old_pi.scalars().all()
    ):

        await db.delete(
            purchase_item
        )

    # ---------------------------------------------------------
    # Save ingredient requirements
    # ---------------------------------------------------------

    for req in (
        calc_result.ingredient_requirements
    ):

        db.add(
            EventRequirement(
                event_id=uid,

                ingredient_id=uuid.UUID(
                    req.ingredient_id
                ),

                required_amount=(
                    req.required_amount
                ),

                unit=req.unit,

                calculated_at=now,
            )
        )

    # ---------------------------------------------------------
    # Save purchase items
    # ---------------------------------------------------------

    for item in (
        calc_result.purchase_items
    ):

        db.add(
            EventPurchaseItem(
                event_id=uid,

                ingredient_id=uuid.UUID(
                    item.ingredient_id
                ),

                product_id=(
                    uuid.UUID(
                        item.product_id
                    )
                    if item.product_id
                    else None
                ),

                required_amount=(
                    item.required_amount
                ),

                required_unit=(
                    item.unit
                ),

                packages_required=(
                    item.packages_required
                ),

                package_size=(
                    item.package_size
                ),

                package_unit=(
                    item.package_unit
                ),

                unit_price=(
                    item.unit_price
                ),

                total_price=(
                    item.total_price
                ),

                status=(
                    item.status.value
                ),

                supplier_id=(
                    uuid.UUID(
                        item.supplier_id
                    )
                    if item.supplier_id
                    else None
                ),

                product_url=(
                    item.product_url
                ),
            )
        )

    # ---------------------------------------------------------
    # Update cocktail serving counts
    # ---------------------------------------------------------

    for menu_item in event.menu_items:

        cocktail_id = str(
            menu_item.cocktail_id
        )

        if cocktail_id in (
            calc_result.cocktail_servings
        ):

            menu_item.expected_servings = (
                calc_result
                .cocktail_servings[
                    cocktail_id
                ]
            )

    event.status = "COSTED"

    await db.commit()

    return _format_calc_result(
        calc_result
    )


@router.get("/{event_id}/shopping-list")
async def shopping_list(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return purchase list for event."""

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    result = await db.execute(
        select(
            EventPurchaseItem
        )
        .options(
            selectinload(
                EventPurchaseItem.ingredient
            ),

            selectinload(
                EventPurchaseItem.product
            ),

            selectinload(
                EventPurchaseItem.supplier
            ),
        )
        .where(
            EventPurchaseItem.event_id == uid
        )
        .order_by(
            EventPurchaseItem.status
        )
    )

    items = result.scalars().all()

    if not items:

        raise HTTPException(
            status_code=404,
            detail=(
                "No shopping list found. "
                "Run /calculate first."
            ),
        )

    return {
        "event_id": event_id,

        "items": [
            {
                "ingredient_id": str(
                    item.ingredient_id
                ),

                "product_id": (
                    str(item.product_id)
                    if item.product_id
                    else None
                ),

                "ingredient_name": (
                    item.ingredient.canonical_name
                    if item.ingredient
                    else "UNKNOWN"
                ),

                "product_name": (
                    item.product.name
                    if item.product
                    else None
                ),

                "required_amount": float(
                    item.required_amount
                ),

                "unit": (
                    item.required_unit
                ),

                "packages_required": (
                    item.packages_required
                ),

                "package_size": (
                    float(
                        item.package_size
                    )
                    if item.package_size
                    else None
                ),

                "package_unit": (
                    item.package_unit
                ),

                "unit_price": (
                    float(
                        item.unit_price
                    )
                    if item.unit_price
                    else None
                ),

                "total_price": (
                    float(
                        item.total_price
                    )
                    if item.total_price
                    else None
                ),

                "status": item.status,

                "supplier_name": (
                    item.supplier.name
                    if item.supplier
                    else None
                ),

                "product_url": (
                    item.product_url
                ),
            }
            for item in items
        ],

        "total_cost": round(
            sum(
                float(
                    item.total_price
                )
                for item in items
                if item.total_price
                is not None
            ),
            2,
        ),

        "has_missing_data": any(
            item.status != "OK"
            for item in items
        ),
    }


@router.get("/{event_id}/purchase-plan")
async def purchase_plan(
    event_id: str,
    retailer: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Shopping list arranged by shop.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    retailer_key = (
        retailer
        or DEFAULT_RETAILER_KEY
    )

    if retailer_key not in RETAILERS:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown retailer "
                f"'{retailer_key}'. "
                f"Known: "
                f"{sorted(RETAILERS)}"
            ),
        )

    result = await db.execute(
        select(
            EventPurchaseItem
        )
        .options(
            selectinload(
                EventPurchaseItem.ingredient
            ),

            selectinload(
                EventPurchaseItem.product
            ),

            selectinload(
                EventPurchaseItem.supplier
            ),
        )
        .where(
            EventPurchaseItem.event_id == uid
        )
    )

    items = result.scalars().all()

    if not items:

        raise HTTPException(
            status_code=404,
            detail=(
                "No purchase plan. "
                "Run /calculate first."
            ),
        )

    groups: dict[str, dict] = {}

    blocked: list[dict] = []

    for item in items:

        ingredient_name = (
            item.ingredient.canonical_name
            if item.ingredient
            else "UNKNOWN"
        )

        product_name = (
            item.product.name
            if item.product
            else None
        )

        if (
            item.status != "OK"
            or not item.packages_required
        ):

            blocked.append(
                {
                    "ingredient_name": (
                        ingredient_name
                    ),

                    "product_name": (
                        product_name
                    ),

                    "required_amount": (
                        float(
                            item.required_amount
                        )
                        if item.required_amount
                        else None
                    ),

                    "unit": (
                        item.required_unit
                    ),

                    "status": (
                        item.status
                    ),

                    "reason": (
                        _BLOCKED_REASONS.get(
                            item.status,
                            "Not ready to order.",
                        )
                    ),
                }
            )

            continue

        link = resolve_purchase_link(
            direct_url=(
                item.product_url
            ),

            direct_url_supplier_name=(
                item.supplier.name
                if item.supplier
                else None
            ),

            product_name=(
                product_name
            ),

            canonical_name=(
                ingredient_name
            ),

            retailer_key=(
                retailer_key
            ),
        )

        # Group by the real pricing source.
        # The selected retailer may still provide a fallback purchase link,
        # but it must not be shown as the source of this price.
        if item.supplier:
            key = f"supplier:{item.supplier_id}"
            group_name = item.supplier.name
        else:
            key = f"retailer:{link.retailer_key or retailer_key}"
            group_name = link.retailer_name or retailer_key

        group = groups.setdefault(
            key,
            {
                "group_key": key,

                "store_name": (
                    group_name
                ),

                "store_website": (
                    RETAILERS[
                        retailer_key
                    ].website
                    if key.startswith(
                        "retailer:"
                    )
                    else (
                        item.supplier.website
                        if item.supplier
                        else None
                    )
                ),

                "items": [],

                "subtotal": 0.0,
            },
        )

        total_price = (
            float(
                item.total_price
            )
            if item.total_price
            is not None
            else None
        )

        package_size = (
            float(
                item.package_size
            )
            if item.package_size
            else None
        )

        group["items"].append(
            {
                "ingredient_name": (
                    ingredient_name
                ),

                "product_name": (
                    product_name
                ),

                "order_line": _order_line(
                    item.packages_required,
                    package_size,
                    item.package_unit,
                ),

                "packages_required": (
                    item.packages_required
                ),

                "package_size": (
                    package_size
                ),

                "package_unit": (
                    item.package_unit
                ),

                "required_amount": (
                    float(
                        item.required_amount
                    )
                    if item.required_amount
                    else None
                ),

                "unit": (
                    item.required_unit
                ),

                "unit_price": (
                    float(
                        item.unit_price
                    )
                    if item.unit_price
                    is not None
                    else None
                ),

                "total_price": (
                    total_price
                ),

                "purchase_link": (
                    link.as_dict()
                ),
            }
        )

        if total_price is not None:

            group["subtotal"] = round(
                group["subtotal"]
                + total_price,
                2,
            )

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            -group["subtotal"]
        ),
    )

    for group in ordered_groups:

        group["item_count"] = len(
            group["items"]
        )

        group["items"].sort(
            key=lambda item: -(
                item["total_price"]
                or 0
            )
        )

    return {
        "event_id": event_id,

        "retailer": {
            "key": retailer_key,

            "name": (
                RETAILERS[
                    retailer_key
                ].display_name
            ),

            "website": (
                RETAILERS[
                    retailer_key
                ].website
            ),

            "search_linkable": (
                RETAILERS[
                    retailer_key
                ]
                .search_url_template
                is not None
            ),

            "note": (
                RETAILERS[
                    retailer_key
                ]
                .verification_note
            ),
        },

        "available_retailers": [
            {
                "key": retailer.key,

                "name": (
                    retailer.display_name
                ),

                "search_linkable": (
                    retailer
                    .search_url_template
                    is not None
                ),
            }
            for retailer
            in RETAILERS.values()
        ],

        "groups": (
            ordered_groups
        ),

        "orderable_total": round(
            sum(
                group["subtotal"]
                for group
                in ordered_groups
            ),
            2,
        ),

        "orderable_item_count": sum(
            len(group["items"])
            for group
            in ordered_groups
        ),

        "blocked": blocked,

        "blocked_count": len(
            blocked
        ),
    }


_BLOCKED_REASONS = {
    "PRODUCT_MAPPING_REQUIRED": (
        "No product chosen yet — "
        "map it on the Mapping page."
    ),

    "PRICE_MISSING": (
        "Product has no price on file, "
        "so it cannot be costed or ordered."
    ),

    "SUPPLIER_NOT_MAPPED": (
        "No supplier linked to this product."
    ),

    "PACKAGE_SIZE_MISSING": (
        "Package size unknown, "
        "so the number of units "
        "cannot be worked out."
    ),
}


def _order_line(
    packages: int | None,
    size: float | None,
    unit: str | None,
) -> str:
    """
    Render:
        2 × 700ml
    """

    if not packages:

        return "—"

    if size and unit:

        size_string = (
            f"{size:g}{unit}"
        )

        return (
            f"{packages} × "
            f"{size_string}"
        )

    if packages == 1:

        return (
            f"{packages} × unit"
        )

    return (
        f"{packages} × units"
    )


@router.get("/{event_id}/cost")
async def cost_summary(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return event cost summary."""

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    event_result = await db.execute(
        select(Event).where(
            Event.id == uid
        )
    )

    event = (
        event_result
        .scalar_one_or_none()
    )

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    items_result = await db.execute(
        select(
            EventPurchaseItem
        )
        .options(
            selectinload(
                EventPurchaseItem.ingredient
            )
        )
        .where(
            EventPurchaseItem.event_id == uid
        )
    )

    items = (
        items_result
        .scalars()
        .all()
    )

    if not items:

        raise HTTPException(
            status_code=404,
            detail=(
                "No cost data. "
                "Run /calculate first."
            ),
        )

    total_cost = round(
        sum(
            float(
                item.total_price
            )
            for item in items
            if item.total_price
            is not None
        ),
        2,
    )

    known_count = sum(
        1
        for item in items
        if item.total_price
        is not None
    )

    missing_count = sum(
        1
        for item in items
        if item.status != "OK"
    )

    budget = (
        float(event.budget)
        if event.budget is not None
        else None
    )

    variance = (
        budget - total_cost
        if budget is not None
        else None
    )

    by_category: dict[
        str,
        float,
    ] = {}

    for item in items:

        if item.total_price is None:
            continue

        category = (
            item.ingredient.category
            if item.ingredient
            else "other"
        )

        by_category[category] = (
            by_category.get(
                category,
                0.0,
            )
            + float(
                item.total_price
            )
        )

    return {
        "event_id": event_id,

        "guest_count": (
            event.guest_count
        ),

        "budget": budget,

        "total_cost": (
            total_cost
        ),

        "cost_per_guest": (
            round(
                total_cost
                / event.guest_count,
                2,
            )
            if event.guest_count
            else None
        ),

        "budget_variance": (
            round(
                variance,
                2,
            )
            if variance is not None
            else None
        ),

        "budget_status": (
            (
                "UNDER_BUDGET"
                if (
                    variance
                    and variance > 50
                )
                else (
                    "OVER_BUDGET"
                    if (
                        variance
                        and variance < -50
                    )
                    else "ON_BUDGET"
                )
            )
            if budget
            else None
        ),

        "items_with_data": (
            known_count
        ),

        "items_missing_data": (
            missing_count
        ),

        "cost_by_category": (
            by_category
        ),

        "is_partial": (
            missing_count > 0
        ),
    }


def _format_calc_result(
    result,
) -> dict:
    """
    Serialize calculation result.
    """

    return {
        "guests": (
            result.guests
        ),

        "drinks_per_guest": (
            result.drinks_per_guest
        ),

        "total_drinks": (
            result.total_drinks
        ),

        "alcoholic_drinks": (
            result.alcoholic_drinks
        ),

        "non_alcoholic_drinks": (
            result.non_alcoholic_drinks
        ),

        "cocktail_servings": (
            result.cocktail_servings
        ),

        "ingredient_requirements": [
            {
                "ingredient_id": (
                    requirement
                    .ingredient_id
                ),

                "canonical_name": (
                    requirement
                    .canonical_name
                ),

                "category": (
                    requirement.category
                ),

                "unit": (
                    requirement.unit
                ),

                "raw_amount": round(
                    requirement.raw_amount,
                    2,
                ),

                "required_amount": round(
                    requirement.required_amount,
                    2,
                ),
            }
            for requirement
            in result.ingredient_requirements
        ],

        "purchase_items": [
            {
                "ingredient_id": (
                    item.ingredient_id
                ),

                "canonical_name": (
                    item.canonical_name
                ),

                "category": (
                    item.category
                ),

                "product_name": (
                    item.product_name
                ),

                "required_amount": round(
                    item.required_amount,
                    2,
                ),

                "unit": item.unit,

                "package_size": (
                    item.package_size
                ),

                "package_unit": (
                    item.package_unit
                ),

                "packages_required": (
                    item.packages_required
                ),

                "unit_price": (
                    item.unit_price
                ),

                "total_price": (
                    item.total_price
                ),

                "status": (
                    item.status.value
                ),

                "supplier_name": (
                    item.supplier_name
                ),

                "product_url": (
                    item.product_url
                ),
            }
            for item
            in result.purchase_items
        ],

        "total_cost": (
            result.total_cost
        ),

        "cost_per_guest": (
            round(
                result.cost_per_guest,
                2,
            )
            if result.cost_per_guest
            else None
        ),

        "budget": (
            result.budget
        ),

        "budget_variance": (
            round(
                result.budget_variance,
                2,
            )
            if result.budget_variance
            is not None
            else None
        ),

        "budget_status": (
            result.budget_status.value
            if result.budget_status
            else None
        ),

        "has_missing_prices": (
            result.has_missing_prices
        ),

        "has_missing_mappings": (
            result.has_missing_mappings
        ),

        "cost_by_category": (
            result.cost_by_category
        ),

        "warnings": (
            result.warnings
        ),
    }


# ── Prep sheet ────────────────────────────────────────────────────────────────


@router.get("/{event_id}/prep-sheet")
async def get_prep_sheet(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Operational prep sheet for an event.

    Quantities come from the deterministic calculation engine.
    Sparkling/carbonated cocktails and Angostura cocktails are glass-only.
    """

    try:
        uid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    result = await db.execute(
        select(Event)
        .options(
            selectinload(Event.menu_items)
            .selectinload(EventMenuItem.cocktail)
        )
        .where(Event.id == uid)
    )

    event = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    if not event.menu_items:
        raise HTTPException(
            status_code=422,
            detail="This event has no menu yet.",
        )

    menu_allocs, recipes, ingredient_products = (
        await _build_engine_inputs(db, event)
    )

    calc = calculate_event(
        guests=event.guest_count,
        drinks_per_guest=float(
            event.expected_drinks_per_guest
        ),
        non_alcoholic_pct=float(
            event.non_alcoholic_pct
        ),
        waste_buffer_pct=float(
            event.waste_buffer_pct
        ),
        menu=menu_allocs,
        recipes=recipes,
        ingredient_products=ingredient_products,
        budget=(
            float(event.budget)
            if event.budget is not None
            else None
        ),
    )

    by_id = recipes
    cocktails = []

    no_batch_terms = (
        "soda",
        "sparkling",
        "prosecco",
        "cava",
        "champagne",
        "tonic",
        "ginger beer",
        "ginger ale",
        "sparkling water",
        "club soda",
        "carbonated",
        "cola",
        "sprite",
        "7up",
        "beer",
        "angostura",
    )

    for item in event.menu_items:
        cid = str(item.cocktail_id)

        recipe = by_id.get(cid)

        if recipe is None:
            continue

        servings = calc.cocktail_servings.get(
            cid,
            0,
        )

        c = item.cocktail

        # ----------------------------------------------------
        # Batch rules
        # ----------------------------------------------------

        batch_blocked_by = sorted({
            ing.canonical_name
            for ing in recipe.ingredients
            if any(
                term in ing.canonical_name.lower()
                for term in no_batch_terms
            )
        })

        batch_allowed = not batch_blocked_by

        if batch_allowed:
            batch_instruction = (
                "Take a container and pour in all the ingredients. "
                "Add ice to the container just before the event."
            )
        else:
            batch_instruction = (
                "This cocktail cannot be prepared as a batch. "
                "Prepare it only in the glass."
            )

        # ----------------------------------------------------
        # Ingredient quantities
        # ----------------------------------------------------

        ingredient_lines = []

        for ing in recipe.ingredients:
            if ing.amount is None:
                ingredient_lines.append({
                    "name": ing.canonical_name,
                    "per_drink": None,
                    "unit": ing.unit,
                    "batch_total": None,
                    "bottles": None,
                    "note": "to taste / top up",
                })

                continue

            amount_total = round(
                ing.amount * servings,
                1,
            )

            mapped = ingredient_products.get(
                ing.ingredient_id
            )

            product = (
                getattr(mapped, "product", None)
                if mapped
                else None
            )

            size = (
                getattr(
                    product,
                    "package_size",
                    None,
                )
                if product
                else None
            )

            bottles = None

            if (
                size
                and float(size) > 0
                and ing.unit == "ml"
            ):
                bottles = round(
                    amount_total / float(size),
                    2,
                )

            ingredient_lines.append({
                "name": ing.canonical_name,
                "per_drink": ing.amount,
                "unit": ing.unit,
                "batch_total": amount_total,
                "bottles": bottles,
                "bottle_size_ml": (
                    float(size)
                    if size
                    else None
                ),
                "note": None,
            })

        cocktails.append({
            "cocktail_id": cid,
            "name": (
                c.name
                if c
                else recipe.name
            ),
            "servings": servings,

            # Requested standard glass.
            "glass": "כוס משרד",

            # Operational English instruction.
            # Original per-glass preparation method from the cocktail DB.
            "technique": getattr(c, "technique", None),
            "glass_instruction": getattr(c, "technique", None),

            "batch_allowed": batch_allowed,
            "batch_blocked_by": batch_blocked_by,
            "batch_instruction": batch_instruction,

            "garnish": getattr(
                c,
                "garnish",
                None,
            ),
            "non_alc_variant": getattr(
                c,
                "non_alc_variant",
                None,
            ),
            "ingredients": ingredient_lines,
        })

    return {
        "event_id": str(event.id),
        "event_name": event.name,
        "guests": event.guest_count,
        "duration_hours": float(
            event.duration_hours
        ),
        "total_drinks": calc.total_drinks,
        "cocktails": cocktails,
    }


# ── Event-scoped product alternatives ─────────────────────────────────────────


async def _recalculate(
    event_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    Re-run the engine after product changes.
    """

    await calculate(
        str(event_id),
        db,
    )


async def _substitutable_ingredient_ids(
    ingredient_id: uuid.UUID,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """
    Ingredients in the same substitute group.
    """

    ingredient = (
        await db.execute(
            select(
                Ingredient
            ).where(
                Ingredient.id
                == ingredient_id
            )
        )
    ).scalar_one_or_none()

    if (
        ingredient is None
        or not ingredient.substitute_group
    ):

        return [
            ingredient_id
        ]

    ids = (
        await db.execute(
            select(
                Ingredient.id
            ).where(
                Ingredient.substitute_group
                == ingredient.substitute_group
            )
        )
    ).scalars().all()

    return (
        list(ids)
        or [ingredient_id]
    )


async def _alternatives_for(
    event: Event,
    ingredient_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Product alternatives for one ingredient.

    Ranking is by total event cost,
    not shelf price.
    """

    item = (
        await db.execute(
            select(
                EventPurchaseItem
            ).where(
                EventPurchaseItem.event_id
                == event.id,

                EventPurchaseItem.ingredient_id
                == ingredient_id,
            )
        )
    ).scalars().first()

    if item is None:

        raise HTTPException(
            status_code=422,
            detail=(
                "This ingredient is not "
                "in the event's purchase list. "
                "Calculate the event first."
            ),
        )

    ingredient = (
        await db.execute(
            select(
                Ingredient
            ).where(
                Ingredient.id
                == ingredient_id
            )
        )
    ).scalar_one_or_none()

    override = (
        await db.execute(
            select(
                EventIngredientProductOverride
            ).where(
                EventIngredientProductOverride
                .event_id
                == event.id,

                EventIngredientProductOverride
                .ingredient_id
                == ingredient_id,
            )
        )
    ).scalars().first()

    family = (
        await _substitutable_ingredient_ids(
            ingredient_id,
            db,
        )
    )

    rows = (
        await db.execute(
            select(
                Product,
                SupplierProduct,
                IngredientProductMapping,
            )
            .join(
                IngredientProductMapping,
                IngredientProductMapping.product_id
                == Product.id,
            )
            .join(
                SupplierProduct,
                SupplierProduct.product_id
                == Product.id,
            )
            .options(
                selectinload(
                    SupplierProduct.supplier
                )
            )
            .where(
                IngredientProductMapping
                .ingredient_id
                .in_(family),

                SupplierProduct
                .price_after_vat
                .isnot(None),

                SupplierProduct.available
                == True,
            )
        )
    ).all()

    need = float(
        item.required_amount
    )

    current_total = (
        float(
            item.total_price
        )
        if item.total_price
        is not None
        else None
    )

    current_product_id = (
        str(item.product_id)
        if item.product_id
        else None
    )

    best: dict[
        str,
        tuple,
    ] = {}

    for (
        product,
        listing,
        mapping,
    ) in rows:

        # Supplier-specific package wins.
        size = (
            float(
                listing.package_size
            )
            if listing.package_size
            is not None
            else (
                float(
                    product.package_size
                )
                if product.package_size
                is not None
                else None
            )
        )

        if (
            not size
            or size <= 0
        ):

            continue

        price = float(
            listing.price_after_vat
        )

        key = str(
            product.id
        )

        # Best package for THIS EVENT,
        # not merely cheapest shelf price.
        packages = math.ceil(
            need / size
        )

        event_total = round(
            packages * price,
            2,
        )

        previous = best.get(
            key
        )

        if (
            previous is None
            or event_total
            < previous[1]
        ):

            best[key] = (
                product,
                event_total,
                price,
                size,
                listing,
                mapping,
                packages,
            )

    options = []

    for (
        product,
        event_total,
        price,
        size,
        listing,
        mapping,
        packages,
    ) in best.values():

        options.append(
            {
                "product_id": str(
                    product.id
                ),

                "product_name": (
                    product.brand
                    or product.name
                ),

                "hebrew_name": (
                    product.name
                ),

                "package_size": (
                    size
                ),

                "package_unit": (
                    listing.package_unit
                    or product.package_unit
                    or "ml"
                ),

                "price_per_package": (
                    price
                ),

                "packages_required": (
                    packages
                ),

                "event_total": (
                    event_total
                ),

                "difference_vs_current": (
                    round(
                        event_total
                        - current_total,
                        2,
                    )
                    if current_total
                    is not None
                    else None
                ),

                "is_current": (
                    str(product.id)
                    == current_product_id
                ),

                "is_house_recommendation": bool(
                    mapping.preferred
                ),

                "supplier_name": (
                    listing.supplier.name
                    if listing.supplier
                    else None
                ),
            }
        )

    options.sort(
        key=lambda option: (
            option["event_total"]
        )
    )

    return {
        "event_id": str(
            event.id
        ),

        "ingredient_id": str(
            ingredient_id
        ),

        "ingredient_name": (
            ingredient.canonical_name
            if ingredient
            else None
        ),

        "required_amount": round(
            need,
            1,
        ),

        "required_unit": (
            item.required_unit
        ),

        "current_total": (
            current_total
        ),

        "current_product_id": (
            current_product_id
        ),

        "is_overridden": (
            override is not None
        ),

        "options": options,

        "note": (
            "Compare event_total, not "
            "price_per_package: a cheaper "
            "bottle in a smaller size can "
            "cost more once whole packages "
            "are counted."
        ),
    }


@router.get(
    "/{event_id}/ingredients/"
    "{ingredient_id}/alternatives"
)
async def list_ingredient_alternatives(
    event_id: str,
    ingredient_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Alternative products for ingredient.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

        iid = uuid.UUID(
            ingredient_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid ID",
        )

    event = (
        await db.execute(
            select(
                Event
            ).where(
                Event.id == uid
            )
        )
    ).scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    return await _alternatives_for(
        event,
        iid,
        db,
    )


class ProductOverrideIn(BaseModel):
    product_id: str
    reason: str | None = None


@router.put(
    "/{event_id}/ingredients/"
    "{ingredient_id}/product"
)
async def set_event_product(
    event_id: str,
    ingredient_id: str,
    body: ProductOverrideIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Choose product for this event only.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

        iid = uuid.UUID(
            ingredient_id
        )

        pid = uuid.UUID(
            body.product_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid ID",
        )

    event = (
        await db.execute(
            select(Event).where(
                Event.id == uid
            )
        )
    ).scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    family = (
        await _substitutable_ingredient_ids(
            iid,
            db,
        )
    )

    allowed = (
        await db.execute(
            select(
                IngredientProductMapping
            ).where(
                IngredientProductMapping
                .ingredient_id
                .in_(family),

                IngredientProductMapping
                .product_id
                == pid,
            )
        )
    ).scalars().first()

    if allowed is None:

        raise HTTPException(
            status_code=422,
            detail=(
                "That product is not "
                "a listed option for "
                "this ingredient."
            ),
        )

    existing = (
        await db.execute(
            select(
                EventIngredientProductOverride
            ).where(
                EventIngredientProductOverride
                .event_id
                == uid,

                EventIngredientProductOverride
                .ingredient_id
                == iid,
            )
        )
    ).scalars().first()

    if existing:

        existing.product_id = (
            pid
        )

        existing.reason = (
            body.reason
        )

    else:

        db.add(
            EventIngredientProductOverride(
                event_id=uid,
                ingredient_id=iid,
                product_id=pid,
                reason=body.reason,
            )
        )

    await db.commit()

    await _recalculate(
        uid,
        db,
    )

    return await _alternatives_for(
        event,
        iid,
        db,
    )


@router.delete(
    "/{event_id}/ingredients/"
    "{ingredient_id}/product"
)
async def clear_event_product(
    event_id: str,
    ingredient_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return to house recommendation.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

        iid = uuid.UUID(
            ingredient_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid ID",
        )

    event = (
        await db.execute(
            select(
                Event
            ).where(
                Event.id == uid
            )
        )
    ).scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    existing = (
        await db.execute(
            select(
                EventIngredientProductOverride
            ).where(
                EventIngredientProductOverride
                .event_id
                == uid,

                EventIngredientProductOverride
                .ingredient_id
                == iid,
            )
        )
    ).scalars().first()

    if existing:

        await db.delete(
            existing
        )

        await db.commit()

        await _recalculate(
            uid,
            db,
        )

    return await _alternatives_for(
        event,
        iid,
        db,
    )


@router.get("/{event_id}/overrides")
async def list_event_overrides(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Event-specific product overrides.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    rows = (
        await db.execute(
            select(
                EventIngredientProductOverride,
                Ingredient,
                Product,
            )
            .join(
                Ingredient,
                Ingredient.id
                == EventIngredientProductOverride
                .ingredient_id,
            )
            .join(
                Product,
                Product.id
                == EventIngredientProductOverride
                .product_id,
            )
            .where(
                EventIngredientProductOverride
                .event_id
                == uid
            )
        )
    ).all()

    return {
        "event_id": event_id,

        "count": len(rows),

        "overrides": [
            {
                "ingredient_id": str(
                    override.ingredient_id
                ),

                "ingredient_name": (
                    ingredient
                    .canonical_name
                ),

                "product_id": str(
                    override.product_id
                ),

                "product_name": (
                    product.brand
                    or product.name
                ),

                "reason": (
                    override.reason
                ),
            }
            for (
                override,
                ingredient,
                product,
            ) in rows
        ],
    }


# ── Batch builder ─────────────────────────────────────────────────────────────


@router.get(
    "/{event_id}/cocktails/"
    "{cocktail_id}/batch"
)
async def build_batch(
    event_id: str,
    cocktail_id: str,
    servings: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    Scale one cocktail to N servings.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

        cid = uuid.UUID(
            cocktail_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid ID",
        )

    if servings <= 0:

        raise HTTPException(
            status_code=422,
            detail=(
                "servings must be "
                "a positive whole number"
            ),
        )

    result = await db.execute(
        select(Event)
        .options(
            selectinload(
                Event.menu_items
            )
        )
        .where(
            Event.id == uid
        )
    )

    event = result.scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    (
        _menu,
        recipes,
        ingredient_products,
    ) = await _build_engine_inputs(
        db,
        event,
    )

    recipe = recipes.get(
        str(cid)
    )

    if recipe is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "That cocktail is not "
                "on this event's menu."
            ),
        )

    products = {
        ingredient_id: (
            ingredient_with_product
            .product
        )
        for (
            ingredient_id,
            ingredient_with_product,
        ) in ingredient_products.items()
        if (
            ingredient_with_product
            .product
            is not None
        )
    }

    return batch_to_dict(
        scale_recipe(
            recipe,
            servings,
            products,
        )
    )


# ── Event conversation ────────────────────────────────────────────────────────


@router.get("/{event_id}/messages")
async def list_event_messages(
    event_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    Event conversation.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    rows = (
        await db.execute(
            select(
                EventMessage
            )
            .where(
                EventMessage.event_id
                == uid
            )
            .order_by(
                EventMessage
                .created_at
                .desc()
            )
            .limit(limit)
        )
    ).scalars().all()

    rows = list(
        reversed(rows)
    )

    return {
        "event_id": event_id,

        "count": len(rows),

        "messages": [
            {
                "role": message.role,

                "content": (
                    message.content
                ),

                "tab": message.tab,

                "created_at": (
                    message
                    .created_at
                    .isoformat()
                    if message.created_at
                    else None
                ),
            }
            for message in rows
        ],
    }


@router.delete("/{event_id}/messages")
async def clear_event_messages(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Clear event conversation.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    rows = (
        await db.execute(
            select(
                EventMessage
            ).where(
                EventMessage.event_id
                == uid
            )
        )
    ).scalars().all()

    for message in rows:

        await db.delete(
            message
        )

    await db.commit()

    return {
        "event_id": event_id,
        "cleared": len(rows),
    }


# ── Basket comparison ─────────────────────────────────────────────────────────


@router.get("/{event_id}/compare-shops")
async def compare_shops(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Compare whole-event baskets between shops.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    event = (
        await db.execute(
            select(Event).where(
                Event.id == uid
            )
        )
    ).scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    items = (
        await db.execute(
            select(
                EventPurchaseItem
            )
            .options(
                selectinload(
                    EventPurchaseItem
                    .ingredient
                )
            )
            .where(
                EventPurchaseItem
                .event_id
                == uid
            )
        )
    ).scalars().all()

    if not items:

        raise HTTPException(
            status_code=422,
            detail=(
                "Calculate the event first."
            ),
        )

    # Compare Shops is intentionally ALCOHOL ONLY.
    alcohol_items = [
        item
        for item in items
        if (
            item.ingredient is not None
            and bool(item.ingredient.alcoholic)
        )
    ]

    other_items = [
        item
        for item in items
        if not (
            item.ingredient is not None
            and bool(item.ingredient.alcoholic)
        )
    ]

    def supply_channel(item):
        ingredient = item.ingredient

        if ingredient is None:
            return "other"

        category = str(
            ingredient.category or ""
        ).lower()

        name = ingredient.canonical_name

        if category == "syrup":
            return "house_made"

        if name == "Espresso Shot":
            return "house_made"

        if category == "juice":
            return "juice_supplier"

        if category == "garnish":
            return "supermarket"

        if category == "mixer":
            return "supermarket_or_beverage_supplier"

        if name in {
            "Olive Brine",
            "Foamer (Aquafaba/Egg White)",
        }:
            return "supermarket"

        return "other"

    other_supplies = [
        {
            "ingredient_id": str(item.ingredient_id),
            "ingredient": (
                item.ingredient.canonical_name
                if item.ingredient
                else "?"
            ),
            "category": (
                item.ingredient.category
                if item.ingredient
                else None
            ),
            "channel": supply_channel(item),
            "required_amount": float(
                item.required_amount
            ),
            "unit": item.required_unit,
            "packages_required": item.packages_required,
            "package_size": (
                float(item.package_size)
                if item.package_size is not None
                else None
            ),
            "package_unit": item.package_unit,
            "estimated_total": (
                float(item.total_price)
                if item.total_price is not None
                else None
            ),
            "status": item.status,
            "product_url": item.product_url,
        }
        for item in other_items
    ]

    ingredient_ids = [
        item.ingredient_id
        for item in alcohol_items
    ]

    slot_of: dict[
        str,
        str,
    ] = {}

    widened: list[
        uuid.UUID
    ] = []

    for ingredient_id in (
        ingredient_ids
    ):

        family = (
            await _substitutable_ingredient_ids(
                ingredient_id,
                db,
            )
        )

        for member in family:

            slot_of[
                str(member)
            ] = str(
                ingredient_id
            )

            widened.append(
                member
            )

    rows = (
        await db.execute(
            select(
                Supplier,
                Product,
                SupplierProduct,
                IngredientProductMapping,
            )
            .join(
                IngredientProductMapping,
                IngredientProductMapping
                .product_id
                == Product.id,
            )
            .join(
                SupplierProduct,
                SupplierProduct
                .product_id
                == Product.id,
            )
            .join(
                Supplier,
                Supplier.id
                == SupplierProduct
                .supplier_id,
            )
            .where(
                IngredientProductMapping
                .ingredient_id
                .in_(widened),

                SupplierProduct
                .price_after_vat
                .isnot(None),

                SupplierProduct.available
                == True,

                Supplier.is_retailer
                == True,
            )
        )
    ).all()

    need = {
        str(item.ingredient_id): float(
            item.required_amount
        )
        for item in alcohol_items
    }

    name_of = {
        str(item.ingredient_id): (
            item.ingredient.canonical_name
            if item.ingredient
            else "?"
        )
        for item in alcohol_items
    }

    category_of = {
        str(item.ingredient_id): str(
            item.ingredient.category
        ).lower()
        if item.ingredient
        else None
        for item in alcohol_items
    }

    by_shop: dict[
        str,
        dict,
    ] = {}

    best_anywhere: dict[
        str,
        tuple,
    ] = {}

    for (
        supplier,
        product,
        listing,
        mapping,
    ) in rows:

        ingredient_id = (
            slot_of.get(
                str(
                    mapping.ingredient_id
                )
            )
        )

        if (
            ingredient_id is None
            or ingredient_id
            not in need
        ):

            continue

        size = float(
            listing.package_size
            or product.package_size
            or 0
        )

        if size <= 0:

            continue

        price = float(
            listing.price_after_vat
        )

        packages = math.ceil(
            need[ingredient_id]
            / size
        )

        total = round(
            packages
            * price,
            2,
        )

        shop = by_shop.setdefault(
            supplier.name,
            {
                "shop": (
                    supplier.name
                ),

                "website": (
                    supplier.website
                ),

                "free_delivery_over": (
                    float(
                        supplier
                        .free_delivery_over
                    )
                    if (
                        supplier
                        .free_delivery_over
                        is not None
                    )
                    else None
                ),

                "delivery_fee": (
                    float(
                        supplier
                        .delivery_fee
                    )
                    if (
                        supplier
                        .delivery_fee
                        is not None
                    )
                    else None
                ),

                "minimum_order": (
                    float(
                        supplier
                        .minimum_order
                    )
                    if (
                        supplier
                        .minimum_order
                        is not None
                    )
                    else None
                ),

                "delivery_note": (
                    supplier.delivery_note
                ),

                "lines": {},
            },
        )

        previous = (
            shop["lines"].get(
                ingredient_id
            )
        )

        if (
            previous is None
            or total
            < previous[
                "event_total"
            ]
        ):

            shop["lines"][
                ingredient_id
            ] = {
                "ingredient_id": (
                    ingredient_id
                ),

                "ingredient": (
                    name_of[
                        ingredient_id
                    ]
                ),

                "product": (
                    product.brand
                    or product.name
                ),

                "package_size": (
                    size
                ),

                "package_unit": (
                    listing.package_unit
                    or product.package_unit
                    or "ml"
                ),

                "price_per_package": (
                    price
                ),

                "packages": (
                    packages
                ),

                "event_total": (
                    total
                ),

                "url": (
                    listing.product_url
                ),
            }

        if (
            ingredient_id
            not in best_anywhere
            or total
            < best_anywhere[
                ingredient_id
            ][1]
        ):

            best_anywhere[
                ingredient_id
            ] = (
                supplier.name,
                total,
                shop["lines"][
                    ingredient_id
                ],
            )

    shops = []

    for (
        name,
        shop,
    ) in by_shop.items():

        lines = list(
            shop["lines"].values()
        )

        subtotal = round(
            sum(
                line[
                    "event_total"
                ]
                for line in lines
            ),
            2,
        )

        missing = [
            name_of[
                ingredient_id
            ]
            for ingredient_id
            in need
            if ingredient_id
            not in shop["lines"]
        ]

        bottles = sum(
            line["packages"]
            for line in lines
        )

        free_over = (
            shop[
                "free_delivery_over"
            ]
        )

        fee = (
            shop[
                "delivery_fee"
            ]
        )
        clears = free_over is not None and subtotal >= free_over

        unpublished = bool(
            shop["delivery_note"]
            and (
                "NOT published"
                in shop[
                    "delivery_note"
                ]
                or (
                    "not published"
                    in shop[
                        "delivery_note"
                    ]
                )
            )
        )

        if clears and not unpublished:
            delivery, delivery_known = 0.0, True
        elif not clears and fee is not None and not unpublished:
            delivery, delivery_known = fee, True
        else:
            delivery, delivery_known = None, False

        minimum = (
            shop[
                "minimum_order"
            ]
        )

        below_minimum = (
            minimum is not None
            and subtotal < minimum
        )

        short_by = (
            round(
                minimum - subtotal,
                2,
            )
            if below_minimum
            else None
        )

        shops.append(
            {
                "shop": name,

                "website": (
                    shop["website"]
                ),

                "covers": len(
                    lines
                ),

                "of": len(
                    need
                ),

                "missing": (
                    missing
                ),

                "subtotal": (
                    subtotal
                ),

                "bottles": (
                    bottles
                ),

                "free_delivery_over": (
                    free_over
                ),

                "delivery_fee": (
                    fee
                ),

                "minimum_order": (
                    minimum
                ),
                "below_minimum": below_minimum,

                "short_of_minimum_by": (
                    short_by
                ),

                "delivery_note": (
                    shop[
                        "delivery_note"
                    ]
                ),

                "clears_free_delivery": (
                    clears
                ),

                "delivery": (
                    delivery
                ),

                "delivered_total": (
                    round(
                        subtotal
                        + delivery,
                        2,
                    )
                    if delivery_known
                    else None
                ),

                "delivered_total_unknown_because": (
                    None
                    if delivery_known
                    else (
                        "This shop does not "
                        "publish what delivery "
                        "costs for an order this "
                        "size. The product "
                        "subtotal above is exact; "
                        "the delivered total is "
                        "not knowable from "
                        "published terms."
                    )
                ),

                "lines": sorted(
                    lines,
                    key=lambda line: -(
                        line[
                            "event_total"
                        ]
                    ),
                ),
            }
        )

    shops.sort(
        key=lambda shop: (
            -shop["covers"],
            shop["subtotal"],
        )
    )

    split_total = round(
        sum(
            value[1]
            for value
            in best_anywhere.values()
        ),
        2,
    )

    split_shops = sorted(
        {
            value[0]
            for value
            in best_anywhere.values()
        }
    )

    split_leg_total: dict[
        str,
        float,
    ] = {}

    for (
        shop_name,
        total,
        _line,
    ) in best_anywhere.values():

        split_leg_total[
            shop_name
        ] = round(
            split_leg_total.get(
                shop_name,
                0.0,
            )
            + total,
            2,
        )

    split_below_minimum = [
        {
            "shop": (
                shop_name
            ),

            "leg_total": (
                leg
            ),

            "minimum_order": (
                by_shop[
                    shop_name
                ][
                    "minimum_order"
                ]
            ),

            "short_by": round(
                by_shop[
                    shop_name
                ][
                    "minimum_order"
                ]
                - leg,
                2,
            ),
        }

        for (
            shop_name,
            leg,
        ) in sorted(
            split_leg_total.items()
        )

        if (
            by_shop[
                shop_name
            ][
                "minimum_order"
            ]
            is not None

            and leg
            < by_shop[
                shop_name
            ][
                "minimum_order"
            ]
        )
    ]

    best_single = (
        shops[0]
        if shops
        else None
    )

    best_covers = (
        best_single[
            "covers"
        ]
        if best_single
        else 0
    )

    return {
        "comparison_scope": "alcohol_only",
        "other_supplies": other_supplies,
        "event_id": (
            event_id
        ),

        "ingredients": len(
            need
        ),

        "shops": shops,

        "split": {
            "total": (
                split_total
            ),

            "shop_count": len(
                split_shops
            ),

            "shops": (
                split_shops
            ),

            "covers": len(
                best_anywhere
            ),

            "of": len(
                need
            ),

            "saving_vs_best_single": (
                round(
                    best_single[
                        "subtotal"
                    ]
                    - split_total,
                    2,
                )
                if (
                    best_single
                    and best_covers
                    == len(
                        best_anywhere
                    )
                )
                else None
            ),

            "comparable": bool(
                best_single
                and best_covers
                == len(
                    best_anywhere
                )
            ),

            "best_single_shop": (
                best_single[
                    "shop"
                ]
                if best_single
                else None
            ),

            "best_single_covers": (
                best_covers
            ),

            "leg_totals": (
                split_leg_total
            ),

            "below_minimum": split_below_minimum,

            "note": (
                "Product subtotals only. "
                "Each shop adds its own "
                "delivery, so a split "
                "across several shops "
                "pays several times."
            ),
        },

        "fully_covered_by_any_shop": any(
            shop["covers"]
            == len(need)
            for shop in shops
        ),

        "note": (
            "Compare subtotals, which are "
            "exact. Delivered totals are "
            "shown only where the shop "
            "publishes terms that cover "
            "an order this size. Shops "
            "are ranked by how much of "
            "the event they can supply "
            "first, then by price."
        ),
    }



@router.get("/{event_id}/equipment-shop")
async def get_equipment_shop(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Cocktail/bar equipment available to buy.

    This is deliberately NOT a workshop calculator.
    It is simply the equipment catalogue already stored in the database,
    grouped by tool, with real supplier listings and prices.
    """

    try:
        uid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    event = (
        await db.execute(
            select(Event).where(Event.id == uid)
        )
    ).scalar_one_or_none()

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    rows = (
        await db.execute(
            select(
                Ingredient,
                Product,
                SupplierProduct,
                Supplier,
            )
            .join(
                IngredientProductMapping,
                IngredientProductMapping.ingredient_id
                == Ingredient.id,
            )
            .join(
                Product,
                Product.id
                == IngredientProductMapping.product_id,
            )
            .join(
                SupplierProduct,
                SupplierProduct.product_id
                == Product.id,
            )
            .join(
                Supplier,
                Supplier.id
                == SupplierProduct.supplier_id,
            )
            .where(
                Ingredient.canonical_name.like(
                    "equipment:%"
                ),
                SupplierProduct.price_after_vat.isnot(
                    None
                ),
                Supplier.active == True,  # noqa: E712
                Product.active == True,  # noqa: E712
            )
        )
    ).all()

    labels = {
        "shaker": "Shaker",
        "jigger": "Jigger",
        "strainer": "Strainer",
        "fine_strainer": "Fine strainer",
        "bar_spoon": "Bar spoon",
        "muddler": "Muddler",
        "ice_scoop": "Ice scoop",
        "pourer": "Bottle pourer",
        "glass": "Glassware",
        "glassware": "Glassware",
    }

    groups = {}
    seen = set()

    for ingredient, product, listing, supplier in rows:
        raw_key = ingredient.canonical_name.split(
            "equipment:",
            1,
        )[1]

        key = raw_key.split("_alt_", 1)[0]

        package_size = float(
            listing.package_size
            or product.package_size
            or 1
        )

        package_unit = (
            listing.package_unit
            or product.package_unit
            or "unit"
        )

        price = float(listing.price_after_vat)

        dedupe = (
            key,
            str(product.id),
            str(supplier.id),
            package_size,
            price,
        )

        if dedupe in seen:
            continue

        seen.add(dedupe)

        group = groups.setdefault(
            key,
            {
                "key": key,
                "name": labels.get(
                    key,
                    key.replace("_", " ").title(),
                ),
                "options": [],
            },
        )

        group["options"].append(
            {
                "product_id": str(product.id),
                "product": product.name,
                "supplier": supplier.name,
                "supplier_website": supplier.website,
                "price": round(price, 2),
                "package_size": package_size,
                "package_unit": package_unit,
                "available": bool(listing.available),
                "url": (
                    listing.product_url
                    or (
                        supplier.search_url_template.replace(
                            "{query}",
                            quote_plus(product.name),
                        )
                        if supplier.search_url_template
                        else None
                    )
                    or supplier.website
                ),
            }
        )

    output = []

    for group in groups.values():
        group["options"].sort(
            key=lambda x: (
                not x["available"],
                x["price"],
                x["supplier"],
            )
        )

        output.append(group)

    output.sort(
        key=lambda x: x["name"].lower()
    )

    return {
        "event_id": event_id,
        "groups": output,
        "total_categories": len(output),
        "note": (
            "Cocktail equipment catalogue. "
            "Prices are per listed pack."
        ),
    }



# ── Workshop equipment ────────────────────────────────────────────────────────


class WorkshopSettings(BaseModel):
    is_workshop: bool | None = None
    people_per_station: int | None = None


@router.put("/{event_id}/workshop")
async def set_workshop(
    event_id: str,
    body: WorkshopSettings,
    db: AsyncSession = Depends(get_db),
):
    """
    Set workshop mode.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    event = (
        await db.execute(
            select(
                Event
            ).where(
                Event.id == uid
            )
        )
    ).scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    if body.is_workshop is not None:

        event.is_workshop = (
            body.is_workshop
        )

    if (
        body.people_per_station
        is not None
    ):

        if (
            body.people_per_station
            < 1
        ):

            raise HTTPException(
                status_code=422,
                detail=(
                    "At least one person "
                    "per station."
                ),
            )

        event.people_per_station = (
            body.people_per_station
        )

    await db.commit()

    return {
        "event_id": (
            event_id
        ),

        "is_workshop": (
            event.is_workshop
        ),

        "people_per_station": (
            event.people_per_station
        ),
    }


@router.get("/{event_id}/equipment")
async def get_equipment(
    event_id: str,
    people_per_station: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Workshop equipment calculator.
    """

    try:

        uid = uuid.UUID(
            event_id
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid event ID",
        )

    event = (
        await db.execute(
            select(Event).where(
                Event.id == uid
            )
        )
    ).scalar_one_or_none()

    if event is None:

        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    ratio = (
        people_per_station
        or event.people_per_station
        or 2
    )

    if ratio < 1:

        raise HTTPException(
            status_code=422,
            detail=(
                "At least one person "
                "per station."
            ),
        )

    rows = (
        await db.execute(
            select(
                Ingredient,
                Product,
                SupplierProduct,
                Supplier,
            )
            .join(
                IngredientProductMapping,
                IngredientProductMapping
                .ingredient_id
                == Ingredient.id,
            )
            .join(
                Product,
                Product.id
                == IngredientProductMapping
                .product_id,
            )
            .join(
                SupplierProduct,
                SupplierProduct
                .product_id
                == Product.id,
            )
            .join(
                Supplier,
                Supplier.id
                == SupplierProduct
                .supplier_id,
            )
            .where(
                Ingredient
                .canonical_name
                .like(
                    "equipment:%"
                ),

                SupplierProduct
                .price_after_vat
                .isnot(None),
            )
        )
    ).all()

    prices: dict[
        str,
        EquipmentPrice,
    ] = {}

    alternatives: list[
        dict
    ] = []

    for (
        ingredient,
        product,
        listing,
        supplier,
    ) in rows:

        key = (
            ingredient
            .canonical_name
            .split(
                "equipment:",
                1,
            )[1]
        )

        package = int(
            float(
                listing.package_size
                or product.package_size
                or 1
            )
        )

        entry = EquipmentPrice(
            product_name=(
                product.name
            ),

            price_per_pack=float(
                listing.price_after_vat
            ),

            pack_size=package,

            supplier=(
                supplier.name
            ),

            in_stock=bool(
                listing.available
            ),

            url=(
                listing.product_url
            ),
        )

        if "_alt_" in key:

            base = (
                key.split(
                    "_alt_"
                )[0]
            )

            alternatives.append(
                {
                    "for": base,

                    "product": (
                        product.name
                    ),

                    "price": (
                        entry
                        .price_per_pack
                    ),

                    "in_stock": (
                        entry.in_stock
                    ),

                    "supplier": (
                        supplier.name
                    ),

                    "url": (
                        entry.url
                    ),
                }
            )

            continue

        previous = (
            prices.get(
                key
            )
        )

        if (
            previous is None
            or (
                entry.in_stock,
                -entry.price_per_pack,
            )
            >
            (
                previous.in_stock,
                -previous.price_per_pack,
            )
        ):

            prices[key] = (
                entry
            )

    plan = plan_equipment(
        participants=(
            event.guest_count
        ),

        people_per_station=(
            ratio
        ),

        prices=prices,
    )

    output = plan_to_dict(
        plan
    )

    output["event_id"] = (
        event_id
    )

    output["is_workshop"] = (
        event.is_workshop
    )

    output[
        "saved_people_per_station"
    ] = (
        event.people_per_station
    )

    output["alternatives"] = (
        alternatives
    )

    output["note"] = (
        "Tools are counted per station, "
        "glassware per participant. "
        "Glassware is sold in packs, "
        "so the number bought is usually "
        "more than the number needed."
    )

    return output

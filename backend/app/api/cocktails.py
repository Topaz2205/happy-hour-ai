"""
Cocktails API — read-only endpoints for the cocktail menu.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
import uuid

from app.db.session import get_db
from app.models import Cocktail, CocktailIngredient, Ingredient

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────

class IngredientOut(BaseModel):
    ingredient_id: str
    canonical_name: str
    category: str
    amount: Optional[float]
    unit: str
    alcoholic: bool
    optional: bool

    class Config:
        from_attributes = True


class CocktailListItem(BaseModel):
    id: str
    name: str
    description: Optional[str]
    alcoholic: bool
    theme: Optional[str]
    complexity: Optional[str]
    glass_type: Optional[str]
    technique: Optional[str]
    active: bool

    class Config:
        from_attributes = True


class CocktailDetail(CocktailListItem):
    garnish: Optional[str]
    comments: Optional[str]
    non_alc_variant: Optional[str]
    ingredients: list[IngredientOut]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def list_cocktails(
    theme: Optional[str] = None,
    alcoholic: Optional[bool] = None,
    search: Optional[str] = None,
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List cocktails with optional filters."""
    # Ingredients come along for the ride.
    #
    # A name like "Sbagliato" or "Jasmine" tells someone choosing a menu
    # nothing at all, and the picker was asking people to select drinks they
    # could not identify. selectinload keeps it to one extra query rather than
    # one per cocktail — the reason this is here and not a lookup per row in
    # the browser.
    q = select(Cocktail).options(
        selectinload(Cocktail.ingredients).selectinload(CocktailIngredient.ingredient)
    )

    if active_only:
        q = q.where(Cocktail.active == True)
    if theme:
        q = q.where(Cocktail.theme == theme)
    if alcoholic is not None:
        q = q.where(Cocktail.alcoholic == alcoholic)
    if search:
        q = q.where(Cocktail.name.ilike(f"%{search}%"))

    # Count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginate
    q = q.order_by(Cocktail.theme, Cocktail.name)
    q = q.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(q)
    cocktails = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "alcoholic": c.alcoholic,
                "theme": c.theme,
                "complexity": c.complexity,
                "glass_type": c.glass_type,
                "technique": c.technique,
                "active": c.active,
                # Names only, in recipe order — base spirit first.
                #
                # Deliberately NOT called `ingredients`: the detail endpoint
                # already uses that for measured lines with amounts and units,
                # and one name for two shapes is how a type stops meaning
                # anything. This is the short "what is in it" for a picker.
                "ingredient_names": [
                    ci.ingredient.canonical_name
                    for ci in sorted(c.ingredients, key=lambda x: x.sort_order or 0)
                    if ci.ingredient is not None
                ],
            }
            for c in cocktails
        ],
    }


@router.get("/themes")
async def get_themes(db: AsyncSession = Depends(get_db)):
    """Return unique themes."""
    result = await db.execute(
        select(Cocktail.theme).distinct().where(Cocktail.active == True)
    )
    return {"themes": [r[0] for r in result.all() if r[0]]}


@router.get("/{cocktail_id}")
async def get_cocktail(cocktail_id: str, db: AsyncSession = Depends(get_db)):
    """Get a cocktail with full ingredient list."""
    try:
        uid = uuid.UUID(cocktail_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid cocktail ID")

    result = await db.execute(
        select(Cocktail)
        .options(
            selectinload(Cocktail.ingredients).selectinload(CocktailIngredient.ingredient)
        )
        .where(Cocktail.id == uid)
    )
    cocktail = result.scalar_one_or_none()
    if cocktail is None:
        raise HTTPException(status_code=404, detail="Cocktail not found")

    ingredients = []
    for ci in sorted(cocktail.ingredients, key=lambda x: x.sort_order or 0):
        ing = ci.ingredient
        ingredients.append({
            "ingredient_id": str(ing.id),
            "canonical_name": ing.canonical_name,
            "category": ing.category,
            "amount": float(ci.amount) if ci.amount is not None else None,
            "unit": ci.unit,
            "alcoholic": ing.alcoholic,
            "optional": ci.optional or False,
        })

    return {
        "id": str(cocktail.id),
        "name": cocktail.name,
        "description": cocktail.description,
        "alcoholic": cocktail.alcoholic,
        "theme": cocktail.theme,
        "complexity": cocktail.complexity,
        "glass_type": cocktail.glass_type,
        "technique": cocktail.technique,
        "garnish": cocktail.garnish,
        "comments": cocktail.comments,
        "non_alc_variant": cocktail.non_alc_variant,
        "active": cocktail.active,
        "ingredients": ingredients,
    }

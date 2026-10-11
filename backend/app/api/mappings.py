"""
Ingredient → Product mapping admin API.

The recipe books name specific brands (Beefeater, Beluga Noble, Four Roses...)
that the price lists do not always carry. Rather than guessing a substitution,
the importers leave those ingredients unmapped and the calculation engine flags
them PRODUCT_MAPPING_REQUIRED.

This module lets a human resolve those decisions explicitly. Every mapping
created here is a deliberate, attributed choice — nothing is inferred.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models import (
    Ingredient, Product, IngredientProductMapping,
    Supplier, SupplierProduct, Cocktail, CocktailIngredient,
)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateMappingRequest(BaseModel):
    ingredient_id: str
    product_id: str
    preferred: bool = True
    substitution_allowed: bool = True
    notes: Optional[str] = None


class CreatePriceRequest(BaseModel):
    product_id: str
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    price_before_vat: Optional[float] = Field(None, ge=0)
    price_after_vat: Optional[float] = Field(None, ge=0)
    package_size: Optional[float] = Field(None, gt=0)
    package_unit: Optional[str] = None
    product_url: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _best_price_for_product(db: AsyncSession, product_id: uuid.UUID):
    """Return the preferred SupplierProduct row for a product, or None.

    Prefers a current (non-historical) available listing; falls back to a
    historical one so the UI can still show what the item used to cost.
    """
    result = await db.execute(
        select(SupplierProduct)
        .options(selectinload(SupplierProduct.supplier))
        .where(
            SupplierProduct.product_id == product_id,
            SupplierProduct.available == True,
        )
        .order_by(SupplierProduct.is_historical.asc())
    )
    return result.scalars().first()


def _serialize_candidate(
    product: Product,
    sp: Optional[SupplierProduct],
    canonical_name: Optional[str] = None,
) -> dict:
    return {
        "product_id": str(product.id),
        "product_name": product.name,
        # Source names are Hebrew; the canonical English name makes the
        # picker readable for a non-Hebrew-reading operator.
        "canonical_name": canonical_name,
        "brand": product.brand,
        "package_size": float(product.package_size) if product.package_size else None,
        "package_unit": product.package_unit,
        "price_after_vat": float(sp.price_after_vat) if sp and sp.price_after_vat is not None else None,
        "price_before_vat": float(sp.price_before_vat) if sp and sp.price_before_vat is not None else None,
        "vat_rate": float(sp.vat_rate) if sp else None,
        "is_historical": bool(sp.is_historical) if sp else None,
        "supplier_name": sp.supplier.name if sp and sp.supplier else None,
        "has_price": bool(sp and sp.price_after_vat is not None),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/unmapped")
async def list_unmapped(db: AsyncSession = Depends(get_db)):
    """
    Ingredients that have no product mapping, ranked by how many cocktails
    use them — so the highest-impact decisions surface first.
    """
    mapped_subq = select(IngredientProductMapping.ingredient_id)

    result = await db.execute(
        select(
            Ingredient,
            func.count(distinct(CocktailIngredient.cocktail_id)).label("usage"),
        )
        .outerjoin(CocktailIngredient, CocktailIngredient.ingredient_id == Ingredient.id)
        .where(Ingredient.id.notin_(mapped_subq))
        .group_by(Ingredient.id)
        .order_by(func.count(distinct(CocktailIngredient.cocktail_id)).desc(), Ingredient.canonical_name)
    )

    rows = result.all()
    return {
        "count": len(rows),
        "items": [
            {
                "ingredient_id": str(ing.id),
                "canonical_name": ing.canonical_name,
                "category": ing.category,
                "unit_type": ing.unit_type,
                "alcoholic": ing.alcoholic,
                "cocktail_usage_count": usage,
            }
            for ing, usage in rows
        ],
    }


@router.get("/mapped")
async def list_mapped(db: AsyncSession = Depends(get_db)):
    """Existing mappings, so they can be reviewed, changed, or removed."""
    result = await db.execute(
        select(IngredientProductMapping)
        .options(
            selectinload(IngredientProductMapping.ingredient),
            selectinload(IngredientProductMapping.product),
        )
        .order_by(IngredientProductMapping.preferred.desc())
    )
    mappings = result.scalars().all()

    items = []
    for m in mappings:
        sp = await _best_price_for_product(db, m.product_id)
        items.append({
            "mapping_id": str(m.id),
            "ingredient_id": str(m.ingredient_id),
            "ingredient_name": m.ingredient.canonical_name if m.ingredient else None,
            "category": m.ingredient.category if m.ingredient else None,
            "product_id": str(m.product_id),
            "product_name": m.product.name if m.product else None,
            "preferred": m.preferred,
            "substitution_allowed": m.substitution_allowed,
            "notes": m.notes,
            "price_after_vat": float(sp.price_after_vat) if sp and sp.price_after_vat is not None else None,
            "supplier_name": sp.supplier.name if sp and sp.supplier else None,
            "has_price": bool(sp and sp.price_after_vat is not None),
        })

    return {"count": len(items), "items": items}


@router.get("/candidates/{ingredient_id}")
async def list_candidates(ingredient_id: str, db: AsyncSession = Depends(get_db)):
    """
    Candidate products for an ingredient. Same-category products are returned
    first (most likely substitutes), then everything else so nothing is hidden.
    Products WITHOUT a price are included but marked has_price=false — mapping
    to one of those yields PRICE_MISSING rather than a silent zero.
    """
    try:
        uid = uuid.UUID(ingredient_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ingredient ID")

    ing_r = await db.execute(select(Ingredient).where(Ingredient.id == uid))
    ingredient = ing_r.scalar_one_or_none()
    if ingredient is None:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    # All products, with their own ingredient's category and canonical name
    prod_r = await db.execute(
        select(Product, Ingredient.category, Ingredient.canonical_name)
        .join(Ingredient, Product.ingredient_id == Ingredient.id, isouter=True)
        .where(Product.active == True)
        .order_by(Product.name)
    )
    rows = prod_r.all()

    same_category, other = [], []
    for product, prod_category, prod_canonical in rows:
        sp = await _best_price_for_product(db, product.id)
        entry = _serialize_candidate(product, sp, prod_canonical)
        if prod_category and ingredient.category and prod_category == ingredient.category:
            same_category.append(entry)
        else:
            other.append(entry)

    # Priced options first within each group — a mapping to a priced product
    # is immediately useful, an unpriced one still needs a price entered.
    def _sort_key(e):
        return (not e["has_price"], (e["canonical_name"] or e["product_name"]).lower())

    same_category.sort(key=_sort_key)
    other.sort(key=_sort_key)

    return {
        "ingredient": {
            "ingredient_id": str(ingredient.id),
            "canonical_name": ingredient.canonical_name,
            "category": ingredient.category,
            "unit_type": ingredient.unit_type,
        },
        "same_category": same_category,
        "other": other,
    }


@router.post("", status_code=201)
async def create_mapping(body: CreateMappingRequest, db: AsyncSession = Depends(get_db)):
    """Map an ingredient to a product. Explicit, human-approved substitution."""
    try:
        ing_uid = uuid.UUID(body.ingredient_id)
        prod_uid = uuid.UUID(body.product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    ing_r = await db.execute(select(Ingredient).where(Ingredient.id == ing_uid))
    ingredient = ing_r.scalar_one_or_none()
    if ingredient is None:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    prod_r = await db.execute(select(Product).where(Product.id == prod_uid))
    product = prod_r.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # Reject an exact duplicate rather than silently stacking rows
    dup_r = await db.execute(
        select(IngredientProductMapping).where(
            IngredientProductMapping.ingredient_id == ing_uid,
            IngredientProductMapping.product_id == prod_uid,
        )
    )
    if dup_r.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="This mapping already exists")

    # Only one preferred mapping per ingredient
    if body.preferred:
        existing_r = await db.execute(
            select(IngredientProductMapping).where(
                IngredientProductMapping.ingredient_id == ing_uid,
                IngredientProductMapping.preferred == True,
            )
        )
        for prev in existing_r.scalars().all():
            prev.preferred = False

    mapping = IngredientProductMapping(
        ingredient_id=ing_uid,
        product_id=prod_uid,
        preferred=body.preferred,
        substitution_allowed=body.substitution_allowed,
        notes=body.notes,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

    sp = await _best_price_for_product(db, prod_uid)
    return {
        "mapping_id": str(mapping.id),
        "ingredient_name": ingredient.canonical_name,
        "product_name": product.name,
        "preferred": mapping.preferred,
        "has_price": bool(sp and sp.price_after_vat is not None),
        "warning": (
            None if sp and sp.price_after_vat is not None
            else "Mapped product has no price — costing will report PRICE_MISSING "
                 "until one is added."
        ),
    }


@router.delete("/{mapping_id}", status_code=200)
async def delete_mapping(mapping_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a mapping. The ingredient returns to PRODUCT_MAPPING_REQUIRED."""
    try:
        uid = uuid.UUID(mapping_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid mapping ID")

    result = await db.execute(
        select(IngredientProductMapping).where(IngredientProductMapping.id == uid)
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        raise HTTPException(status_code=404, detail="Mapping not found")

    await db.delete(mapping)
    await db.commit()
    return {"status": "deleted", "mapping_id": mapping_id}


@router.post("/price", status_code=201)
async def add_price(body: CreatePriceRequest, db: AsyncSession = Depends(get_db)):
    """
    Attach a current price to a product that has none.

    New prices are recorded at the CURRENT VAT rate (18%) and is_historical=False.
    Imported 17% records are left untouched so past events remain auditable
    at the rate actually paid.
    """
    try:
        prod_uid = uuid.UUID(body.product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    prod_r = await db.execute(select(Product).where(Product.id == prod_uid))
    product = prod_r.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if body.price_before_vat is None and body.price_after_vat is None:
        raise HTTPException(
            status_code=422,
            detail="Provide price_before_vat or price_after_vat. "
                   "A price is never assumed to be zero.",
        )

    # Resolve supplier
    supplier = None
    if body.supplier_id:
        try:
            sup_uid = uuid.UUID(body.supplier_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid supplier ID")
        sup_r = await db.execute(select(Supplier).where(Supplier.id == sup_uid))
        supplier = sup_r.scalar_one_or_none()
        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")
    else:
        name = body.supplier_name or "Manual Entry"
        sup_r = await db.execute(select(Supplier).where(Supplier.name == name))
        supplier = sup_r.scalar_one_or_none()
        if supplier is None:
            supplier = Supplier(name=name, active=True)
            db.add(supplier)
            await db.flush()

    # Derive the missing side of the price from the current VAT rate
    vat = settings.DEFAULT_VAT_RATE
    before = body.price_before_vat
    after = body.price_after_vat
    if before is None:
        before = round(after / (1 + vat), 2)
    if after is None:
        after = round(before * (1 + vat), 2)

    # Package size can be corrected here too — it is required to compute packages
    if body.package_size is not None:
        product.package_size = body.package_size
    if body.package_unit:
        product.package_unit = body.package_unit

    listing = SupplierProduct(
        supplier_id=supplier.id,
        product_id=prod_uid,
        price_before_vat=before,
        price_after_vat=after,
        vat_rate=vat,
        is_historical=False,
        product_url=body.product_url,
        source_file=None,
        available=True,
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    return {
        "supplier_product_id": str(listing.id),
        "product_name": product.name,
        "supplier_name": supplier.name,
        "price_before_vat": float(listing.price_before_vat),
        "price_after_vat": float(listing.price_after_vat),
        "vat_rate": float(listing.vat_rate),
        "package_size": float(product.package_size) if product.package_size else None,
        "package_unit": product.package_unit,
    }


@router.get("/coverage")
async def mapping_coverage(db: AsyncSession = Depends(get_db)):
    """
    Headline numbers for the admin screen: how much of the catalog is
    actually costable right now.
    """
    total_r = await db.execute(select(func.count()).select_from(Ingredient))
    total = total_r.scalar_one()

    mapped_r = await db.execute(
        select(func.count(distinct(IngredientProductMapping.ingredient_id)))
    )
    mapped = mapped_r.scalar_one()

    # Mapped AND the mapped product carries a usable price
    priced_r = await db.execute(
        select(func.count(distinct(IngredientProductMapping.ingredient_id)))
        .join(SupplierProduct, SupplierProduct.product_id == IngredientProductMapping.product_id)
        .where(
            SupplierProduct.price_after_vat.isnot(None),
            SupplierProduct.available == True,
        )
    )
    priced = priced_r.scalar_one()

    return {
        "total_ingredients": total,
        "mapped": mapped,
        "unmapped": total - mapped,
        "mapped_and_priced": priced,
        "mapped_without_price": mapped - priced,
        "coverage_pct": round(priced / total * 100, 1) if total else 0.0,
    }

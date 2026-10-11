"""
Suppliers API — list suppliers and their products with pricing.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models import Supplier, SupplierProduct, Product, Ingredient

router = APIRouter()


@router.get("")
async def list_suppliers(db: AsyncSession = Depends(get_db)):
    """List all active suppliers."""
    result = await db.execute(
        select(Supplier).where(Supplier.active == True).order_by(Supplier.name)
    )
    suppliers = result.scalars().all()
    return {
        "suppliers": [
            {"id": str(s.id), "name": s.name, "website": s.website}
            for s in suppliers
        ]
    }


@router.get("/{supplier_id}/products")
async def supplier_products(supplier_id: str, db: AsyncSession = Depends(get_db)):
    """List products with pricing for a specific supplier."""
    import uuid
    try:
        uid = uuid.UUID(supplier_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid supplier ID")

    result = await db.execute(
        select(SupplierProduct)
        .options(
            selectinload(SupplierProduct.product).selectinload(Product.ingredient)
        )
        .where(
            SupplierProduct.supplier_id == uid,
            SupplierProduct.available == True,
        )
        .order_by(SupplierProduct.is_historical, SupplierProduct.last_checked_at.desc().nullslast())
    )
    items = result.scalars().all()

    return {
        "supplier_id": supplier_id,
        "products": [
            {
                "product_id": str(sp.product_id),
                "product_name": sp.product.name if sp.product else None,
                "ingredient_name": sp.product.ingredient.canonical_name if sp.product and sp.product.ingredient else None,
                "package_size": float(sp.product.package_size) if sp.product and sp.product.package_size else None,
                "package_unit": sp.product.package_unit if sp.product else None,
                "price_before_vat": float(sp.price_before_vat) if sp.price_before_vat else None,
                "price_after_vat": float(sp.price_after_vat) if sp.price_after_vat else None,
                "vat_rate": float(sp.vat_rate) if sp.vat_rate else None,
                "is_historical": sp.is_historical,
                "product_url": sp.product_url,
            }
            for sp in items
        ]
    }

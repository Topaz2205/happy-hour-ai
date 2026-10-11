"""
Cost the house-made ingredients from the price of their inputs.

Creates a "House-made" supplier, a product per house recipe priced from your
own sugar price, and maps the ingredient to it — so cocktails using simple
syrup stop being under-costed.

Re-run it any time an input price changes; it updates rather than duplicating.

    python scripts/setup_house_made.py
    python scripts/setup_house_made.py --show    # print the maths, change nothing
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import (
    Ingredient, Product, IngredientProductMapping, Supplier, SupplierProduct,
)
from app.services.house_made import HOUSE_RECIPES, HOUSE_SUPPLIER_NAME

BATCH_BOTTLE_ML = 1000.0  # house syrup is bottled by the litre


async def _price_per_ml(session) -> dict[str, float]:
    """Cheapest available price per ml, per ingredient name."""
    rows = await session.execute(
        select(Ingredient.canonical_name, Product.package_size,
               SupplierProduct.price_after_vat)
        .join(Product, Product.ingredient_id == Ingredient.id)
        .join(SupplierProduct, SupplierProduct.product_id == Product.id)
        .where(SupplierProduct.price_after_vat.isnot(None),
               SupplierProduct.available == True,
               Product.package_size.isnot(None))
    )
    best: dict[str, float] = {}
    for name, size, price in rows.all():
        if not size or float(size) <= 0:
            continue
        per_ml = float(price) / float(size)
        if name not in best or per_ml < best[name]:
            best[name] = per_ml
    return best


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true", help="print the maths, change nothing")
    args = ap.parse_args()

    print("=" * 66)
    print("HOUSE-MADE INGREDIENTS")
    print("=" * 66)

    async with AsyncSessionLocal() as session:
        prices = await _price_per_ml(session)

        supplier = None
        if not args.show:
            sup_r = await session.execute(
                select(Supplier).where(Supplier.name == HOUSE_SUPPLIER_NAME)
            )
            supplier = sup_r.scalar_one_or_none()
            if supplier is None:
                supplier = Supplier(name=HOUSE_SUPPLIER_NAME, active=True, is_retailer=False)
                session.add(supplier)
                await session.flush()

        for recipe in HOUSE_RECIPES:
            print(f"\n▸ {recipe.ingredient_name}")
            print(f"  {recipe.method}")

            cost_per_ml, problems = recipe.cost_per_ml(prices)
            for line in recipe.inputs:
                if line.free:
                    print(f"    {line.amount_ml:>6.0f}ml  {line.ingredient_name:<22} free")
                else:
                    unit = prices.get(line.ingredient_name)
                    if unit is None:
                        print(f"    {line.amount_ml:>6.0f}ml  {line.ingredient_name:<22} NO PRICE")
                    else:
                        print(f"    {line.amount_ml:>6.0f}ml  {line.ingredient_name:<22} "
                              f"₪{unit * line.amount_ml:.2f}  (₪{unit * 1000:.2f}/L)")

            if cost_per_ml is None:
                for p in problems:
                    print(f"  ✗ {p}")
                continue

            print(f"  yield: {recipe.yield_ml:.0f}ml — {recipe.yield_note}")
            print(f"  → ₪{cost_per_ml * 1000:.2f} per litre")

            if args.show:
                continue

            ing_r = await session.execute(
                select(Ingredient).where(Ingredient.canonical_name == recipe.ingredient_name)
            )
            ingredient = ing_r.scalar_one_or_none()
            if ingredient is None:
                print(f"  ! '{recipe.ingredient_name}' is not an ingredient in the "
                      f"database — skipped.")
                continue

            prod_r = await session.execute(
                select(Product).where(Product.ingredient_id == ingredient.id,
                                      Product.name == recipe.ingredient_name)
            )
            product = prod_r.scalar_one_or_none()
            if product is None:
                product = Product(
                    name=recipe.ingredient_name,
                    ingredient_id=ingredient.id,
                    package_size=BATCH_BOTTLE_ML,
                    package_unit="ml",
                    active=True,
                    notes=f"House-made. {recipe.method} {recipe.yield_note}",
                )
                session.add(product)
                await session.flush()

            bottle_price = round(cost_per_ml * BATCH_BOTTLE_ML, 2)

            sp_r = await session.execute(
                select(SupplierProduct).where(
                    SupplierProduct.supplier_id == supplier.id,
                    SupplierProduct.product_id == product.id,
                )
            )
            listing = sp_r.scalar_one_or_none()
            if listing is None:
                session.add(SupplierProduct(
                    supplier_id=supplier.id, product_id=product.id,
                    price_before_vat=round(bottle_price / (1 + settings.DEFAULT_VAT_RATE), 2),
                    price_after_vat=bottle_price,
                    vat_rate=settings.DEFAULT_VAT_RATE,
                    is_historical=False, available=True,
                    source_file="computed from input prices",
                ))
                print(f"  ✅ priced at ₪{bottle_price:.2f} per litre")
            else:
                old = float(listing.price_after_vat or 0)
                listing.price_after_vat = bottle_price
                listing.price_before_vat = round(bottle_price / (1 + settings.DEFAULT_VAT_RATE), 2)
                print(f"  ✅ updated ₪{old:.2f} → ₪{bottle_price:.2f} per litre")

            map_r = await session.execute(
                select(IngredientProductMapping).where(
                    IngredientProductMapping.ingredient_id == ingredient.id
                )
            )
            if map_r.scalars().first() is None:
                session.add(IngredientProductMapping(
                    ingredient_id=ingredient.id, product_id=product.id,
                    preferred=True, substitution_allowed=False,
                    notes="House-made — cost computed from input prices.",
                ))
                print("  ✅ mapped")

        if not args.show:
            await session.commit()
            print("\nDone. Re-run this whenever an input price changes.")
        else:
            print("\n(--show: nothing was changed)")


if __name__ == "__main__":
    asyncio.run(main())

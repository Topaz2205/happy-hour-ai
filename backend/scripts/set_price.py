"""
Give an ingredient a price, so it stops blocking the shopping list.

Use this for anything you can buy but that isn't in the imported price files —
fresh lime juice, a new supplier's bottle, a product whose price changed.

    # see what still has no price
    python scripts/set_price.py --list

    # price fresh lime juice at ₪27 for a 2-litre bottle
    python scripts/set_price.py "Fresh Lime Juice" --price 27 --size 2000

    # name the supplier and link the product page
    python scripts/set_price.py "Fresh Lime Juice" --price 27 --size 2000 \\
        --supplier "Paneco" --url "https://www.paneco.co.il/..."

The price you give is the price INCLUDING VAT — what you actually pay. The
pre-VAT figure is worked back from it at the current rate.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import (
    Ingredient, Product, IngredientProductMapping, Supplier, SupplierProduct,
    CocktailIngredient,
)


async def show_unpriced(session, limit: int = 40):
    priced = (
        select(IngredientProductMapping.ingredient_id)
        .join(SupplierProduct,
              SupplierProduct.product_id == IngredientProductMapping.product_id)
        .where(SupplierProduct.price_after_vat.isnot(None))
    )
    rows = await session.execute(
        select(Ingredient.canonical_name, Ingredient.unit_type,
               func.count(CocktailIngredient.cocktail_id).label("uses"))
        .outerjoin(CocktailIngredient,
                   CocktailIngredient.ingredient_id == Ingredient.id)
        .where(Ingredient.id.notin_(priced))
        .group_by(Ingredient.id)
        .order_by(func.count(CocktailIngredient.cocktail_id).desc())
        .limit(limit)
    )
    items = rows.all()
    print(f"{len(items)} ingredient(s) with no usable price, most blocking first:\n")
    for name, unit, uses in items:
        flag = "  ←" if uses >= 4 else ""
        print(f"  {uses:>3} cocktails   {name:<42} ({unit}){flag}")
    print("\nPrice one with:")
    print('  python scripts/set_price.py "NAME" --price 27 --size 2000')


async def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ingredient", nargs="?", help="exact canonical name, in quotes")
    ap.add_argument("--price", type=float, help="price you pay, including VAT")
    ap.add_argument("--size", type=float, help="package size, in the ingredient's unit")
    ap.add_argument("--supplier", default="Manual Entry")
    ap.add_argument("--url", default=None, help="product page, if you have it")
    ap.add_argument("--list", action="store_true", help="show what still has no price")
    ap.add_argument("--free", metavar="REASON",
                    help="this costs nothing to buy — say why, e.g. "
                         '"office coffee machine". Recorded explicitly, never silently.')
    args = ap.parse_args()

    async with AsyncSessionLocal() as session:
        if args.list or not args.ingredient:
            await show_unpriced(session)
            return

        # Zero is normally forbidden — a missing price must surface as a gap, not
        # as free. --free is the one exception: an ingredient you genuinely do not
        # buy (tap water, office coffee, brine that comes with the olives). It
        # demands a written reason so the zero is always attributable, and the
        # reason travels with the mapping into the UI.
        if args.free:
            args.price = 0.0
            args.size = args.size or 1.0

        if args.price is None or args.size is None:
            print("Both --price and --size are required.")
            print('  python scripts/set_price.py "Fresh Lime Juice" --price 27 --size 2000')
            return
        if not args.free and (args.price <= 0 or args.size <= 0):
            print("Price and size must both be greater than zero.")
            print("A price of zero is never assumed anywhere in this system.")
            print('If it genuinely costs you nothing, say so explicitly:')
            print('  --free "office coffee machine"')
            return

        ing_r = await session.execute(
            select(Ingredient).where(
                func.lower(Ingredient.canonical_name) == args.ingredient.lower()
            )
        )
        ingredient = ing_r.scalar_one_or_none()
        if ingredient is None:
            near = await session.execute(
                select(Ingredient.canonical_name).where(
                    Ingredient.canonical_name.ilike(f"%{args.ingredient}%")
                ).limit(8)
            )
            options = [n for (n,) in near.all()]
            print(f"No ingredient called '{args.ingredient}'.")
            if options:
                print("Did you mean:")
                for o in options:
                    print(f"  {o}")
            else:
                print("Run with --list to see what exists.")
            return

        sup_r = await session.execute(select(Supplier).where(Supplier.name == args.supplier))
        supplier = sup_r.scalar_one_or_none()
        if supplier is None:
            supplier = Supplier(name=args.supplier, active=True)
            session.add(supplier)
            await session.flush()

        prod_r = await session.execute(
            select(Product).where(Product.ingredient_id == ingredient.id)
        )
        product = prod_r.scalars().first()
        if product is None:
            product = Product(
                name=ingredient.canonical_name,
                ingredient_id=ingredient.id,
                package_size=args.size,
                package_unit=ingredient.unit_type or "ml",
                active=True,
                notes="Created by set_price.py",
            )
            session.add(product)
            await session.flush()
        else:
            product.package_size = args.size

        vat = settings.DEFAULT_VAT_RATE
        before = round(args.price / (1 + vat), 2)

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
                price_before_vat=before, price_after_vat=args.price,
                vat_rate=vat, is_historical=False, available=True,
                product_url=args.url,
            ))
            action = "priced"
        else:
            listing.price_after_vat = args.price
            listing.price_before_vat = before
            listing.vat_rate = vat
            if args.url:
                listing.product_url = args.url
            action = "updated"

        map_r = await session.execute(
            select(IngredientProductMapping).where(
                IngredientProductMapping.ingredient_id == ingredient.id
            )
        )
        if map_r.scalars().first() is None:
            session.add(IngredientProductMapping(
                ingredient_id=ingredient.id, product_id=product.id,
                preferred=True, substitution_allowed=False,
                notes=(f"No purchase cost — {args.free}" if args.free
                       else f"Priced manually via set_price.py ({args.supplier})"),
            ))

        await session.commit()

        unit = ingredient.unit_type or "ml"
        if args.free:
            print(f"✅ {ingredient.canonical_name}: recorded as no purchase cost")
            print(f"   reason: {args.free}")
            print("\n   It will show in recipes but add nothing to the total.")
            return
        per_l = args.price / args.size * 1000 if unit == "ml" else None
        print(f"✅ {action}: {ingredient.canonical_name}")
        print(f"   ₪{args.price:.2f} per {args.size:g}{unit}"
              + (f"  (₪{per_l:.2f}/L)" if per_l else ""))
        print(f"   supplier: {args.supplier}  ·  VAT {vat:.0%}")
        if args.url:
            print(f"   link: {args.url}")
        print("\n   Re-plan an event to see it in the shopping list.")


if __name__ == "__main__":
    asyncio.run(main())

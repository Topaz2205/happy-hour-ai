"""
Give every spirit slot a ladder of real alternatives, from Topaz's price book.

    python scripts/load_spirit_options.py [--apply]

THE PROBLEM THIS SOLVES
-----------------------
A recipe names a specific bottle — "Beefeater London Dry Gin". Until now that
was the only product the engine could buy, so when someone said "make it
cheaper" the agent's only move was to change the menu: drop a cocktail, or
swap it for a different drink. That is the wrong answer to the question. The
person asked for a cheaper *margarita*, not for a different cocktail.

Her own price book already holds the answer — four gins from ₪57 to ₪139, six
whiskies from ₪77 to ₪333. Those are alternatives for the same slot. Loading
them turns "make it cheaper" into a bottle choice instead of a menu cut.

WHAT IS AND IS NOT A SUBSTITUTION
---------------------------------
Pouring Gordon's where the recipe says Beefeater changes the drink. That is a
real decision and it is the customer's to make, not the software's — so every
alternative is marked `substitution_allowed` and offered, never silently
applied. The recipe's own bottle stays `preferred`, and the ladder is sorted by
price so the position in it means something.

Alternatives are only ever offered within the same spirit type. Gin for gin.
The table below is written out by hand for exactly that reason: a fuzzy match
on Hebrew product names would eventually pour arak into a margarita, and that
failure would reach a paying customer as a shopping list, not as an error.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.models import Ingredient, Product, Supplier
from app.models.product import IngredientProductMapping
from app.models.supplier import SupplierProduct

# Prices are her price book's pre-VAT figures, which predate the 2025 VAT change
# and are therefore stored at the historical rate, like every other imported
# price in this system. They are not rewritten to 18%.
VAT = settings.HISTORICAL_VAT_RATE

# ingredient canonical_name  →  [(hebrew name, english name, size_ml, price_ex_vat)]
# Ordered as written; the loader sorts by price, so this order is not load-bearing.
OPTIONS: dict[str, list[tuple[str, str, float, float]]] = {
    "Beefeater London Dry Gin": [
        ("ג׳ין זמנסקי", "Zemanski Gin", 1000, 48.80),
        ("גורדונס", "Gordon's Gin", 1000, 60.00),
        ("בומביי", "Bombay Sapphire Gin", 750, 115.00),
        ("הנדריקס", "Hendrick's Gin", 700, 119.00),
    ],
    "Beluga Noble Vodka": [
        ("וודקה מירור", "Mirror Vodka", 1000, 55.50),
        ("סטוליצינה ליטר", "Stolichnaya Vodka", 1000, 69.00),
        ("גרייגוס", "Grey Goose Vodka", 1000, 125.00),
    ],
    "Olmeca Silver Tequila": [
        ("אמיסריו סילבר", "Emisario Silver Tequila", 1000, 65.70),
        ("פטרון סילבר", "Patrón Silver Tequila", 750, 165.00),
    ],
    "Havana Club Añejo 3 Años Rum": [
        ("רום קפטן מורגן ספייס", "Captain Morgan Spiced Rum", 700, 68.00),
        ("רום קאנוקה", "Canuka Rum", 700, 68.40),
        ("רום זאקפה", "Zacapa Rum", 700, 210.00),
    ],
    # Her instruction, recorded earlier: Rittenhouse Rye may be replaced with an
    # ordinary whiskey. These are the whiskies in her book, not a guess.
    "Rittenhouse Rye Whiskey": [
        ("מאלטז' ויסקי סקוטי", "Maltese Scotch Whisky", 700, 65.50),
        ("בושימלס", "Bushmills Irish Whiskey", 1000, 85.00),
        ("גק' דניאלס", "Jack Daniel's", 1000, 105.00),
        ("בלאק לייבל", "Johnnie Walker Black Label", 700, 128.00),
    ],
    "Four Roses Bourbon": [
        ("בושימלס", "Bushmills Irish Whiskey", 1000, 85.00),
        ("גק' דניאלס", "Jack Daniel's", 1000, 105.00),
        ("בלאק לייבל", "Johnnie Walker Black Label", 700, 128.00),
    ],
}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        supplier = (await db.execute(
            select(Supplier).where(Supplier.name.ilike("%המשמח%"))
        )).scalars().first()
        if supplier is None:
            supplier = (await db.execute(
                select(Supplier).where(Supplier.is_retailer == True)  # noqa: E712
            )).scalars().first()
        if supplier is None:
            print("✗ No retailer in the database. Run add_suppliers first.")
            return 1

        total = 0
        for ing_name, options in OPTIONS.items():
            ing = (await db.execute(
                select(Ingredient).where(Ingredient.canonical_name == ing_name)
            )).scalar_one_or_none()
            if ing is None:
                print(f"  ! no ingredient named {ing_name!r} — skipped")
                continue

            ladder = sorted(options, key=lambda o: o[3] / o[2])  # by ₪ per ml
            print(f"\n{ing_name}")
            for rank, (he, en, size, ex_vat) in enumerate(ladder, start=1):
                inc_vat = round(ex_vat * (1 + VAT), 2)
                per_ml = ex_vat / size
                print(f"  {rank}. {en:<32} {size:>5.0f}ml  ₪{inc_vat:>7.2f}  "
                      f"({per_ml*1000:.0f} ₪/L)")
                total += 1
                if not args.apply:
                    continue

                # .first(), not .scalar_one_or_none(): the same bottle legitimately
                # serves more than one slot — Bushmills is an alternative for both
                # the rye and the bourbon — and a name may already exist from an
                # earlier import. One Product row, many mappings.
                product = (await db.execute(
                    select(Product).where(Product.name == he)
                )).scalars().first()
                if product is None:
                    product = Product(name=he, brand=en, ingredient_id=ing.id,
                                      package_size=size, package_unit="ml",
                                      notes=f"{en} — alternative for {ing_name}")
                    db.add(product)
                    await db.flush()

                listing = (await db.execute(
                    select(SupplierProduct).where(
                        SupplierProduct.product_id == product.id,
                        SupplierProduct.supplier_id == supplier.id)
                )).scalar_one_or_none()
                if listing is None:
                    db.add(SupplierProduct(
                        supplier_id=supplier.id, product_id=product.id,
                        price_before_vat=ex_vat, price_after_vat=inc_vat,
                        vat_rate=VAT, is_historical=True, available=True))

                mapping = (await db.execute(
                    select(IngredientProductMapping).where(
                        IngredientProductMapping.ingredient_id == ing.id,
                        IngredientProductMapping.product_id == product.id)
                )).scalar_one_or_none()
                if mapping is None:
                    db.add(IngredientProductMapping(
                        ingredient_id=ing.id, product_id=product.id,
                        preferred=False,          # the recipe's own bottle stays preferred
                        substitution_allowed=True,
                        substitution_priority=rank,
                        notes="Alternative from Topaz's price book. Offer, never apply silently."))

        if args.apply:
            await db.commit()

    print(f"\n{total} alternatives across {len(OPTIONS)} spirit slots.")
    print("The recipe's own bottle stays preferred; these are offered, not applied.")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""
The bottles each shop actually stocks for slots whose exact brand it does not.

    python scripts/load_substitutes.py [--apply]

WHY THESE WERE NOT LOADED BEFORE
--------------------------------
The earlier price loaders found all of these and deliberately left them out,
with the note: "every shop stocks a white rum, but they are different brands —
which one belongs in a daiquiri is a recipe decision, not an import decision."

That was the right call at the time and the wrong outcome. Topaz has since made
the decision — any rum will do, the brand in a recipe is a preference — so the
data can come in. Each row below is mapped to the substitute group rather than
to a specific recipe, which is what lets a shop holding Bacardi cover a recipe
that names Havana Club.

EVERY PRICE WAS READ ON A PAGE THAT WAS LOADED
----------------------------------------------
Same rule as everywhere else. Products that were only ever seen on a category
listing, or whose size was unconfirmed, are not here.
"""
import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.models import Product, Supplier, Ingredient
from app.models.product import IngredientProductMapping
from app.models.supplier import SupplierProduct

VAT = settings.DEFAULT_VAT_RATE

# (substitute group, shop, product name, size ml, ₪, in stock)
#
# Mapped to the group's ingredient, so any recipe in that group can use them.
SUBSTITUTES = [
    # ── white rum ─────────────────────────────────────────────────────────
    ("white_rum", "שר המשקאות", "רום בקרדי לבן ליטר", 1000, 110.0, True),
    ("white_rum", "שר המשקאות", "רום קריביקה לבן 700 מ\"ל", 700, 65.0, True),
    ("white_rum", "בנא משקאות", "רום קפטן מורגן וייט 700 מ\"ל", 700, 94.90, True),
    ("white_rum", "בנא משקאות", "רום בקרדי לבן ליטר", 1000, 126.90, True),
    ("white_rum", "Paneco", "בקרדי לבן ליטר", 1000, 114.90, True),
    ("white_rum", "עולם היין", "רום נגריטה לבן 0.7", 700, 68.0, True),
    ("white_rum", "עולם היין", "רום קפטן מורגן לבן 0.7", 700, 80.0, True),
    ("white_rum", "עולם היין", "רום קריביקה", 700, 64.0, True),

    # ── blanco tequila ────────────────────────────────────────────────────
    # No shop stocks plain Olmeca Silver. These are what they do have.
    ("blanco_tequila", "עולם היין", "טקילה סיירה סילבר 700", 700, 88.0, True),
    ("blanco_tequila", "עולם היין", "אולמקה גולד 700", 700, 94.0, True),
    ("blanco_tequila", "Paneco", "טקילה מילגרו סילבר", 700, 144.90, True),

    # ── orange liqueur ────────────────────────────────────────────────────
    # Nobody stocks Pierre Ferrand Dry Curaçao. Cointreau and triple sec are
    # the same family — drier or sweeter, but each makes a margarita.
    ("orange_liqueur", "עולם היין", "ליקר קוונטרו 0.7", 700, 105.0, True),
    ("orange_liqueur", "עולם היין", "ליקר בולס טריפל סק", 700, 89.0, True),
    ("orange_liqueur", "Paneco", "ליקר טריפל סק 1715", 700, 59.0, True),

    # ── sweet vermouth ────────────────────────────────────────────────────
    ("sweet_vermouth", "שר המשקאות", "ורמוט גאנצ'יה רוסו", 1000, 45.0, True),
    ("sweet_vermouth", "בנא משקאות", "ורמוט צינזנו אדום 750", 750, 44.90, True),
    ("sweet_vermouth", "עולם היין", "וורמוט ברברו ביאנקו ליטר", 1000, 27.0, True),

    # ── gin ───────────────────────────────────────────────────────────────
    ("gin", "עולם היין", "ג'ין גורדונס", 1000, 70.20, True),

    # ── dry vermouth ──────────────────────────────────────────────────────
    # Mancino Secco is stocked nowhere; Dolin is the standard dry vermouth.
    ("dry_vermouth", "עולם היין", "וורמוט דולין יבש 17.5% 750", 750, 41.0, True),

    # ── bianco vermouth ───────────────────────────────────────────────────
    ("bianco_vermouth", "עולם היין", "וורמוט מרטיני ביאנקו ליטר", 1000, 50.0, True),
]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    done, skipped = [], []

    async with AsyncSessionLocal() as db:
        for group, shop, name, size, price, stock in SUBSTITUTES:
            # Map to the group's own ingredient — any of them will do, since
            # they all share the group and the query widens across it.
            ing = (await db.execute(
                select(Ingredient).where(Ingredient.substitute_group == group)
            )).scalars().first()
            supplier = (await db.execute(
                select(Supplier).where(Supplier.name == shop)
            )).scalars().first()
            if ing is None or supplier is None:
                skipped.append(f"{name} @ {shop} ({group})")
                continue

            product = (await db.execute(
                select(Product).where(Product.name == name)
            )).scalars().first()
            if product is None:
                product = Product(name=name, brand=name, package_size=size,
                                  package_unit="ml", ingredient_id=ing.id,
                                  notes=f"Substitute · {group}")
                if args.apply:
                    db.add(product)
                    await db.flush()

            if args.apply:
                listing = (await db.execute(
                    select(SupplierProduct).where(
                        SupplierProduct.product_id == product.id,
                        SupplierProduct.supplier_id == supplier.id)
                )).scalars().first()
                if listing is None:
                    listing = SupplierProduct(supplier_id=supplier.id,
                                              product_id=product.id)
                    db.add(listing)
                listing.package_size = size
                listing.package_unit = "ml"
                listing.price_after_vat = price
                listing.price_before_vat = round(price / (1 + VAT), 2)
                listing.vat_rate = VAT
                listing.is_historical = False
                listing.available = stock

                mapping = (await db.execute(
                    select(IngredientProductMapping).where(
                        IngredientProductMapping.ingredient_id == ing.id,
                        IngredientProductMapping.product_id == product.id)
                )).scalars().first()
                if mapping is None:
                    db.add(IngredientProductMapping(
                        ingredient_id=ing.id, product_id=product.id,
                        preferred=False,           # never displaces the recipe's own
                        substitution_allowed=True,
                        substitution_priority=5,
                        notes=f"Substitute within {group}. Offered, never applied silently."))

            done.append((group, shop, name, size, price))

        if args.apply:
            await db.commit()

    by_group: dict[str, list] = {}
    for group, shop, name, size, price in done:
        by_group.setdefault(group, []).append((shop, name, size, price))

    for group, rows in sorted(by_group.items()):
        print(f"\n{group}")
        for shop, name, size, price in sorted(rows, key=lambda r: r[3] / r[2]):
            print(f"   {shop:<18} {name[:30]:<30} {size:>5.0f}ml  ₪{price:>7.2f}"
                  f"   {price / size * 1000:>6.1f} ₪/L")

    print(f"\n{len(done)} substitute listing(s) across {len({d[1] for d in done})} shop(s).")
    if skipped:
        print(f"{len(skipped)} skipped (no such group or shop): " + "; ".join(skipped))
    print("\nAll are substitution_allowed and never preferred — the recipe's own "
          "bottle stays the recommendation.")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

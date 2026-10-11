"""
Workshop equipment, priced where a price exists.

    python scripts/load_equipment.py [--apply]

Researched 27 Aug 2026. Every price was read on an EQUIP product page that was
actually loaded, and stock was taken from the product page rather than the
search results — those disagreed, showing a shaker as in stock in search and
sold out on its own page.

WHY ONLY ONE SHOP
-----------------
Of the three equipment suppliers Topaz named, only EQUIP publishes prices.
קוקטייל ארט is a lead-capture catalogue — every product page is an enquiry form
with no figure anywhere — and they run cocktail workshops themselves, so they
are a competitor as well as a possible supplier. The other two are B2B
catalogues with no public pricing. Those facts are recorded at the bottom of
this file rather than left to be rediscovered.

THE SHAKER PROBLEM
------------------
Both of EQUIP's standalone shakers are out of stock. The only in-stock route to
a shaker is the ₪130 bartender kit, which contains one — so a ten-station
workshop pays ₪1,300 for shakers instead of ₪370. That is not a rounding
detail; it is most of the equipment bill, and it is why the out-of-stock
shakers are loaded rather than dropped. Their prices are real and the
comparison is worth showing.
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
SHOP = "אקוויפ"

# equipment key → (our name, their Hebrew name, pack size, ₪, in stock, url)
#
# The `key` matches app/engine/equipment.py so the planner can find a price for
# each slot. An item with no row here is reported as unpriced, not skipped.
EQUIPMENT = [
    ("shaker", "Bartender kit (contains shaker)", "ציוד מקצועי לברמן",
     1, 130.0, True,
     "https://equip-online.co.il/product/3453078-ציוד-מקצועי-לברמן-לבר-להכנת-משקאות-אל/"),
    ("shaker_alt_tin", "Tin-tin shaker", "שייקר טין טין לבר כסף מאט",
     1, 37.0, False,
     "https://equip-online.co.il/product/שייקר-טין-טין-לבר-כסף-מאט/"),
    ("shaker_alt_750", "Cocktail shaker 750ml", "שייקר לקוקטייל 750 מ\"ל נירוסטה",
     1, 30.0, False,
     "https://equip-online.co.il/product/1990593-שייקר-לקוקטייל-750-מ-ל-נירוסטה-אזל-במלאי/"),
    ("jigger", "Jigger", "ג'יגר נירוסטה איכותי",
     1, 6.0, True,
     "https://equip-online.co.il/product/1990586-ג-יגר-נירוסטה-איכותי/"),
    ("strainer", "Strainer", "מסננת לשייקר/קוקטייל ספירלה",
     1, 14.0, True,
     "https://equip-online.co.il/product/1990589-מסננת-לשייקר-קוקטייל-ספירלה/"),
    ("bar_spoon", "Bar spoon", "כפית קוקטייל לבר",
     1, 9.0, True,
     "https://equip-online.co.il/product/כפית-קוקטייל-לבר/"),
    ("muddler", "Muddler", "כותש קרח / לימון מקל מפלסטיק 23 ס\"מ",
     1, 28.0, True,
     "https://equip-online.co.il/product/1990604-כותש-קרח-לימון-מקל-מפלסטיק-23-ס-מ/"),
    # Glassware: packs of six, which is the whole reason the planner counts packs.
    ("glass_rocks", "Rocks glasses (6)", "סט 6 כוסות וויסקי 250 מ\"ל ISTANBUL",
     6, 25.0, True,
     "https://equip-online.co.il/product/סט-6-כוסות-שתייה-וויסקי-250-מל-זכוכית-istanbul/"),
    ("glass_highball", "Highball glasses (6)", "סט 6 כוסות לונג 290 מ\"ל ISTANBUL",
     6, 20.0, True,
     "https://equip-online.co.il/product/כוס-לונג-290-מל-זכוכית-istanbul/"),
    ("glass_martini", "Martini glasses (6)", "סט 6 כוסות מרטיני 230 מ\"ל TIMELESS",
     6, 89.0, True,
     "https://equip-online.co.il/product/סט-6-כוסות-מרטיני-230-מל-timeless/"),
    ("glass_martini_pc", "Martini glasses, unbreakable (6)",
     "סט 6 כוס מרטיני 275 מ\"ל פוליקרבונט",
     6, 92.0, True,
     "https://equip-online.co.il/product/1991277-כוס-מרטיני-280-ס-ל-פוליקרבונט/"),
    ("ice_bucket", "Ice bucket", "דלי לקרח נירוסטה + טבעות", 1, 18.0, True, None),
    ("ice_tongs", "Ice tongs", "מלקחיים לקרח 16 ס\"מ", 1, 6.0, True, None),
    ("ice_scoop", "Ice scoop", "כף לקרח נירוסטה 24 ס\"מ", 1, 14.0, True, None),
]

# Needed by the default kit, sold by nobody who publishes a price.
UNPRICED = {
    "Pourers": "EQUIP does not stock them; קוקטייל ארט has them but quotes no price.",
    "Ice trays / moulds": "Not stocked at EQUIP. Ice handling tools are, and are loaded.",
    "Bar mats": "Not stocked at EQUIP.",
    "Coupe glasses": "Not at EQUIP. קוקטייל ארט sells them singly, price on enquiry — "
                     "singly would suit odd headcounts better than packs of six.",
}

SHOP_TERMS = {
    "free_delivery_over": 299.0,
    "delivery_fee": 55.0,
    "delivery_note": (
        "Free over ₪299, otherwise ₪55. Open to private customers with a card. "
        "One category page's search snippet mentioned a ₪500 threshold — that page "
        "was not loaded, so confirm by phone before relying on ₪299 for a large "
        "equipment order."
    ),
    "search_url_template": "https://equip-online.co.il/?s={query}&post_type=product",
}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    done = []

    async with AsyncSessionLocal() as db:
        supplier = (await db.execute(
            select(Supplier).where(Supplier.name == SHOP)
        )).scalars().first()
        if supplier is None:
            print(f"✗ no supplier named {SHOP!r} — run add_suppliers_2026_08.py first")
            return 1
        if args.apply:
            supplier.free_delivery_over = SHOP_TERMS["free_delivery_over"]
            supplier.delivery_fee = SHOP_TERMS["delivery_fee"]
            supplier.delivery_note = SHOP_TERMS["delivery_note"]
            supplier.search_url_template = SHOP_TERMS["search_url_template"]

        for key, our, theirs, pack, price, stock, url in EQUIPMENT:
            # Equipment lives beside drinks as a Product, so it can be costed,
            # linked and compared by the machinery that already exists. The
            # `equipment:` prefix on the ingredient keeps it out of every recipe
            # query, which all filter on cocktails.
            ing_name = f"equipment:{key}"
            ing = (await db.execute(
                select(Ingredient).where(Ingredient.canonical_name == ing_name)
            )).scalars().first()
            if ing is None:
                ing = Ingredient(canonical_name=ing_name, category="equipment",
                                 unit_type="unit", alcoholic=False)
                if args.apply:
                    db.add(ing)
                    await db.flush()

            product = (await db.execute(
                select(Product).where(Product.name == theirs)
            )).scalars().first()
            if product is None:
                product = Product(name=theirs, brand=our, package_size=pack,
                                  package_unit="unit",
                                  ingredient_id=ing.id if args.apply else None,
                                  notes=f"Workshop equipment · {key}")
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
                listing.package_size = pack
                listing.package_unit = "unit"
                listing.price_after_vat = price
                listing.price_before_vat = round(price / (1 + VAT), 2)
                listing.vat_rate = VAT
                listing.is_historical = False
                listing.available = stock
                listing.product_url = url
                listing.last_checked_at = now

                mapping = (await db.execute(
                    select(IngredientProductMapping).where(
                        IngredientProductMapping.ingredient_id == ing.id,
                        IngredientProductMapping.product_id == product.id)
                )).scalars().first()
                if mapping is None:
                    db.add(IngredientProductMapping(
                        ingredient_id=ing.id, product_id=product.id,
                        preferred=True, substitution_allowed=True,
                        substitution_priority=1))

            done.append((key, our, pack, price, stock))

        if args.apply:
            await db.commit()

    print(f"{len(done)} equipment item(s) at {SHOP}\n")
    for key, our, pack, price, stock in done:
        per = f"  (₪{price / pack:.2f} each)" if pack > 1 else ""
        mark = "" if stock else "   ← out of stock"
        print(f"  {key:<18} {our:<34} ₪{price:>6.2f} / {pack}{per}{mark}")
    print(f"\n{len(UNPRICED)} item(s) the default kit wants that nobody prices:")
    for name, why in UNPRICED.items():
        print(f"  · {name}: {why}")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

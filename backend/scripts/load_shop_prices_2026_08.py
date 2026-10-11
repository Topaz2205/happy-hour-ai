"""
Prices from two Israeli shops, so a basket can be compared.

    python scripts/load_shop_prices_2026_08.py [--apply]

WHAT IS HERE
------------
Only figures read off a product page that was actually loaded. The research
also produced category-listing figures for other items; those are deliberately
excluded, because listing pages rendered every size as "700ml" — including for
bottles that are demonstrably 1L — and a size that is wrong by 30% produces a
per-ml cost that is wrong by 30%.

THE SIZES ARE PER SHOP, AND THAT IS THE POINT
---------------------------------------------
Aperol and Campari are not sold in 700ml by either shop; both stock only 1L.
Jack Daniel's and Grey Goose are 1L at one shop and 700ml at the other. Our
product records said 700ml for all four. A single size on the Product cannot
describe that, which is why SupplierProduct now carries its own size — and why
each row below states the size that shop actually sells.

VAT
---
Neither shop states VAT anywhere. Israeli consumer prices are legally shown
inclusive of it, so these are recorded as price_after_vat at the current rate.
That is an inference about Israeli retail law, not about these shops, and it is
written down here rather than left implicit.

NOT FOUND IS RECORDED TOO
-------------------------
The bottom of this file lists what neither shop stocks. A gap that is written
down can be filled; a gap that is silently skipped looks like a product nobody
needed.
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
from app.models import Product, Supplier
from app.models.supplier import SupplierProduct

VAT = settings.DEFAULT_VAT_RATE

# Shop delivery terms, as published. None means the shop does not publish it —
# never a stand-in figure.
SHOPS = {
    "משקאות המשמח": {
        "free_delivery_over": 399.0,
        "delivery_fee": 35.0,
        "delivery_note": (
            "Free over ₪399, otherwise ₪35. The published clause qualifies the "
            "threshold with 'מחוץ לירושלים' (outside Jerusalem) — the Jerusalem "
            "case was not resolved and should be confirmed before it is relied on."
        ),
        "search_url_template": "https://www.hamesameach.co.il/?s={query}&post_type=product",
    },
    "עולם היין": {
        "free_delivery_over": 299.0,
        "delivery_fee": None,     # not published anywhere; appears only at checkout
        "delivery_note": (
            "Free over ₪299. The charge below that is NOT published. Separately, "
            "orders above twelve bottles incur an additional per-case fee whose "
            "amount is also unpublished — and an event order passes twelve "
            "bottles routinely, so 'free over ₪299' cannot be treated as an "
            "unconditional zero for this use."
        ),
        "search_url_template": "https://olamhayain.co.il/?s={query}&post_type=product",
    },
}

# (our product name, shop, their name, size, unit, price ₪, url path)
PRICES = [
    # ── משקאות המשמח ────────────────────────────────────────────────────
    ("בומביי", "משקאות המשמח", "ג'ין בומביי ספייר", 700, "ml", 119.0,
     "https://www.hamesameach.co.il/product/גין-בומביי-ספייר/"),
    ("גק' דניאלס", "משקאות המשמח", "ג'ק דניאלס ליטר", 1000, "ml", 149.0,
     "https://www.hamesameach.co.il/product/גק-דניאלס-ליטר/"),
    ("גרייגוס", "משקאות המשמח", "גריי גוס 1 ליטר", 1000, "ml", 169.0,
     "https://www.hamesameach.co.il/product/גריי-גוס-1-ליטר/"),
    ("Cognac VS", "משקאות המשמח", "קוניאק רולנד ברו VS כשר", 700, "ml", 149.0,
     "https://www.hamesameach.co.il/product/קוניאק-רולנד-ברו-vs-כשר/"),
    ("אפרול", "משקאות המשמח", "אפרול ליטר", 1000, "ml", 95.0,
     "https://www.hamesameach.co.il/product/אפרול-ליטר/"),
    ("קמפרי", "משקאות המשמח", "קמפרי ליטר", 1000, "ml", 95.0,
     "https://www.hamesameach.co.il/product/קמפרי-ליטר/"),
    ("Fernet Branca", "משקאות המשמח", "פרנה ברנקה במארז", 700, "ml", 109.0,
     "https://www.hamesameach.co.il/product/פרנה-ברנקה-במארז/"),
    ("Green Chartreuse", "משקאות המשמח", "שרטרז ירוק", 700, "ml", 359.0,
     "https://www.hamesameach.co.il/product/שרטרז-ירוק/"),
    ("קאווה איבריקה", "משקאות המשמח", "קאווה ויברסיונס יבש", 750, "ml", 39.0,
     "https://www.hamesameach.co.il/product/קאווה-ויברסיונס-יבש/"),

    # ── עולם היין ───────────────────────────────────────────────────────
    ("בומביי", "עולם היין", "ג'ין בומביי ספיר 0.7", 700, "ml", 109.0,
     "https://olamhayain.co.il/product/ג'ין-בומביי-ספיר/"),
    ("גק' דניאלס", "עולם היין", "וויסקי ג'ק דניאלס 0.7", 700, "ml", 113.0,
     "https://olamhayain.co.il/product/וויסקי-ג'ק-דניאלס-0.7/"),
    ("גרייגוס", "עולם היין", "וודקה גריי גוס 0.7", 700, "ml", 119.0,
     "https://olamhayain.co.il/product/וודקה-גריי-גוס-0-7/"),
    ("Cognac VS", "עולם היין", "קוניאק טיפון VS", 700, "ml", 107.0,
     "https://olamhayain.co.il/product/קוניאק-טיפון-vs/"),
    ("אפרול", "עולם היין", "ליקר אפרול ליטר", 1000, "ml", 77.0,
     "https://olamhayain.co.il/product/ליקר-אפרול-ליטר/"),
    ("קמפרי", "עולם היין", "קמפרי ליטר", 1000, "ml", 80.0,
     "https://olamhayain.co.il/product/קמפרי-ליטר/"),
    ("Fernet Branca", "עולם היין", "ליקר פרנט בראנקה", 700, "ml", 104.0,
     "https://olamhayain.co.il/product/ליקר-פרנט-בראנקה/"),
    ("Green Chartreuse", "עולם היין", "ליקר שרטרז ירוק 0.7", 700, "ml", 299.0,
     "https://olamhayain.co.il/product/ליקר-שרטרז-ירוק-0-7/"),
    ("Luxardo Maraschino", "עולם היין", "ליקר לוקסרדו מרסקינו", 700, "ml", 128.0,
     "https://olamhayain.co.il/product/ליקר-מרסקינו-לוקסרדו/"),
    ("Red Vermouth", "עולם היין", "וורמוט מרטיני רוסו ליטר", 1000, "ml", 50.0,
     "https://olamhayain.co.il/product/וורמוט-מרטיני-רוסו-ליטר/"),
    ("אנגוסטורה ביטרס", "עולם היין", "ביטר אנגוסטורה 0.2", 200, "ml", 89.0,
     "https://olamhayain.co.il/product/ביטר-אנגוסטורה-0-2/"),
    ("קאווה איבריקה", "עולם היין", "מבעבע קאווה ג'אום סרה ברוט", 750, "ml", 31.5,
     "https://olamhayain.co.il/product/מבעבע-קאווה-ג'אום-סרה-ברוט/"),
]

# Neither shop stocks these. Written down so the gap is visible.
NOT_STOCKED = {
    "Olmeca Silver Tequila": "Neither shop sells plain Olmeca Silver. Both carry "
                             "Olmeca Altos Plata, a higher tier and a different "
                             "product — not substituted.",
    "רום קאנוקה": "Not stocked at either. Other white rums exist at both; "
                  "choosing one is a recipe decision, not an import decision.",
    "Dry Curacao Pierre Ferrand": "Neither stocks it. One carries blue curaçao, "
                                  "which is a different thing.",
    "Crème de Cacao": "Not stocked at either.",
    "Mancino Bianco Vermouth": "Not stocked; other bianco vermouths available.",
    "Mancino Secco Dry Vermouth": "Not stocked; Dolin dry available at one shop.",
    "Kina L'Aero D'Or": "Not stocked at either.",
    "Orange Bitters": "Angostura Orange found at 100ml/₪52 — but our record is "
                      "in dashes, not ml, so the conversion is a judgement "
                      "nobody has made yet. Left unpriced rather than guessed.",
    "סודה": "Neither shop sells plain soda water.",
    "Ginger Beer": "Fever-Tree 200ml singles at ₪7 exist at one shop, but our "
                   "record is a 4,800ml case. Different pack; not merged.",
}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    added, updated, missing = [], [], []

    async with AsyncSessionLocal() as db:
        for name, terms in SHOPS.items():
            sup = (await db.execute(
                select(Supplier).where(Supplier.name == name)
            )).scalars().first()
            if sup is None:
                print(f"  ! no supplier {name!r} — run add_suppliers first")
                continue
            if args.apply:
                sup.free_delivery_over = terms["free_delivery_over"]
                sup.delivery_fee = terms["delivery_fee"]
                sup.delivery_note = terms["delivery_note"]
                sup.search_url_template = terms["search_url_template"]

        for our_name, shop, their_name, size, unit, price, url in PRICES:
            product = (await db.execute(
                select(Product).where(Product.name == our_name)
            )).scalars().first()
            supplier = (await db.execute(
                select(Supplier).where(Supplier.name == shop)
            )).scalars().first()
            if product is None or supplier is None:
                missing.append(f"{our_name} @ {shop}")
                continue

            listing = (await db.execute(
                select(SupplierProduct).where(
                    SupplierProduct.product_id == product.id,
                    SupplierProduct.supplier_id == supplier.id)
            )).scalars().first()

            flag = "≠" if product.package_size and float(product.package_size) != size else " "
            (updated if listing else added).append(
                f"{flag} {shop:<14} {their_name[:30]:<30} {size:>5.0f}{unit} ₪{price:>7.2f}")

            if not args.apply:
                continue
            if listing is None:
                listing = SupplierProduct(supplier_id=supplier.id, product_id=product.id)
                db.add(listing)
            listing.package_size = size
            listing.package_unit = unit
            listing.price_after_vat = price
            listing.price_before_vat = round(price / (1 + VAT), 2)
            listing.vat_rate = VAT
            listing.is_historical = False
            listing.available = True
            listing.product_url = url
            listing.last_checked_at = now

        if args.apply:
            await db.commit()

    for line in added + updated:
        print(line)
    print(f"\n{len(added)} new listing(s), {len(updated)} updated, {len(missing)} unmatched")
    print("≠ marks a shop size that differs from our product record — the shop's wins.")
    if missing:
        print("\nUnmatched (product name not in the database):")
        for m in missing:
            print(f"  · {m}")
    print(f"\n{len(NOT_STOCKED)} item(s) neither shop stocks — see NOT_STOCKED in this file.")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

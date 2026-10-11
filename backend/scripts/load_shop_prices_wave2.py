"""
Prices from five more shops, so the comparison has something to compare.

    python scripts/load_shop_prices_wave2.py [--apply]

Researched 27 Aug 2026 across Paneco, שר המשקאות, בנא משקאות, יין בעיר אקספרס
and בית המשקאות של נפתלי, on top of the two loaded earlier.

WHAT IS HERE AND WHAT IS NOT
----------------------------
Only prices read off a page that was actually loaded. Where a shop's own
listing and its product page disagreed, the product page won. Items that are
out of stock are loaded with available=False rather than dropped: the price is
real and useful for comparison, but the engine must not plan an order around a
bottle nobody can send.

SIZES ARE PER SHOP
------------------
Aperol and Campari are 1L almost everywhere and never 700ml. Jack Daniel's,
Grey Goose and Bombay come in both, at different prices, in different shops.
Each row states the size that shop sells, and the cost engine divides by that —
not by a nominal size on the product record.

TWO THINGS THE RESEARCH FOUND THAT ARE NOT PRICES
-------------------------------------------------
1. Delivery is not a simple threshold at most of these shops. שר המשקאות gives
   free delivery over ₪299 *only if the order fits one box of twelve bottles*
   and does not publish what a thirteenth costs. עולם היין has an unpublished
   per-case surcharge above twelve. An event order passes twelve routinely, so
   for those shops the delivered total is genuinely unknown and is recorded as
   unknown.
2. בית המשקאות של נפתלי lists Aperol and Campari as 100ml at ₪99 and ₪108 —
   full-bottle prices on a 100ml label. That is almost certainly their
   catalogue error, but "almost certainly" is not good enough to put in a cost
   model, so both are left out entirely with the reason recorded below.
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

# name → (free_over, fee_below, note). None where the shop does not publish it.
SHOPS = {
    "Paneco": (299.0, 19.90,
               "Free over ₪299, otherwise ₪19.90. Orders of 28+ bottles are routed "
               "to a scheduled courier tier, still free over ₪299. No per-case "
               "surcharge found — the most predictable of the shops researched."),
    "שר המשקאות": (299.0, 35.0,
                   "Free over ₪299 BUT only while the order fits one box of up to "
                   "12 bottles. What a 13th bottle costs is NOT published, and an "
                   "event order passes 12 routinely — so the delivered total is "
                   "unknown for this shop. ₪35 Gush Dan / ₪45 outside below the "
                   "threshold, plus ₪20 per floor with no lift."),
    "בנא משקאות": (299.9, 29.90,
                   "Free over ₪299.90, otherwise ₪29.90 per box (~12 bottles). "
                   "Crucially, ₪29.90 for EACH additional box beyond 12kg — which "
                   "is published, so a large order here is actually predictable. "
                   "Beer, cider and soft drinks are excluded from free shipping."),
    "יין בעיר אקספרס": (400.0, 35.0,
                        "₪35 up to ₪399, free from ₪400. No per-case surcharge "
                        "published. Boutique import list — does not stock the "
                        "mainstream well brands."),
    "בית המשקאות של נפתלי": (350.0, None,
                             "A homepage banner states free delivery from ₪350, "
                             "read once and not re-confirmed — treat as "
                             "provisional. The fee below it, any minimum and any "
                             "large-order surcharge are not published on any "
                             "crawlable page. Phone 03-7316022 before quoting."),
}

# our product, shop, their name, size, unit, ₪, in stock, url
PRICES = [
    # ── Paneco ──────────────────────────────────────────────────────────
    ("בומביי", "Paneco", "בומביי ספייר ליטר 40% כשר", 1000, "ml", 135.0, False,
     "https://www.paneco.co.il/gin"),
    ("גק' דניאלס", "Paneco", "ג'ק דניאלס", 700, "ml", 109.90, True,
     "https://www.paneco.co.il/jack-daniels-black-label"),
    ("גרייגוס", "Paneco", "גריי גוס ליטר כשר", 1000, "ml", 139.0, True,
     "https://www.paneco.co.il/01-00259"),
    ("אפרול", "Paneco", "אפרול ליטר כשר", 1000, "ml", 79.90, True,
     "https://www.paneco.co.il/aperol-1l"),
    ("קמפרי", "Paneco", "קמפרי ליטר כשר", 1000, "ml", 84.90, True,
     "https://www.paneco.co.il/campari-bitters-1l"),
    ("Fernet Branca", "Paneco", "פרנה ברנקה", 700, "ml", 99.0, False,
     "https://www.paneco.co.il/liqueur"),
    ("Green Chartreuse", "Paneco", "ליקר שרטרז ירוק", 700, "ml", 299.0, True,
     "https://www.paneco.co.il/liqueur"),
    ("Red Vermouth", "Paneco", "מרטיני רוסו כשר ליטר", 1000, "ml", 54.0, True,
     "https://www.paneco.co.il/liqueur"),
    ("אנגוסטורה ביטרס", "Paneco", "אנגוסטורה ארומטיק ביטרס", 200, "ml", 79.0, False,
     "https://www.paneco.co.il/angostura-bitters"),
    ("קאווה איבריקה", "Paneco", "ג'אום סרה קאווה ברוט", 750, "ml", 38.0, True,
     "https://www.paneco.co.il/76-10120"),

    # ── שר המשקאות ──────────────────────────────────────────────────────
    ("בומביי", "שר המשקאות", "ג'ין בומביי 700 מ\"ל", 700, "ml", 109.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=683"),
    ("גק' דניאלס", "שר המשקאות", "וויסקי ג'ק דניאלס 700 מ\"ל", 700, "ml", 119.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=1109"),
    ("גרייגוס", "שר המשקאות", "וודקה גריי גוס 700 מ\"ל", 700, "ml", 135.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=19372"),
    ("Olmeca Silver Tequila", "שר המשקאות", "טקילה אולמקה בלאנקו 700 מ\"ל", 700, "ml", 105.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=3652"),
    ("Cognac VS", "שר המשקאות", "קוניאק נאולין VS 700 מ\"ל", 700, "ml", 129.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=17484"),
    ("אפרול", "שר המשקאות", "ליקר אפרול ליטר", 1000, "ml", 79.0, True,
     "https://mashkaot.co.il/index.php?cs=9411&dir=site&op=item&page=catalog"),
    ("קמפרי", "שר המשקאות", "קמפרי ליטר", 1000, "ml", 85.0, True,
     "https://mashkaot.co.il/index.php?cs=7964&dir=site&op=item&page=catalog"),
    ("Fernet Branca", "שר המשקאות", "פרנה ברנקה 700 מ\"ל", 700, "ml", 110.0, True,
     "https://mashkaot.co.il/index.php?cs=1346&dir=site&op=item&page=catalog"),
    ("Green Chartreuse", "שר המשקאות", "ליקר שרטרז ירוק 700 מ\"ל", 700, "ml", 299.0, True,
     "https://mashkaot.co.il/index.php?cs=601&dir=site&op=item&page=catalog"),
    ("Luxardo Maraschino", "שר המשקאות", "לוקסרדו מרסקינו 700 מ\"ל", 700, "ml", 119.0, True,
     "https://mashkaot.co.il/index.php?cs=14294&dir=site&op=item&page=catalog"),
    ("Red Vermouth", "שר המשקאות", "מרטיני רוסו", 1000, "ml", 59.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=7864"),
    ("אנגוסטורה ביטרס", "שר המשקאות", "אנגוסטורה ארומטיק ביטרס 200 מ\"ל", 200, "ml", 95.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=1923"),
    ("קאווה איבריקה", "שר המשקאות", "קאווה פרקשנט כרטה נבדה 750 מ\"ל", 750, "ml", 60.0, True,
     "https://www.mashkaot.co.il/index.php?dir=site&page=catalog&op=item&cs=6429"),

    # ── בנא משקאות ──────────────────────────────────────────────────────
    ("בומביי", "בנא משקאות", "ג'ין בומביי ספייר ליטר", 1000, "ml", 124.90, True,
     "https://www.banamashkaot.co.il/product-category/אלכוהול/גין/"),
    ("גק' דניאלס", "בנא משקאות", "וויסקי ג'ק דניאלס 700 מ\"ל", 700, "ml", 114.90, True,
     "https://www.banamashkaot.co.il/brands/גק-דניאלס/"),
    ("גרייגוס", "בנא משקאות", "וודקה גריי גוס ליטר", 1000, "ml", 134.90, True,
     "https://www.banamashkaot.co.il/product/וודקה-גריי-גוס-ליטר/"),
    ("Olmeca Silver Tequila", "בנא משקאות", "טקילה אולמקה בלאנקו 700 מ\"ל", 700, "ml", 126.90, True,
     "https://www.banamashkaot.co.il/product/טקילה-אולמקה-בלאנקו-700-מל/"),
    ("Cognac VS", "בנא משקאות", "קוניאק הנסי VS 700 מ\"ל", 700, "ml", 139.90, True,
     "https://www.banamashkaot.co.il/product-category/אלכוהול/קוניאק/"),
    ("אפרול", "בנא משקאות", "אפרול ליטר", 1000, "ml", 79.90, True,
     "https://www.banamashkaot.co.il/product/אפרול-ליטר/"),
    ("קמפרי", "בנא משקאות", "קמפרי ליטר", 1000, "ml", 84.90, True,
     "https://www.banamashkaot.co.il/product/קמפרי-ליטר/"),
    ("Fernet Branca", "בנא משקאות", "ליקר פרנה ברנקה 700 מ\"ל", 700, "ml", 109.90, True,
     "https://www.banamashkaot.co.il/product/ליקר-פרנה-ברנקה-700-מל/"),
    ("Green Chartreuse", "בנא משקאות", "ליקר שרטרז ירוק 700 מ\"ל", 700, "ml", 329.90, True,
     "https://www.banamashkaot.co.il/product/ליקר-שרטרז-ירוק-700-מל/"),
    ("Luxardo Maraschino", "בנא משקאות", "ליקר לוקסרדו מרסקינו כשר 700 מ\"ל", 700, "ml", 119.90, True,
     "https://www.banamashkaot.co.il/product/ליקר-לוקסרדו-מרסקינו-כשר-700-מל/"),
    ("Red Vermouth", "בנא משקאות", "ורמוט גנציה רוסו ליטר", 1000, "ml", 37.90, True,
     "https://www.banamashkaot.co.il/product-category/אלכוהול/ליקר-אלכוהול/ורמוט/"),
    ("אנגוסטורה ביטרס", "בנא משקאות", "אנגוסטורה ביטרס 200 מ\"ל", 200, "ml", 75.0, True,
     "https://www.banamashkaot.co.il/product/אנגוסטורה-ביטרס-200-מל/"),
    ("קאווה איבריקה", "בנא משקאות", "קאווה איבריקה יבש", 750, "ml", 35.0, True,
     "https://www.banamashkaot.co.il/product-category/יין/יין-מבעבע/קאווה-יין-מבעבע/"),

    # ── יין בעיר אקספרס ─────────────────────────────────────────────────
    ("Cognac VS", "יין בעיר אקספרס", "קוניאק הנרי מונייר VS", 700, "ml", 155.0, True,
     "https://wine-direct.co.il/product/קוניאק-הנרי-מונייר-vs/"),
    ("אפרול", "יין בעיר אקספרס", "אפרול אפריטיבו ליטר", 1000, "ml", 95.0, True,
     "https://wine-direct.co.il/product/אפרול/"),
    ("Fernet Branca", "יין בעיר אקספרס", "פרנט ברנקה", 700, "ml", 99.0, True,
     "https://wine-direct.co.il/product/פרנט-ברנקה/"),
    ("Green Chartreuse", "יין בעיר אקספרס", "ליקר שרטרז ירוק", 700, "ml", 315.0, True,
     "https://wine-direct.co.il/product/ליקר-שרטרז-ירוק/"),

    # ── בית המשקאות של נפתלי ────────────────────────────────────────────
    ("Fernet Branca", "בית המשקאות של נפתלי", "פרנט בראנקה", 700, "ml", 115.0, True,
     "https://www.goodwines.co.il/product/פרנט-ברנקה"),
    ("Green Chartreuse", "בית המשקאות של נפתלי", "ליקר שרטרז ירוק", 700, "ml", 356.0, True,
     "https://www.goodwines.co.il/product/ליקר-שרטרז-ירוק"),
    ("אנגוסטורה ביטרס", "בית המשקאות של נפתלי", "אנגוסטורה ביטרס", 200, "ml", 79.90, True,
     "https://www.goodwines.co.il/product/אנגוסטורה"),
    ("קאווה איבריקה", "בית המשקאות של נפתלי", "קאווה קסניוס", 750, "ml", 42.0, True,
     "https://www.goodwines.co.il/product/קאווה-קסניוס"),
]

# Found but deliberately NOT loaded, with the reason.
WITHHELD = {
    "Aperol @ בית המשקאות של נפתלי":
        "Their page states 100ml at ₪99 — a full-bottle price on a 100ml label. "
        "Almost certainly their catalogue error, but 'almost certainly' does not "
        "belong in a cost model. Phone to confirm the volume.",
    "Campari @ בית המשקאות של נפתלי":
        "Same problem: 100ml at ₪108.",
    "Campari @ יין בעיר אקספרס":
        "A search snippet mentions ₪99 for club members, but the product page "
        "404'd twice and the item is absent from the bitter category. Unverified.",
    "White rum, everywhere":
        "Every shop stocks a white rum, but they are different brands — Bacardi, "
        "Captain Morgan, Caribica, Negrita. Which one belongs in a daiquiri is a "
        "recipe decision, not an import decision, so none was mapped to our "
        "Havana Club record.",
}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    done, unmatched = [], []

    async with AsyncSessionLocal() as db:
        for shop, (free_over, fee, note) in SHOPS.items():
            sup = (await db.execute(
                select(Supplier).where(Supplier.name == shop)
            )).scalars().first()
            if sup is None:
                sup = Supplier(name=shop, is_retailer=True, prefers_hebrew_query=True)
                if args.apply:
                    db.add(sup)
                    await db.flush()
            if args.apply:
                sup.free_delivery_over = free_over
                sup.delivery_fee = fee
                sup.delivery_note = note
                sup.is_retailer = True

        for our, shop, theirs, size, unit, price, in_stock, url in PRICES:
            product = (await db.execute(
                select(Product).where(Product.name == our)
            )).scalars().first()
            supplier = (await db.execute(
                select(Supplier).where(Supplier.name == shop)
            )).scalars().first()
            if product is None or supplier is None:
                unmatched.append(f"{our} @ {shop}")
                continue

            listing = (await db.execute(
                select(SupplierProduct).where(
                    SupplierProduct.product_id == product.id,
                    SupplierProduct.supplier_id == supplier.id)
            )).scalars().first()
            done.append((shop, our, size, price, in_stock))

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
            # Out of stock keeps its price but must not be planned around.
            listing.available = in_stock
            listing.product_url = url
            listing.last_checked_at = now

        if args.apply:
            await db.commit()

    by_product: dict[str, list] = {}
    for shop, our, size, price, in_stock in done:
        by_product.setdefault(our, []).append((shop, size, price, in_stock))

    for our, rows in sorted(by_product.items()):
        print(f"\n{our}")
        for shop, size, price, in_stock in sorted(rows, key=lambda r: r[2] / r[1]):
            mark = "" if in_stock else "  (out of stock)"
            print(f"   {shop:<24} {size:>5.0f}ml  ₪{price:>7.2f}   "
                  f"{price / size * 1000:>6.1f} ₪/L{mark}")

    print(f"\n{len(done)} listing(s) across {len(SHOPS)} shop(s).")
    if unmatched:
        print(f"{len(unmatched)} unmatched: " + ", ".join(unmatched))
    print(f"{len(WITHHELD)} finding(s) deliberately withheld — see WITHHELD.")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

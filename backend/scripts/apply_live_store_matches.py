"""
Happy Hour AI — import verified live retail matches.

Input:
    data/relevant_store_matches_ready.json

Only complete, high-confidence listings are imported.

Creates/updates:
- Product
- IngredientProductMapping (preferred=False)
- SupplierProduct

Usage:
    python scripts/apply_live_store_matches.py
    python scripts/apply_live_store_matches.py --apply
"""

import argparse
import asyncio
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import (
    Ingredient,
    IngredientProductMapping,
    Product,
    Supplier,
    SupplierProduct,
)

SOURCE = Path("data/relevant_store_matches_ready.json")
BATCH = "targeted-live-retail-2026-09-03"


def norm(value):
    value = html.unescape(str(value or "")).lower()
    value = (
        value
        .replace("״", '"')
        .replace("׳", "'")
        .replace("’", "'")
    )
    return " ".join(
        re.sub(
            r"[^a-z0-9\u0590-\u05ff]+",
            " ",
            value,
        ).split()
    )


REJECT = {
    "Angostura Aromatic Bitters": [
        "cocoa", "cacao", "קקאו",
        "orange", "אורנג", "תפוז",
        "rum", "רום",
    ],
    "Beefeater London Dry Gin": [
        "beefeater 24", "ביפיטר 24",
        "pink", "פינק", "תות",
    ],
    "Beluga Noble Vodka": [
        "gold", "גולד",
        "trans atlantic", "טרנס אטלנטיק",
        "adriatic", "אדריאטיק",
        "botanical", "בוטניקל",
        "miniature", "מיניאטורה",
    ],
    "Campari": [
        "spritz", "שפריץ",
        "soda", "סודה",
        "negroni", "נגרוני",
    ],
    "Cognac VS": [
        "vsop",
        "xo",
        "reserve", "רזרב",
        "napoleon", "נפוליאון",
    ],
    "Dry Curacao Pierre Ferrand": [
        "cognac", "קוניאק",
        "reserve", "רזרב",
        "selection", "סלקסיון",
    ],
    "Fernet Branca": [
        "mint", "menta", "מנטה",
    ],
    "Four Roses Bourbon": [
        "small batch", "סמול באץ",
        "single barrel", "סינגל בארל",
    ],
    "Fresh Lemon Juice": [
        "ליים",
    ],
    "Green Chartreuse": [
        "yellow", "צהוב",
    ],
    "Havana Club Añejo 3 Años Rum": [
        "7 years", "7 שנים",
        "anejo 7", "אנייחו 7",
        "especial", "אספסיאל",
    ],
    "Mancino Secco Dry Vermouth": [
        "rosso", "רוסו",
        "glasses", "כוסות",
    ],
    "Olmeca Silver Tequila": [
        "gold", "גולד",
        "anejo", "אנייחו",
        "altos", "אלטוס",
    ],
    "Soda Water": [
        "campari", "קמפרי",
    ],
}


def contains_any(text, words):
    n = norm(text)
    return any(norm(word) in n for word in words)


def safe_variant(ingredient, product):
    if contains_any(
        product,
        REJECT.get(ingredient, []),
    ):
        return False

    n = f" {norm(product)} "

    if ingredient == "Havana Club Añejo 3 Años Rum":
        if not any(
            x in n
            for x in (
                " 3 שנים ",
                " 3yo ",
                " club3yo ",
                " havana club 3 ",
                " הוואנה קלאב 3 ",
            )
        ):
            return False

    if ingredient == "Olmeca Silver Tequila":
        if not any(
            x in n
            for x in (
                " silver ",
                " סילבר ",
            )
        ):
            return False

    if ingredient == "Green Chartreuse":
        if not any(
            x in n
            for x in (
                " green ",
                " ירוק ",
            )
        ):
            return False

    if ingredient == "Cognac VS":
        # VSOP must never be treated as VS.
        if " vsop " in n:
            return False

        if not any(
            x in n
            for x in (
                " vs ",
                " וי אס ",
            )
        ):
            return False

    return True


def total_package_size(product, size):
    """
    Correct multipacks.

    If enrichment found 200ml on a "24 units" product,
    the listed price is for 24 × 200ml = 4800ml.
    """

    size = float(size)
    n = norm(product)

    if size > 2000:
        return size

    count = None

    for pattern in (
        r"\b(\d{1,2})\s*יח\b",
        r"\b(\d{1,2})\s*יחידות\b",
        r"\bpack\s*(?:of\s*)?(\d{1,2})\b",
        r"\bbox\s*(?:of\s*)?(\d{1,2})\b",
    ):
        m = re.search(pattern, n)

        if m:
            count = int(m.group(1))
            break

    if count and count > 1:
        return size * count

    return size


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually write verified matches to PostgreSQL.",
    )
    args = ap.parse_args()

    if not SOURCE.exists():
        raise SystemExit(
            f"❌ Missing {SOURCE}"
        )

    data = json.loads(
        SOURCE.read_text()
    )

    candidates = []
    skipped_missing = []
    skipped_variant = []

    for row in data["ingredients"]:
        ingredient_id = row["ingredient_id"]
        ingredient_name = row["ingredient"]

        for store_name, matches in row["stores"].items():

            for match in matches:
                price = match.get("price")
                size = match.get("package_size_ml")
                url = match.get("url")
                product = str(
                    match.get("product") or ""
                ).strip()

                if (
                    not product
                    or not url
                    or price is None
                    or size is None
                ):
                    skipped_missing.append(
                        (
                            ingredient_name,
                            store_name,
                            product,
                        )
                    )
                    continue

                try:
                    price = float(price)
                    size = total_package_size(
                        product,
                        size,
                    )
                except Exception:
                    skipped_missing.append(
                        (
                            ingredient_name,
                            store_name,
                            product,
                        )
                    )
                    continue

                if (
                    price <= 0
                    or price > 5000
                    or size < 100
                    or size > 50000
                ):
                    skipped_missing.append(
                        (
                            ingredient_name,
                            store_name,
                            product,
                        )
                    )
                    continue

                if not safe_variant(
                    ingredient_name,
                    product,
                ):
                    skipped_variant.append(
                        (
                            ingredient_name,
                            store_name,
                            product,
                        )
                    )
                    continue

                candidates.append(
                    {
                        "ingredient_id": ingredient_id,
                        "ingredient": ingredient_name,
                        "store": store_name,
                        "product": product[:255],
                        "price": price,
                        "size": size,
                        "url": url[:1000],
                        "available": (
                            match.get("available")
                            is not False
                        ),
                    }
                )

    print()
    print("🍹 LIVE RETAIL IMPORT")
    print("=" * 90)
    print(
        "Safe listings:",
        len(candidates),
    )
    print(
        "Skipped incomplete:",
        len(skipped_missing),
    )
    print(
        "Skipped variant mismatch:",
        len(skipped_variant),
    )

    if skipped_variant:
        print()
        print("VARIANTS REJECTED")
        print("-" * 90)

        for ingredient, store, product in skipped_variant:
            print(
                f"{ingredient} | "
                f"{store} | "
                f"{product}"
            )

    if not args.apply:
        print()
        print(
            "DRY RUN — database unchanged."
        )
        print(
            "Run again with --apply "
            "to import these safe listings."
        )
        return

    created_products = 0
    created_mappings = 0
    created_listings = 0
    updated_listings = 0

    async with AsyncSessionLocal() as db:

        try:
            for row in candidates:

                ingredient = await db.get(
                    Ingredient,
                    row["ingredient_id"],
                )

                if ingredient is None:
                    print(
                        "⚠️ Ingredient missing:",
                        row["ingredient"],
                    )
                    continue

                if (
                    ingredient.canonical_name
                    != row["ingredient"]
                ):
                    print(
                        "⚠️ Ingredient ID/name mismatch:",
                        row["ingredient"],
                    )
                    continue

                sr = await db.execute(
                    select(Supplier).where(
                        Supplier.name
                        == row["store"]
                    )
                )

                supplier = (
                    sr.scalar_one_or_none()
                )

                if supplier is None:
                    print(
                        "⚠️ Supplier missing:",
                        row["store"],
                    )
                    continue

                # These are verified orderable shops.
                supplier.active = True
                supplier.is_retailer = True

                # If this exact live URL already exists,
                # reuse its Product instead of duplicating it.
                existing_listing_result = (
                    await db.execute(
                        select(
                            SupplierProduct
                        ).where(
                            SupplierProduct.supplier_id
                            == supplier.id,
                            SupplierProduct.product_url
                            == row["url"],
                        )
                    )
                )

                listing = (
                    existing_listing_result
                    .scalar_one_or_none()
                )

                if listing is not None:
                    product = await db.get(
                        Product,
                        listing.product_id,
                    )

                else:
                    product_result = (
                        await db.execute(
                            select(Product).where(
                                Product.ingredient_id
                                == ingredient.id,
                                Product.name
                                == row["product"],
                            )
                        )
                    )

                    product = (
                        product_result
                        .scalar_one_or_none()
                    )

                if product is None:
                    product = Product(
                        name=row["product"],
                        brand=None,
                        ingredient_id=ingredient.id,
                        package_size=row["size"],
                        package_unit="ml",
                        active=True,
                        notes=(
                            f"{BATCH}: verified "
                            f"live retail product"
                        ),
                    )

                    db.add(product)
                    await db.flush()

                    created_products += 1

                elif product.ingredient_id is None:
                    product.ingredient_id = (
                        ingredient.id
                    )

                mapping_result = (
                    await db.execute(
                        select(
                            IngredientProductMapping
                        ).where(
                            IngredientProductMapping.ingredient_id
                            == ingredient.id,
                            IngredientProductMapping.product_id
                            == product.id,
                        )
                    )
                )

                mapping = (
                    mapping_result
                    .scalar_one_or_none()
                )

                if mapping is None:
                    db.add(
                        IngredientProductMapping(
                            ingredient_id=ingredient.id,
                            product_id=product.id,
                            preferred=False,
                            substitution_allowed=False,
                            substitution_priority=99,
                            notes=(
                                f"{BATCH}: verified "
                                f"live retail match"
                            ),
                        )
                    )

                    created_mappings += 1

                if listing is None:
                    listing = SupplierProduct(
                        supplier_id=supplier.id,
                        product_id=product.id,
                    )

                    db.add(listing)

                    created_listings += 1

                else:
                    updated_listings += 1

                listing.package_size = row["size"]
                listing.package_unit = "ml"
                listing.product_url = row["url"]

                # Website shop prices are consumer prices.
                listing.price_before_vat = None
                listing.price_after_vat = row["price"]

                listing.is_historical = False
                listing.source_file = BATCH
                listing.last_checked_at = (
                    datetime.now(timezone.utc)
                )
                listing.available = row["available"]

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    print()
    print("=" * 90)
    print("IMPORT COMPLETE")
    print("=" * 90)
    print(
        "Products created:",
        created_products,
    )
    print(
        "Mappings created:",
        created_mappings,
    )
    print(
        "Supplier listings created:",
        created_listings,
    )
    print(
        "Supplier listings updated:",
        updated_listings,
    )
    print()
    print("✅ Database committed.")


if __name__ == "__main__":
    asyncio.run(main())

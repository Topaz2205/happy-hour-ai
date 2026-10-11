"""
Happy Hour AI — multi-store catalog scanner.

FIRST STAGE:
- Reads every real retailer from the DB.
- Ignores equipment stores / bookkeeping sources.
- Tries to detect WooCommerce-style product catalogues.
- Extracts sample product name, price, package size and URL.
- DOES NOT WRITE TO THE DATABASE YET.

Once every shop has a working adapter, this same command will get --apply.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import Supplier


# These are real retailers, but they sell equipment rather than
# ingredients/drinks. They should not enter drink-price comparison.
EXCLUDED_STORES = {
    '"אול סאל" טרדינג ירושלים',
    "בר פרודקטס ישראל",
    "ארגל",
    "יעקב סוכנויות יבוא יצוא",
    "שופבר",
    "אקוויפ",
    "קוקטייל ארט",
}


@dataclass
class CatalogProduct:
    name: str
    price: float | None
    package_size: float | None
    package_unit: str | None
    url: str
    available: bool


def clean(text: str | None) -> str:
    return " ".join((text or "").split())


def parse_price(text: str) -> float | None:
    """
    WooCommerce sale prices often contain:
        old price + new price

    We take the LAST shekel amount, which is normally the current price.
    """
    text = text.replace(",", "")
    values = re.findall(
        r"₪\s*([0-9]+(?:\.[0-9]{1,2})?)",
        text,
    )

    if not values:
        values = re.findall(
            r"([0-9]+(?:\.[0-9]{1,2})?)\s*₪",
            text,
        )

    if not values:
        return None

    try:
        return float(values[-1])
    except ValueError:
        return None


def parse_package_size(name: str) -> tuple[float | None, str | None]:
    """
    Examples:
      700 מ"ל
      750 מ״ל
      1000ml
      1L
      1 LT
      1 ליטר
    """
    normalized = (
        name.lower()
        .replace("מ״ל", "ml")
        .replace('מ"ל', "ml")
        .replace("מ׳׳ל", "ml")
    )

    ml_match = re.search(
        r"(\d+(?:\.\d+)?)\s*ml\b",
        normalized,
        re.I,
    )
    if ml_match:
        return float(ml_match.group(1)), "ml"

    litre_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:l|lt|liter|litre|ליטר)\b",
        normalized,
        re.I,
    )
    if litre_match:
        return float(litre_match.group(1)) * 1000, "ml"

    return None, None


def parse_woocommerce(html: str, base_url: str) -> list[CatalogProduct]:
    soup = BeautifulSoup(html, "lxml")

    cards = soup.select(
        "li.product, "
        ".products .product, "
        ".woocommerce ul.products li.product"
    )

    products: list[CatalogProduct] = []
    seen_urls: set[str] = set()

    for card in cards:
        title_node = card.select_one(
            ".woocommerce-loop-product__title, "
            ".product-title, "
            ".product_title, "
            "h2, h3"
        )

        name = clean(
            title_node.get_text(" ", strip=True)
            if title_node
            else None
        )

        link_node = card.select_one(
            "a.woocommerce-LoopProduct-link[href], "
            "a[href*='/product/'], "
            "a[href*='/product-page/']"
        )

        if link_node is None:
            link_node = card.find("a", href=True)

        if not name or link_node is None:
            continue

        url = urljoin(base_url, link_node.get("href"))

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        price_node = card.select_one(
            ".price, "
            ".woocommerce-Price-amount, "
            "[class*='price']"
        )

        price_text = (
            price_node.get_text(" ", strip=True)
            if price_node
            else ""
        )

        price = parse_price(price_text)

        card_text = clean(card.get_text(" ", strip=True)).lower()

        unavailable_words = (
            "המלאי אזל",
            "אזל מהמלאי",
            "out of stock",
            "sold out",
        )

        available = not any(
            phrase in card_text
            for phrase in unavailable_words
        )

        package_size, package_unit = parse_package_size(name)

        products.append(
            CatalogProduct(
                name=name,
                price=price,
                package_size=package_size,
                package_unit=package_unit,
                url=url,
                available=available,
            )
        )

    return products


async def fetch_catalog_page(
    client: httpx.AsyncClient,
    website: str,
) -> tuple[str | None, list[CatalogProduct]]:
    """
    Different WooCommerce shops expose the catalogue differently.
    Try common entry points without guessing product data.
    """

    candidates = [
        urljoin(website.rstrip("/") + "/", "shop/"),
        website,
    ]

    for url in candidates:
        try:
            response = await client.get(url)

            if response.status_code >= 400:
                continue

            products = parse_woocommerce(
                response.text,
                str(response.url),
            )

            if products:
                return str(response.url), products

        except Exception:
            continue

    return None, []


async def load_stores() -> list[Supplier]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Supplier)
            .where(
                Supplier.active.is_(True),
                Supplier.is_retailer.is_(True),
            )
            .order_by(Supplier.name)
        )

        return [
            supplier
            for supplier in result.scalars().all()
            if supplier.name not in EXCLUDED_STORES
        ]


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--max-products",
        type=int,
        default=8,
        help="How many sample products to print per shop.",
    )

    args = parser.parse_args()

    stores = await load_stores()

    print()
    print("🍹 HAPPY HOUR AI — STORE CATALOG SCAN")
    print("=" * 72)
    print(f"Drink / ingredient retailers found: {len(stores)}")
    print()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/128 Safari/537.36"
        ),
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=25,
    ) as client:

        success = 0
        unsupported = []

        for store in stores:

            print()
            print("=" * 72)
            print("STORE:", store.name)
            print("SITE: ", store.website)

            if not store.website:
                print("⚠️  NO WEBSITE — skipped")
                unsupported.append(store.name)
                continue

            source_url, products = await fetch_catalog_page(
                client,
                store.website,
            )

            if not products:
                print("⚠️  NO GENERIC CATALOG DETECTED")
                print("    This shop will need its own adapter.")
                unsupported.append(store.name)
                continue

            success += 1

            print("✅ CATALOG FOUND")
            print("PAGE: ", source_url)
            print("FOUND ON FIRST PAGE:", len(products))

            print()
            print("SAMPLE:")

            for product in products[: args.max_products]:
                size = (
                    f"{product.package_size:g}{product.package_unit}"
                    if product.package_size
                    else "size ?"
                )

                price = (
                    f"₪{product.price:.2f}"
                    if product.price is not None
                    else "price ?"
                )

                stock = (
                    "in stock"
                    if product.available
                    else "out of stock"
                )

                print(
                    f"  • {product.name}\n"
                    f"    {price} | {size} | {stock}\n"
                    f"    {product.url}"
                )

        print()
        print("=" * 72)
        print("SCAN SUMMARY")
        print("=" * 72)
        print(f"✅ Generic catalog detected: {success}")
        print(f"⚠️  Needs custom adapter:     {len(unsupported)}")

        if unsupported:
            print()
            print("CUSTOM ADAPTERS NEEDED:")
            for name in unsupported:
                print("  -", name)

        print()
        print(
            "DRY RUN ONLY — nothing was written to the database."
        )


if __name__ == "__main__":
    asyncio.run(main())

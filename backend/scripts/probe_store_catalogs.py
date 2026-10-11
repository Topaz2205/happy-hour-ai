"""
Happy Hour AI — store catalog probe.

Discovers product URLs through:
1. product sitemap
2. WordPress/WooCommerce sitemap
3. generic sitemap index

Then opens actual product pages and tries to read
name, current price, availability and package size.

DRY RUN ONLY.
"""

import asyncio
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import Supplier


EXCLUDED_STORES = {
    '"אול סאל" טרדינג ירושלים',
    "בר פרודקטס ישראל",
    "ארגל",
    "יעקב סוכנויות יבוא יצוא",
    "שופבר",
    "אקוויפ",
    "קוקטייל ארט",
}


def clean(value):
    return " ".join(str(value or "").split())


def parse_size(text):
    text = clean(text).lower()

    replacements = {
        'מ״ל': 'ml',
        'מ"ל': 'ml',
        "מ׳׳ל": "ml",
        "מ'ל": "ml",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    match = re.search(
        r'(\d+(?:\.\d+)?)\s*ml\b',
        text,
        re.I,
    )
    if match:
        size = float(match.group(1))

        # Do not accidentally treat "price per 100ml"
        # as bottle size.
        if size != 100:
            return size, "ml"

    match = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:ליטר|litre|liter|ltr|lt|l)\b',
        text,
        re.I,
    )
    if match:
        return float(match.group(1)) * 1000, "ml"

    return None, None


def flatten_json(value):
    if isinstance(value, list):
        for item in value:
            yield from flatten_json(item)

    elif isinstance(value, dict):
        yield value

        for item in value.values():
            yield from flatten_json(item)


def get_product_jsonld(soup):
    for node in soup.select('script[type="application/ld+json"]'):
        raw = node.string or node.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        for obj in flatten_json(data):
            kind = obj.get("@type")

            if isinstance(kind, list):
                is_product = "Product" in kind
            else:
                is_product = kind == "Product"

            if is_product:
                return obj

    return None


def extract_offer(product):
    offers = product.get("offers")

    if isinstance(offers, list):
        offers = offers[0] if offers else None

    if not isinstance(offers, dict):
        return None, None

    price = (
        offers.get("price")
        or offers.get("lowPrice")
        or offers.get("highPrice")
    )

    try:
        price = float(
            str(price).replace(",", "").replace("₪", "").strip()
        )
    except Exception:
        price = None

    availability = clean(offers.get("availability")).lower()

    if availability:
        available = not any(
            x in availability
            for x in (
                "outofstock",
                "out-of-stock",
                "soldout",
                "sold-out",
            )
        )
    else:
        available = None

    return price, available


def parse_product_page(html, url):
    soup = BeautifulSoup(html, "lxml")

    product = get_product_jsonld(soup)

    if product:
        name = clean(product.get("name"))
        price, available = extract_offer(product)

        description = clean(product.get("description"))

        size, unit = parse_size(name)

        if size is None:
            size, unit = parse_size(description)

        if name and price is not None:
            return {
                "name": name,
                "price": price,
                "size": size,
                "unit": unit,
                "available": available,
                "url": url,
                "source": "JSON-LD",
            }

    # Conservative HTML fallback.
    h1 = soup.select_one("h1")
    name = clean(h1.get_text(" ", strip=True) if h1 else "")

    price = None

    selectors = [
        'meta[property="product:price:amount"]',
        '[itemprop="price"]',
        '.summary .price',
        '.product .price',
    ]

    for selector in selectors:
        node = soup.select_one(selector)

        if not node:
            continue

        raw = (
            node.get("content")
            if node.has_attr("content")
            else node.get_text(" ", strip=True)
        )

        numbers = re.findall(
            r'\d+(?:,\d{3})*(?:\.\d+)?',
            raw or "",
        )

        if numbers:
            try:
                price = float(numbers[-1].replace(",", ""))
                break
            except Exception:
                pass

    size, unit = parse_size(name)

    if name and price is not None:
        return {
            "name": name,
            "price": price,
            "size": size,
            "unit": unit,
            "available": None,
            "url": url,
            "source": "HTML",
        }

    return None


def xml_locations(text):
    try:
        root = ET.fromstring(text)
    except Exception:
        return []

    result = []

    for elem in root.iter():
        if elem.tag.lower().endswith("loc") and elem.text:
            result.append(elem.text.strip())

    return result


async def fetch_text(client, url):
    try:
        response = await client.get(url)

        if response.status_code >= 400:
            return None, None

        return str(response.url), response.text

    except Exception:
        return None, None


async def discover_product_urls(client, website):
    root = website.rstrip("/") + "/"

    sitemap_candidates = [
        urljoin(root, "product-sitemap.xml"),
        urljoin(root, "wp-sitemap-posts-product-1.xml"),
        urljoin(root, "sitemap_index.xml"),
        urljoin(root, "wp-sitemap.xml"),
        urljoin(root, "sitemap.xml"),
    ]

    visited = set()
    product_urls = []
    child_sitemaps = []

    for sitemap_url in sitemap_candidates:
        final_url, text = await fetch_text(client, sitemap_url)

        if not text:
            continue

        locations = xml_locations(text)

        if not locations:
            continue

        for loc in locations:
            lower = loc.lower()

            if loc.endswith(".xml"):
                if (
                    "product" in lower
                    or "post" in lower
                ):
                    child_sitemaps.append(loc)

            elif (
                "/product/" in lower
                or "/product-page/" in lower
                or "/shop/" in lower
            ):
                product_urls.append(loc)

    for sitemap_url in child_sitemaps[:15]:
        if sitemap_url in visited:
            continue

        visited.add(sitemap_url)

        _, text = await fetch_text(client, sitemap_url)

        if not text:
            continue

        for loc in xml_locations(text):
            lower = loc.lower()

            if (
                "/product/" in lower
                or "/product-page/" in lower
                or "/shop/" in lower
            ):
                product_urls.append(loc)

    # preserve order, remove duplicates
    return list(dict.fromkeys(product_urls))


async def load_stores():
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
    stores = await load_stores()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/128 Safari/537.36"
        ),
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }

    print()
    print("🍹 HAPPY HOUR AI — PRODUCT PAGE PROBE")
    print("=" * 76)

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=15,
    ) as client:

        successful = []
        failed = []

        for store in stores:
            print()
            print("=" * 76)
            print("STORE:", store.name)
            print("SITE: ", store.website)

            if not store.website:
                print("⚠️  NO WEBSITE")
                failed.append(store.name)
                continue

            urls = await discover_product_urls(
                client,
                store.website,
            )

            print("PRODUCT URLS DISCOVERED:", len(urls))

            parsed = []

            for url in urls[:5]:
                _, html = await fetch_text(client, url)

                if not html:
                    continue

                item = parse_product_page(html, url)

                if item:
                    parsed.append(item)

            if not parsed:
                print("⚠️  Could not parse product pages")
                failed.append(store.name)
                continue

            successful.append(store.name)

            print("✅ PRODUCT PAGE DATA FOUND")

            for item in parsed[:3]:
                size = (
                    f"{item['size']:g}{item['unit']}"
                    if item["size"]
                    else "size ?"
                )

                stock = (
                    "stock ?"
                    if item["available"] is None
                    else (
                        "in stock"
                        if item["available"]
                        else "out of stock"
                    )
                )

                print()
                print("  PRODUCT:", item["name"])
                print("  PRICE:  ", f"₪{item['price']:.2f}")
                print("  SIZE:   ", size)
                print("  STOCK:  ", stock)
                print("  SOURCE: ", item["source"])
                print("  URL:    ", item["url"])

        print()
        print("=" * 76)
        print("PROBE SUMMARY")
        print("=" * 76)
        print("✅ Product pages readable:", len(successful))
        print("⚠️  Still need adapter:    ", len(failed))

        if successful:
            print()
            print("READABLE:")
            for name in successful:
                print("  -", name)

        if failed:
            print()
            print("NEEDS WORK:")
            for name in failed:
                print("  -", name)

        print()
        print("DRY RUN ONLY — database unchanged.")


if __name__ == "__main__":
    asyncio.run(main())

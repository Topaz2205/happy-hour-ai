"""
Happy Hour AI — enrich missing package sizes.

Reads:
    data/relevant_store_matches_clean.json

Only revisits accepted products whose package size is still missing.

DRY RUN with respect to the database:
it updates only the local JSON report, never PostgreSQL.
"""

import asyncio
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from bs4 import BeautifulSoup

SOURCE = Path("data/relevant_store_matches_clean.json")
OUTPUT = Path("data/relevant_store_matches_ready.json")


COMMON_ML = [
    100,
    150,
    180,
    200,
    250,
    275,
    300,
    325,
    330,
    500,
    700,
    750,
    1000,
    1500,
    2000,
]


def clean(value):
    return html.unescape(str(value or "")).lower()


def candidate_sizes(text):
    text = clean(text)

    text = (
        text
        .replace("מ״ל", " ml ")
        .replace('מ"ל', " ml ")
        .replace("מ׳׳ל", " ml ")
        .replace("מ'ל", " ml ")
        .replace("מיליליטר", " ml ")
    )

    sizes = []

    # 700ml / 750 ml
    for raw in re.findall(
        r"\b(\d{2,4}(?:[\.,]\d+)?)\s*ml\b",
        text,
        re.I,
    ):
        try:
            value = float(raw.replace(",", "."))
            if 100 <= value <= 5000:
                sizes.append(value)
        except Exception:
            pass

    # 70cl / 75 cl
    for raw in re.findall(
        r"\b(\d{1,3}(?:[\.,]\d+)?)\s*cl\b",
        text,
        re.I,
    ):
        try:
            value = float(raw.replace(",", ".")) * 10
            if 100 <= value <= 5000:
                sizes.append(value)
        except Exception:
            pass

    # 1L / 0.7 L / 0.75L
    for raw in re.findall(
        r"\b(\d+(?:[\.,]\d+)?)\s*(?:l|lt|ltr|liter|litre)\b",
        text,
        re.I,
    ):
        try:
            value = float(raw.replace(",", ".")) * 1000
            if 100 <= value <= 5000:
                sizes.append(value)
        except Exception:
            pass

    # Hebrew litres
    for raw in re.findall(
        r"\b(\d+(?:[\.,]\d+)?)\s*ליטר\b",
        text,
        re.I,
    ):
        try:
            value = float(raw.replace(",", ".")) * 1000
            if 100 <= value <= 5000:
                sizes.append(value)
        except Exception:
            pass

    # "ליטר" by itself normally means 1L.
    if "ליטר" in text and not sizes:
        sizes.append(1000.0)

    return sizes


def choose_size(sizes):
    if not sizes:
        return None

    # Remove common price-per-100ml noise where larger bottle values exist.
    unique = []
    for size in sizes:
        if size not in unique:
            unique.append(size)

    non_100 = [
        x for x in unique
        if x != 100
    ]

    if non_100:
        unique = non_100

    # Prefer standard retail package sizes.
    for common in COMMON_ML:
        if common in unique:
            return float(common)

    return float(unique[0])


def extract_page_size(page_html, product_name):
    soup = BeautifulSoup(page_html, "lxml")

    texts = [product_name]

    # Product JSON-LD
    for script in soup.select(
        'script[type="application/ld+json"]'
    ):
        raw = script.string or script.get_text()

        if raw:
            texts.append(raw)

    # Useful product areas
    selectors = [
        "h1",
        ".summary",
        ".product_meta",
        ".woocommerce-product-details__short-description",
        ".woocommerce-Tabs-panel",
        ".product-description",
        ".description",
        "[class*='description']",
        "[class*='product']",
    ]

    for selector in selectors:
        for node in soup.select(selector)[:8]:
            texts.append(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

    # Meta tags sometimes expose package/name info.
    for node in soup.select("meta[content]"):
        content = node.get("content")

        if content:
            texts.append(content)

    sizes = candidate_sizes(
        " ".join(texts)
    )

    return choose_size(sizes)


async def fetch(client, url):
    try:
        response = await client.get(url)

        if response.status_code >= 400:
            return None

        return response.text

    except Exception:
        return None


async def main():
    data = json.loads(
        SOURCE.read_text()
    )

    missing_before = 0
    filled = 0
    still_missing = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "Chrome/128 Safari/537.36"
        ),
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=18,
    ) as client:

        for ingredient in data["ingredients"]:

            for store, matches in ingredient["stores"].items():

                for match in matches:

                    if match.get("package_size_ml"):
                        continue

                    missing_before += 1

                    print(
                        f"Checking "
                        f"{ingredient['ingredient']} | "
                        f"{store} | "
                        f"{match['product']}"
                    )

                    page_html = await fetch(
                        client,
                        match["url"],
                    )

                    if not page_html:
                        still_missing.append(
                            (
                                ingredient["ingredient"],
                                store,
                                match["product"],
                            )
                        )
                        continue

                    size = extract_page_size(
                        page_html,
                        match["product"],
                    )

                    if size:
                        match["package_size_ml"] = size
                        filled += 1

                        print(
                            f"  ✅ {size:g}ml"
                        )
                    else:
                        still_missing.append(
                            (
                                ingredient["ingredient"],
                                store,
                                match["product"],
                            )
                        )

                        print(
                            "  ⚠️ size still unknown"
                        )

                    await asyncio.sleep(0.1)

    OUTPUT.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
    )

    print()
    print("=" * 90)
    print("PACKAGE SIZE ENRICHMENT")
    print("=" * 90)
    print(
        "Missing before:",
        missing_before,
    )
    print(
        "Filled automatically:",
        filled,
    )
    print(
        "Still missing:",
        len(still_missing),
    )

    if still_missing:
        print()
        print("STILL MISSING")
        print("-" * 90)

        for ingredient, store, product in still_missing:
            print(
                f"{ingredient} | "
                f"{store} | "
                f"{product}"
            )

    print()
    print(
        "Saved:",
        OUTPUT,
    )
    print(
        "DATABASE UNCHANGED."
    )


if __name__ == "__main__":
    asyncio.run(main())

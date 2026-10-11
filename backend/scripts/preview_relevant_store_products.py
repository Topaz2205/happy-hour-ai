"""
Happy Hour AI — targeted live product matcher.

Searches only products needed by active cocktails across the
7 stores we can read.

DRY RUN ONLY.
Nothing is written to the database.
"""

import asyncio
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import or_, select

from app.db.session import AsyncSessionLocal
from app.models import Cocktail, CocktailIngredient, Ingredient, Supplier

from probe_store_catalogs import (
    discover_product_urls,
    fetch_text,
    parse_product_page,
    get_product_jsonld,
)


STORES = [
    "Alcohome",
    "Free Spirits & Co",
    "בית היין",
    "דרך היין",
    "סחוט (Sahut)",
    "עולם היין",
    "משקאות המשמח",
]


# Products we actually want to buy / compare.
EXTRA_PURCHASE_ITEMS = {
    "Fresh Lemon Juice",
    "Fresh Lime Juice",
    "Ginger Beer",
    "Soda Water",
}


ALIASES = {
    "Angostura Aromatic Bitters": [
        "angostura",
        "אנגוסטורה",
    ],
    "Orange Bitters": [
        "orange bitters",
        "אורנג ביטרס",
        "ביטרס תפוז",
    ],
    "Aperol": [
        "aperol",
        "אפרול",
    ],
    "Campari": [
        "campari",
        "קמפרי",
    ],
    "Crème de Cacao": [
        "creme de cacao",
        "crème de cacao",
        "קרם דה קקאו",
        "קרם קקאו",
    ],
    "Dry Curacao Pierre Ferrand": [
        "pierre ferrand",
        "dry curacao",
        "פייר פראן",
        "פייר פרנד",
        "קורסאו פייר",
    ],
    "Fernet Branca": [
        "fernet branca",
        "פרנה ברנקה",
        "פרנט ברנקה",
    ],
    "Green Chartreuse": [
        "green chartreuse",
        "chartreuse",
        "שרטרז ירוק",
        "שארטרז ירוק",
        "שרטרז",
    ],
    "Kina L'Aero D'Or": [
        "kina l aero",
        "kina laero",
        "kina",
        "קינה לארו",
    ],
    "Luxardo Maraschino": [
        "luxardo maraschino",
        "maraschino luxardo",
        "לוקסרדו מרסקינו",
        "לוקסארדו מרסקינו",
    ],
    "Mancino Bianco Vermouth": [
        "mancino bianco",
        "מנצינו ביאנקו",
        "מנצ'ינו ביאנקו",
    ],
    "Mancino Secco Dry Vermouth": [
        "mancino secco",
        "mancino seco",
        "מנצינו סקו",
        "מנצ'ינו סקו",
    ],
    "Red Vermouth": [
        "red vermouth",
        "rosso vermouth",
        "vermouth rosso",
        "ורמוט אדום",
        "ורמוט רוסו",
    ],
    "Savoia Americano": [
        "savoia americano",
        "סבויה אמריקנו",
    ],
    "Beefeater London Dry Gin": [
        "beefeater",
        "ביפיטר",
    ],
    "Beluga Noble Vodka": [
        "beluga noble",
        "beluga",
        "בלוגה נובל",
        "בלוגה",
    ],
    "Cognac VS": [
        "cognac vs",
        "קוניאק vs",
        "קוניאק וי אס",
        "קוניאק",
    ],
    "Four Roses Bourbon": [
        "four roses",
        "פור רוזס",
    ],
    "Havana Club Añejo 3 Años Rum": [
        "havana club 3",
        "havana club anejo 3",
        "havana club",
        "הוואנה קלאב 3",
        "הוואנה 3",
        "הוואנה קלאב",
    ],
    "Olmeca Silver Tequila": [
        "olmeca silver",
        "olmeca blanco",
        "אולמקה סילבר",
        "אולמקה בלנקו",
        "אולמקה",
    ],
    "Rittenhouse Rye Whiskey": [
        "rittenhouse",
        "ריטנהאוס",
    ],
    "Sparkling Wine / Prosecco": [
        "prosecco",
        "sparkling wine",
        "פרוסקו",
        "יין מבעבע",
    ],
    "Ginger Beer": [
        "ginger beer",
        "גינגר ביר",
        "ג'ינג'ר ביר",
        "בירת גינגר",
        "בירת ג'ינג'ר",
    ],
    "Soda Water": [
        "soda water",
        "מי סודה",
        "סודה",
    ],
    "Fresh Lemon Juice": [
        "lemon juice",
        "fresh lemon",
        "לימון סחוט",
        "מיץ לימון",
    ],
    "Fresh Lime Juice": [
        "lime juice",
        "fresh lime",
        "ליים סחוט",
        "מיץ ליים",
    ],
}


BUNDLE_WORDS = {
    "מארז",
    "שישייה",
    "שישיית",
    "זוג",
    "pack",
    "box",
    "case",
    "gift set",
}


def normalize(value):
    value = html.unescape(
        unquote(str(value or ""))
    ).lower()

    value = (
        value
        .replace("״", '"')
        .replace("׳", "'")
        .replace("’", "'")
        .replace("á", "a")
        .replace("é", "e")
        .replace("ñ", "n")
    )

    value = re.sub(
        r"[^a-z0-9\u0590-\u05ff]+",
        " ",
        value,
    )

    return " ".join(value.split())


def alias_score(alias, value):
    a = normalize(alias)
    v = normalize(value)

    if not a or not v:
        return 0

    if a in v:
        words = a.split()

        if len(words) >= 2:
            return 100

        if len(a) >= 6:
            return 75

        return 55

    words = [
        word
        for word in a.split()
        if len(word) >= 4
    ]

    if not words:
        return 0

    matches = sum(
        1
        for word in words
        if word in v
    )

    if matches == len(words) and matches >= 2:
        return 80

    return 0


def is_bundle(name):
    n = normalize(name)

    return any(
        normalize(word) in n
        for word in BUNDLE_WORDS
    )


def extract_size(html_text, product_name):
    soup = BeautifulSoup(
        html_text,
        "lxml",
    )

    pieces = [product_name]

    product_json = get_product_jsonld(soup)

    if product_json:
        pieces.append(
            str(
                product_json.get(
                    "description",
                    "",
                )
            )
        )

    for selector in (
        ".woocommerce-product-details__short-description",
        ".product-short-description",
        ".product-description",
        ".summary",
    ):
        node = soup.select_one(selector)

        if node:
            pieces.append(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

    text = html.unescape(
        " ".join(pieces)
    ).lower()

    text = (
        text
        .replace("מ״ל", "ml")
        .replace('מ"ל', "ml")
        .replace("מ׳׳ל", "ml")
        .replace("מ'ל", "ml")
    )

    candidates = []

    for value in re.findall(
        r"(\d+(?:[\.,]\d+)?)\s*ml\b",
        text,
        re.I,
    ):
        try:
            ml = float(
                value.replace(",", ".")
            )

            if 150 <= ml <= 5000:
                candidates.append(ml)

        except ValueError:
            pass

    for value in re.findall(
        r"(\d+(?:[\.,]\d+)?)\s*"
        r"(?:ליטר|liter|litre|ltr|lt)\b",
        text,
        re.I,
    ):
        try:
            ml = (
                float(
                    value.replace(",", ".")
                )
                * 1000
            )

            if 150 <= ml <= 5000:
                candidates.append(ml)

        except ValueError:
            pass

    if not candidates:
        return None

    # Prefer common bottle sizes where possible.
    common = [
        200,
        250,
        330,
        500,
        700,
        750,
        1000,
        1500,
        2000,
    ]

    for size in common:
        if size in candidates:
            return float(size)

    return candidates[0]


async def load_targets_and_stores():
    async with AsyncSessionLocal() as db:

        ingredient_result = await db.execute(
            select(Ingredient)
            .join(
                CocktailIngredient,
                CocktailIngredient.ingredient_id
                == Ingredient.id,
            )
            .join(
                Cocktail,
                Cocktail.id
                == CocktailIngredient.cocktail_id,
            )
            .where(
                Cocktail.active.is_(True),
                or_(
                    Ingredient.alcoholic.is_(True),
                    Ingredient.canonical_name.in_(
                        EXTRA_PURCHASE_ITEMS
                    ),
                ),
            )
            .distinct()
            .order_by(
                Ingredient.canonical_name
            )
        )

        targets = list(
            ingredient_result.scalars().all()
        )

        supplier_result = await db.execute(
            select(Supplier)
            .where(
                Supplier.name.in_(STORES),
                Supplier.active.is_(True),
            )
            .order_by(Supplier.name)
        )

        stores = list(
            supplier_result.scalars().all()
        )

    return targets, stores


async def main():
    targets, stores = (
        await load_targets_and_stores()
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "Chrome/128 Safari/537.36"
        ),
        "Accept-Language": (
            "he-IL,he;q=0.9,en;q=0.8"
        ),
    }

    print()
    print(
        "🍹 HAPPY HOUR AI — "
        "TARGETED PRODUCT PREVIEW"
    )
    print("=" * 90)
    print(
        "Purchase ingredients:",
        len(targets),
    )
    print(
        "Readable stores:",
        len(stores),
    )

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=18,
    ) as client:

        catalogs = {}

        for store in stores:
            print(
                f"Reading {store.name}...",
                end=" ",
                flush=True,
            )

            if not store.website:
                catalogs[store.name] = []
                print("no website")
                continue

            urls = await discover_product_urls(
                client,
                store.website,
            )

            urls = [
                url
                for url in urls
                if urlparse(url).path.rstrip("/")
                not in (
                    "/shop",
                    "/product",
                    "/product-page",
                )
            ]

            catalogs[store.name] = urls

            print(
                f"{len(urls)} URLs"
            )

        final_report = []

        for ingredient in targets:

            name = ingredient.canonical_name

            search_terms = ALIASES.get(
                name,
                [name],
            )

            print()
            print("=" * 90)
            print("INGREDIENT:", name)

            store_results = {}

            for store in stores:

                urls = catalogs.get(
                    store.name,
                    [],
                )

                scored_urls = []

                for url in urls:
                    score = max(
                        (
                            alias_score(
                                term,
                                url,
                            )
                            for term
                            in search_terms
                        ),
                        default=0,
                    )

                    if score >= 55:
                        scored_urls.append(
                            (
                                score,
                                url,
                            )
                        )

                scored_urls.sort(
                    reverse=True,
                    key=lambda x: x[0],
                )

                matches = []

                # Open only the best candidate pages.
                for _url_score, url in scored_urls[:8]:

                    _, page_html = (
                        await fetch_text(
                            client,
                            url,
                        )
                    )

                    if not page_html:
                        continue

                    item = parse_product_page(
                        page_html,
                        url,
                    )

                    if not item:
                        continue

                    product_name = item["name"]

                    title_score = max(
                        (
                            alias_score(
                                term,
                                product_name,
                            )
                            for term
                            in search_terms
                        ),
                        default=0,
                    )

                    if title_score < 55:
                        continue

                    if is_bundle(product_name):
                        continue

                    if item.get(
                        "available"
                    ) is False:
                        continue

                    size = extract_size(
                        page_html,
                        product_name,
                    )

                    matches.append(
                        {
                            "product": product_name,
                            "price": item["price"],
                            "size_ml": size,
                            "available": item.get(
                                "available"
                            ),
                            "url": url,
                            "score": title_score,
                        }
                    )

                    if len(matches) >= 2:
                        break

                    await asyncio.sleep(0.08)

                if matches:
                    store_results[
                        store.name
                    ] = matches

                    for match in matches:
                        size_text = (
                            f"{match['size_ml']:g}ml"
                            if match["size_ml"]
                            else "SIZE ?"
                        )

                        print(
                            f"  ✅ {store.name:<20} "
                            f"₪{match['price']:<8.2f} "
                            f"{size_text:<10} "
                            f"{match['product']}"
                        )

            if not store_results:
                print(
                    "  ❌ No verified live matches"
                )

            final_report.append(
                {
                    "ingredient_id": (
                        str(ingredient.id)
                    ),
                    "ingredient": name,
                    "store_count": len(
                        store_results
                    ),
                    "stores": store_results,
                }
            )

    final_report.sort(
        key=lambda x: (
            x["store_count"],
            x["ingredient"].lower(),
        )
    )

    three_plus = [
        x
        for x in final_report
        if x["store_count"] >= 3
    ]

    two = [
        x
        for x in final_report
        if x["store_count"] == 2
    ]

    one = [
        x
        for x in final_report
        if x["store_count"] == 1
    ]

    zero = [
        x
        for x in final_report
        if x["store_count"] == 0
    ]

    print()
    print("=" * 90)
    print("TARGETED MATCH SUMMARY")
    print("=" * 90)

    print(
        f"✅ 3+ stores: {len(three_plus)}"
    )
    print(
        f"🟡 2 stores:  {len(two)}"
    )
    print(
        f"🟠 1 store:   {len(one)}"
    )
    print(
        f"🔴 0 stores:  {len(zero)}"
    )

    print()
    print("0–1 STORE ITEMS")
    print("-" * 90)

    for row in zero + one:
        names = (
            ", ".join(
                row["stores"].keys()
            )
            or "NONE"
        )

        print(
            f"{row['ingredient']:<45}"
            f" {row['store_count']} | "
            f"{names}"
        )

    output = Path(
        "data/relevant_store_matches.json"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            {
                "stores": STORES,
                "ingredients": final_report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print()
    print(
        "Saved:",
        output,
    )
    print(
        "DRY RUN ONLY — "
        "database unchanged."
    )


if __name__ == "__main__":
    asyncio.run(main())

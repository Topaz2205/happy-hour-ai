"""
Happy Hour AI — live store coverage check.

Goal:
For every ingredient used by an active cocktail, check whether the
7 readable shops appear to contain a matching product.

This DOES NOT modify the database.

It uses:
- canonical ingredient names
- ingredient aliases
- products already mapped to that ingredient
- substitute-group ingredients/products
- decoded product URLs from each store's sitemap

The result is a coverage report that tells us whether the 7 working
shops are enough before we disable the other shops.
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
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import (
    Cocktail,
    CocktailIngredient,
    Ingredient,
    IngredientAlias,
    IngredientProductMapping,
    Product,
    Supplier,
)

from probe_store_catalogs import discover_product_urls


WORKING_STORES = [
    "Alcohome",
    "Free Spirits & Co",
    "בית היין",
    "דרך היין",
    "סחוט (Sahut)",
    "עולם היין",
    "משקאות המשמח",
]


# Generic words should not prove that two products are the same.
STOPWORDS = {
    "the",
    "and",
    "with",
    "for",
    "of",
    "club",
    "anejo",
    "anos",
    "year",
    "old",
    "spirit",
    "spirits",
    "liqueur",
    "liquor",
    "alcohol",
    "bottle",
    "drink",
    "drinks",
    "juice",
    "syrup",
    "rum",
    "gin",
    "vodka",
    "whisky",
    "whiskey",
    "tequila",
    "vermouth",
    "wine",
    "beer",
    "fresh",
    "dry",
    "white",
    "red",
    "sweet",
    "ml",
    "liter",
    "litre",
    "product",
    "shop",
    "page",

    # Hebrew generic terms
    "רום",
    "ג׳ין",
    "גין",
    "וודקה",
    "ויסקי",
    "וויסקי",
    "טקילה",
    "יין",
    "בירה",
    "ליקר",
    "סירופ",
    "מיץ",
    "משקה",
    "בקבוק",
    "ליטר",
    "יבש",
    "לבן",
    "אדום",
}


def normalize(value: str | None) -> str:
    value = html.unescape(unquote(str(value or ""))).lower()

    value = (
        value
        .replace("״", '"')
        .replace("׳", "'")
        .replace("’", "'")
        .replace("á", "a")
        .replace("é", "e")
        .replace("ñ", "n")
    )

    value = re.sub(r"[^a-z0-9\u0590-\u05ff]+", " ", value)

    return " ".join(value.split())


def useful_tokens(value: str) -> list[str]:
    tokens = normalize(value).split()

    output = []

    for token in tokens:
        if len(token) < 4:
            continue

        if token in STOPWORDS:
            continue

        output.append(token)

    return output


def match_score(term: str, candidate: str) -> int:
    """
    Conservative matcher.

    100 = full normalized phrase appears
     80 = 3 useful tokens match
     65 = 2 useful tokens match
     50 = one long distinctive token matches
    """

    term_n = normalize(term)
    candidate_n = normalize(candidate)

    if not term_n or not candidate_n:
        return 0

    if len(term_n) >= 5 and term_n in candidate_n:
        return 100

    tokens = useful_tokens(term)

    if not tokens:
        return 0

    matched = [
        token
        for token in tokens
        if token in candidate_n
    ]

    if len(matched) >= 3:
        return 80

    if len(matched) >= 2:
        return 65

    if len(matched) == 1:
        token = matched[0]

        # Long brand/product words can be distinctive enough alone:
        # aperol, campari, havana, chartreuse, angostura, etc.
        if len(token) >= 6:
            return 50

    return 0


async def get_active_ingredients(db):
    result = await db.execute(
        select(Ingredient)
        .join(
            CocktailIngredient,
            CocktailIngredient.ingredient_id == Ingredient.id,
        )
        .join(
            Cocktail,
            Cocktail.id == CocktailIngredient.cocktail_id,
        )
        .where(Cocktail.active.is_(True))
        .distinct()
        .order_by(Ingredient.canonical_name)
    )

    return list(result.scalars().all())


async def terms_for_ingredient(db, ingredient):
    terms = {ingredient.canonical_name}

    aliases = await db.execute(
        select(IngredientAlias.source_name)
        .where(
            IngredientAlias.ingredient_id == ingredient.id
        )
    )

    terms.update(
        x
        for x in aliases.scalars().all()
        if x
    )

    mapped = await db.execute(
        select(Product.name)
        .join(
            IngredientProductMapping,
            IngredientProductMapping.product_id == Product.id,
        )
        .where(
            IngredientProductMapping.ingredient_id == ingredient.id
        )
    )

    terms.update(
        x
        for x in mapped.scalars().all()
        if x
    )

    # Include substitute-group names/products because Compare Shops
    # is allowed to consider appropriate substitutes too.
    substitute_group = getattr(
        ingredient,
        "substitute_group",
        None,
    )

    if substitute_group:
        related_result = await db.execute(
            select(Ingredient)
            .where(
                Ingredient.substitute_group == substitute_group
            )
        )

        related = list(
            related_result.scalars().all()
        )

        for other in related:
            terms.add(other.canonical_name)

            alias_result = await db.execute(
                select(IngredientAlias.source_name)
                .where(
                    IngredientAlias.ingredient_id == other.id
                )
            )

            terms.update(
                x
                for x in alias_result.scalars().all()
                if x
            )

            product_result = await db.execute(
                select(Product.name)
                .join(
                    IngredientProductMapping,
                    IngredientProductMapping.product_id == Product.id,
                )
                .where(
                    IngredientProductMapping.ingredient_id == other.id
                )
            )

            terms.update(
                x
                for x in product_result.scalars().all()
                if x
            )

    return sorted(
        {
            term.strip()
            for term in terms
            if term and term.strip()
        }
    )


async def load_stores(db):
    result = await db.execute(
        select(Supplier)
        .where(
            Supplier.name.in_(WORKING_STORES),
            Supplier.active.is_(True),
        )
        .order_by(Supplier.name)
    )

    return list(result.scalars().all())


async def main():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/128 Safari/537.36"
        ),
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }

    async with AsyncSessionLocal() as db:
        ingredients = await get_active_ingredients(db)
        stores = await load_stores(db)

        targets = {}

        for ingredient in ingredients:
            targets[str(ingredient.id)] = {
                "ingredient": ingredient.canonical_name,
                "terms": await terms_for_ingredient(
                    db,
                    ingredient,
                ),
            }

    print()
    print("🍹 HAPPY HOUR AI — LIVE STORE COVERAGE")
    print("=" * 82)
    print("Active cocktail ingredients:", len(ingredients))
    print("Working stores:", len(stores))
    print()

    store_catalogs = {}

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=18,
    ) as client:

        for store in stores:
            print(
                f"Reading {store.name}...",
                end=" ",
                flush=True,
            )

            if not store.website:
                print("NO WEBSITE")
                store_catalogs[store.name] = []
                continue

            urls = await discover_product_urls(
                client,
                store.website,
            )

            # /shop/ is not a product.
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

            store_catalogs[store.name] = urls

            print(f"{len(urls)} product URLs")

    report = []

    for target in targets.values():
        ingredient_name = target["ingredient"]
        terms = target["terms"]

        matches_by_store = {}

        for store_name, urls in store_catalogs.items():
            best = None

            for url in urls:
                score = max(
                    (
                        match_score(term, url)
                        for term in terms
                    ),
                    default=0,
                )

                if score < 50:
                    continue

                if best is None or score > best["score"]:
                    best = {
                        "score": score,
                        "url": url,
                    }

                    if score == 100:
                        break

            if best:
                matches_by_store[store_name] = best

        report.append(
            {
                "ingredient": ingredient_name,
                "store_count": len(matches_by_store),
                "stores": matches_by_store,
                "terms": terms,
            }
        )

    report.sort(
        key=lambda x: (
            x["store_count"],
            x["ingredient"].lower(),
        )
    )

    green = [
        x for x in report
        if x["store_count"] >= 3
    ]

    yellow = [
        x for x in report
        if x["store_count"] == 2
    ]

    red = [
        x for x in report
        if x["store_count"] < 2
    ]

    print()
    print("=" * 82)
    print("COVERAGE SUMMARY")
    print("=" * 82)
    print(
        f"✅ 3+ stores: {len(green)}"
    )
    print(
        f"🟡 2 stores:  {len(yellow)}"
    )
    print(
        f"🔴 0–1 store: {len(red)}"
    )

    print()
    print("INGREDIENTS WITH LESS THAN 2 STORES")
    print("-" * 82)

    if not red:
        print("✅ NONE — excellent coverage")
    else:
        for row in red:
            stores_text = (
                ", ".join(row["stores"].keys())
                if row["stores"]
                else "NONE"
            )

            print(
                f"{row['ingredient']:<45} "
                f"{row['store_count']} store(s) | "
                f"{stores_text}"
            )

    print()
    print("INGREDIENTS WITH EXACTLY 2 STORES")
    print("-" * 82)

    if not yellow:
        print("None")
    else:
        for row in yellow:
            print(
                f"{row['ingredient']:<45} "
                + ", ".join(row["stores"].keys())
            )

    output = Path("data/store_coverage_report.json")

    output.write_text(
        json.dumps(
            {
                "working_stores": WORKING_STORES,
                "summary": {
                    "ingredients": len(report),
                    "three_plus": len(green),
                    "two": len(yellow),
                    "less_than_two": len(red),
                },
                "ingredients": report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print()
    print("Saved:", output)
    print()
    print(
        "READ ONLY — database was not changed."
    )


if __name__ == "__main__":
    asyncio.run(main())

"""
OPTIONAL — seed provisional ingredient→product mappings.

This is deliberately NOT part of setup.sh. Choosing what to pour when a recipe
calls for a bottle you don't stock is a bar decision, not a software one, so
nothing here is applied unless you run it on purpose.

What it does: applies a small set of same-style substitutions so the shopping
list and buy links have something real in them on day one. Every mapping is
tagged PROVISIONAL and is listed, changeable, and removable on the Mapping
screen at /mappings.

Only pairings defensible on style grounds are included. Ingredients with no
genuine counterpart in the price file — house-made syrups, fresh lime, the
vermouths, Fernet, Dry Curaçao — are intentionally left unmapped, because
inventing a substitute for those would be a worse answer than saying "missing".

    python scripts/seed_provisional_mappings.py           # apply
    python scripts/seed_provisional_mappings.py --revert  # remove them again
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models import Ingredient, Product, IngredientProductMapping

PROVISIONAL_TAG = "PROVISIONAL"

# The source spreadsheets mix straight (') and curly (’) apostrophes, sometimes
# for the same product. Comparing raw strings makes "Jack Daniel's" silently
# fail to match "Jack Daniel’s" — a bug that is invisible in a diff because the
# two characters look nearly identical. Normalise before comparing.
_APOSTROPHES = {"’", "‘", "ʼ", "´", "`"}


def norm_name(name: str) -> str:
    out = name or ""
    for ch in _APOSTROPHES:
        out = out.replace(ch, "'")
    return " ".join(out.split()).casefold()

# ingredient canonical name -> (product's canonical name, rationale)
PAIRINGS: dict[str, tuple[str, str]] = {
    "Beefeater London Dry Gin": (
        "Bombay Sapphire Gin",
        "London Dry to London Dry; closest style match in the price file.",
    ),
    "Beluga Noble Vodka": (
        "Grey Goose Vodka",
        "Premium neutral vodka to premium neutral vodka.",
    ),
    "Sparkling Wine / Prosecco": (
        "Cava Iberica Sparkling Wine",
        "Dry sparkling wine; Cava fills the Prosecco role in a spritz or a French 75.",
    ),
    "Soda Water": (
        "Soda Water (Can)",
        "Same product — the price file lists it by the can.",
    ),
    "Four Roses Bourbon": (
        "Jack Daniel's Tennessee Whiskey",
        "Nearest American whiskey in the price file. Tennessee, not bourbon — "
        "sweeter and charcoal-filtered, so taste before committing.",
    ),
    "Havana Club Añejo 3 Años Rum": (
        "Canuca Rum",
        "Light/white rum stand-in for a 3-year Cuban style.",
    ),
}


async def apply(session) -> tuple[int, list[str]]:
    applied, skipped = 0, []

    # Load every ingredient once and index by normalised name, so apostrophe
    # style never decides whether a pairing lands.
    all_ing_r = await session.execute(select(Ingredient))
    by_norm: dict[str, Ingredient] = {
        norm_name(i.canonical_name): i for i in all_ing_r.scalars().all()
    }

    for ing_name, (product_canonical, rationale) in PAIRINGS.items():
        ingredient = by_norm.get(norm_name(ing_name))
        if ingredient is None:
            skipped.append(f"{ing_name}: ingredient not in database")
            continue

        existing_r = await session.execute(
            select(IngredientProductMapping).where(
                IngredientProductMapping.ingredient_id == ingredient.id
            )
        )
        if existing_r.scalars().first() is not None:
            skipped.append(f"{ing_name}: already mapped, left alone")
            continue

        # Find a product whose own ingredient carries the canonical name
        target = by_norm.get(norm_name(product_canonical))
        product = None
        if target is not None:
            prod_r = await session.execute(
                select(Product).where(Product.ingredient_id == target.id)
            )
            product = prod_r.scalars().first()
        if product is None:
            skipped.append(f"{ing_name}: no product '{product_canonical}' in catalog")
            continue

        session.add(IngredientProductMapping(
            ingredient_id=ingredient.id,
            product_id=product.id,
            preferred=True,
            substitution_allowed=True,
            notes=f"{PROVISIONAL_TAG} — {rationale} Review on the Mapping page.",
        ))
        applied += 1
        print(f"  ✅ {ing_name}")
        print(f"     → {product.name}   ({rationale})")

    return applied, skipped


async def revert(session) -> int:
    result = await session.execute(
        select(IngredientProductMapping).where(
            IngredientProductMapping.notes.like(f"{PROVISIONAL_TAG}%")
        )
    )
    rows = result.scalars().all()
    for row in rows:
        await session.delete(row)
    return len(rows)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revert", action="store_true",
                        help="remove previously seeded provisional mappings")
    args = parser.parse_args()

    print("=" * 62)
    print("PROVISIONAL MAPPINGS — " + ("REVERT" if args.revert else "APPLY"))
    print("=" * 62)

    async with AsyncSessionLocal() as session:
        if args.revert:
            n = await revert(session)
            await session.commit()
            print(f"\nRemoved {n} provisional mapping(s).")
            return

        applied, skipped = await apply(session)
        await session.commit()

        print()
        print(f"Applied {applied} provisional mapping(s).")
        if skipped:
            print(f"\nSkipped {len(skipped)}:")
            for s in skipped:
                print(f"  · {s}")
        print()
        print("These are starting points, not decisions. Review them at")
        print("  http://localhost:3000/mappings")
        print("Undo with:  python scripts/seed_provisional_mappings.py --revert")


if __name__ == "__main__":
    asyncio.run(main())

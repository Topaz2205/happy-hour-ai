"""
Say which spirits can stand in for which.

    python scripts/set_substitute_groups.py [--apply]

WHY
---
A recipe names a bottle — "Havana Club Añejo 3 Años Rum". No Israeli shop
researched stocks that exact bottle, but every one of them sells white rum.
Until now the system could only offer a product already mapped to that precise
ingredient, so those shops reported "not stocked here" and their buy links led
to a search with no results — while a perfectly good rum sat on the shelf.

Topaz's rule, and it is hers to make: any rum will do. The brand in the recipe
is a preference, not a requirement.

WHAT IS AND IS NOT GROUPED
--------------------------
Grouped: the base spirits, where one bottle of the type genuinely substitutes
for another. A daiquiri made with Bacardi instead of Havana Club is a daiquiri.

NOT grouped, deliberately: Campari, Aperol, Fernet Branca, Green Chartreuse,
Luxardo Maraschino, Suze, Kina L'Aero d'Or. Nothing else tastes like any of
them, and a "negroni" with a different red bitter is a different drink. Leaving
them ungrouped means the system says "not stocked" — which is true, and more
useful than a substitution nobody asked for.

Vermouth is grouped by colour but not by brand tier, because sweet vermouth is
sweet vermouth; the difference between Martini Rosso and Gancia is real but it
is a preference, not a category error.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models import Ingredient

# ingredient canonical_name → substitute group
GROUPS: dict[str, str] = {
    # ── Base spirits: interchangeable within type ──────────────────────────
    "Beefeater London Dry Gin": "gin",
    "Beluga Noble Vodka": "vodka",
    "Olmeca Silver Tequila": "blanco_tequila",
    "Havana Club Añejo 3 Años Rum": "white_rum",
    "Four Roses Bourbon": "whiskey",
    "Rittenhouse Rye Whiskey": "whiskey",
    "Cognac VS": "cognac",

    # ── Vermouth: by colour, which is what the recipe cares about ──────────
    "Red Vermouth": "sweet_vermouth",
    "Mancino Bianco Vermouth": "bianco_vermouth",
    "Mancino Secco Dry Vermouth": "dry_vermouth",

    # ── Sparkling: prosecco, cava and crémant all do the job ───────────────
    "Sparkling Wine / Prosecco": "sparkling_wine",
    "קאווה איבריקה": "sparkling_wine",

    # ── Orange liqueur: triple sec, curaçao and Cointreau are one family ───
    # Not identical — Pierre Ferrand is drier than Cointreau — but any of them
    # makes a margarita, and none of them makes it a different drink.
    "Dry Curacao Pierre Ferrand": "orange_liqueur",

    # ── Mixers ─────────────────────────────────────────────────────────────
    "Soda Water": "soda",
    "סודה": "soda",
    "Ginger Beer": "ginger_beer",
}

# Named so the reasoning survives, and so nobody later "fixes" the omission.
DELIBERATELY_UNGROUPED = {
    "Campari": "Nothing else is Campari. A negroni with a different red bitter "
               "is a different drink.",
    "אפרול": "Same. Aperol is not interchangeable with Campari — different "
             "strength, different sweetness.",
    "Fernet Branca": "Unmistakable and unsubstitutable.",
    "Green Chartreuse": "Made by monks to a secret recipe. There is no equivalent.",
    "Luxardo Maraschino": "Other maraschinos are sweeter cherry liqueurs and "
                          "behave differently in a drink.",
    "Kina L'Aero D'Or": "A specific quinquina. Lillet is close but not the same.",
    "Crème de Cacao": "Chocolate liqueurs vary enormously; not swappable blind.",
    "Angostura Aromatic Bitters": "The reference aromatic bitter. Others are "
                                  "different, not equivalent.",
}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    set_, missing, cleared = [], [], []

    async with AsyncSessionLocal() as db:
        for name, group in GROUPS.items():
            ing = (await db.execute(
                select(Ingredient).where(Ingredient.canonical_name == name)
            )).scalars().first()
            if ing is None:
                missing.append(name)
                continue
            set_.append((name, group))
            if args.apply:
                ing.substitute_group = group

        # Explicit is better than absent: anything named as unsubstitutable has
        # its group cleared, so a stale value from an earlier run cannot linger.
        for name in DELIBERATELY_UNGROUPED:
            ing = (await db.execute(
                select(Ingredient).where(Ingredient.canonical_name == name)
            )).scalars().first()
            if ing is not None and ing.substitute_group is not None:
                cleared.append(name)
                if args.apply:
                    ing.substitute_group = None

        if args.apply:
            await db.commit()

    by_group: dict[str, list[str]] = {}
    for name, group in set_:
        by_group.setdefault(group, []).append(name)

    for group, names in sorted(by_group.items()):
        print(f"  {group:<18} {', '.join(names)}")
    print(f"\n{len(set_)} ingredient(s) grouped.")
    if cleared:
        print(f"{len(cleared)} cleared: {', '.join(cleared)}")
    if missing:
        print(f"{len(missing)} not in this database: {', '.join(missing)}")
    print(f"\n{len(DELIBERATELY_UNGROUPED)} left unsubstitutable on purpose — "
          f"see DELIBERATELY_UNGROUPED for why each.")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

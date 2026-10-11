"""
Take a cocktail out of the app.

    python scripts/remove_cocktail.py "Bellini"
    python scripts/remove_cocktail.py "Bellini" "Basil Smash (Classic)"
    python scripts/remove_cocktail.py --list-removed
    python scripts/remove_cocktail.py --restore "Bellini"

By default this deactivates rather than erases: every query in the app filters
on `active`, so a deactivated cocktail disappears completely — from the menu,
from search, from the planner — but the recipe stays in the database and can be
brought back. Deleting rows outright would also destroy any past event that
used the drink, and with it the record of what that event actually cost.

Use --purge to erase permanently. It refuses if a past event used the cocktail,
because that would silently corrupt the event's history.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models import Cocktail, CocktailIngredient, EventMenuItem


async def _find(session, name: str):
    r = await session.execute(
        select(Cocktail).where(func.lower(Cocktail.name) == name.lower())
    )
    c = r.scalar_one_or_none()
    if c:
        return c
    r = await session.execute(
        select(Cocktail).where(Cocktail.name.ilike(f"%{name}%"))
    )
    matches = r.scalars().all()
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"  '{name}' matches more than one cocktail — be exact:")
        for m in matches:
            print(f"     {m.name}")
    return None


async def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="cocktail names, in quotes")
    ap.add_argument("--purge", action="store_true", help="erase permanently")
    ap.add_argument("--restore", action="store_true", help="bring back a deactivated cocktail")
    ap.add_argument("--list-removed", action="store_true")
    args = ap.parse_args()

    async with AsyncSessionLocal() as session:
        if args.list_removed:
            r = await session.execute(
                select(Cocktail).where(Cocktail.active == False).order_by(Cocktail.name)
            )
            gone = r.scalars().all()
            if not gone:
                print("Nothing has been removed.")
                return
            print(f"{len(gone)} cocktail(s) currently removed from the app:\n")
            for c in gone:
                print(f"  {c.name}")
            print('\nRestore one with:\n  python scripts/remove_cocktail.py --restore "NAME"')
            return

        if not args.names:
            ap.print_help()
            return

        for name in args.names:
            cocktail = await _find(session, name)
            if cocktail is None:
                print(f"  ✗ no cocktail called '{name}'")
                continue

            if args.restore:
                cocktail.active = True
                print(f"  ✅ restored: {cocktail.name}")
                continue

            used_r = await session.execute(
                select(func.count()).select_from(EventMenuItem)
                .where(EventMenuItem.cocktail_id == cocktail.id)
            )
            used_by = used_r.scalar_one()

            if args.purge:
                if used_by:
                    print(f"  ✗ {cocktail.name}: used by {used_by} past event(s). "
                          f"Erasing it would corrupt their cost history.")
                    print(f"    Deactivate instead (drop --purge) — it disappears from "
                          f"the app either way.")
                    continue
                ing_r = await session.execute(
                    select(CocktailIngredient)
                    .where(CocktailIngredient.cocktail_id == cocktail.id)
                )
                for line in ing_r.scalars().all():
                    await session.delete(line)
                await session.delete(cocktail)
                print(f"  ✅ erased: {cocktail.name}")
            else:
                cocktail.active = False
                note = f" (kept for {used_by} past event(s))" if used_by else ""
                print(f"  ✅ removed from the app: {cocktail.name}{note}")

        await session.commit()

        left = await session.execute(
            select(func.count()).select_from(Cocktail).where(Cocktail.active == True)
        )
        print(f"\n{left.scalar_one()} cocktails still active.")


if __name__ == "__main__":
    asyncio.run(main())

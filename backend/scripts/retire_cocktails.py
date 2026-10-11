"""
Take cocktails out of the catalogue, by name.

    python scripts/retire_cocktails.py                    # show the standing list
    python scripts/retire_cocktails.py --apply
    python scripts/retire_cocktails.py --name "Bellini" --apply
    python scripts/retire_cocktails.py --restore --name "Bellini" --apply

WHY A GENERAL SCRIPT
--------------------
This is the third time a specific cocktail has had to go, and each previous one
got its own single-purpose script. That does not scale and it hides the record:
the list below IS the record of what was removed and why, in one place, and it
is re-runnable. If a database somewhere is out of step — a machine that missed a
run, a fresh clone — running this brings it back in line rather than requiring
someone to remember which one-off script to use.

DEACTIVATE, NOT DELETE
----------------------
Rows are marked inactive. An event planned earlier with one of these still reads
correctly; a shopping list that refers to a cocktail which no longer exists does
not. Every query in the app filters on `active`, so an inactive cocktail is
invisible in the product without being destroyed — and `--restore` undoes it.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models import Cocktail, EventMenuItem

# name → why it went. Matching is case-insensitive and ignores surrounding
# whitespace, but is otherwise exact: a LIKE would eventually catch a cocktail
# nobody meant to remove.
RETIRED: dict[str, str] = {
    "Bellini":               "Topaz: not part of the offering.",
    "Basil Smash (Classic)": "Topaz: dropped along with the basil syrup.",
    "Basil Smash Highball":  "Topaz: dropped along with the basil syrup.",
    "Savoia Americano":      "Topaz: not part of the offering.",
}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="make the change")
    ap.add_argument("--name", action="append", default=None,
                    help="act on this cocktail instead of the standing list")
    ap.add_argument("--restore", action="store_true", help="reactivate instead")
    args = ap.parse_args()

    targets = args.name if args.name else list(RETIRED)
    want_active = args.restore
    verb = "Restoring" if args.restore else "Retiring"

    changed, already, missing = [], [], []

    async with AsyncSessionLocal() as db:
        for name in targets:
            row = (await db.execute(
                select(Cocktail).where(
                    func.lower(func.trim(Cocktail.name)) == name.strip().lower())
            )).scalars().first()

            if row is None:
                missing.append(name)
                continue
            if row.active == want_active:
                already.append(row.name)
                continue

            used = (await db.execute(
                select(func.count()).select_from(EventMenuItem)
                .where(EventMenuItem.cocktail_id == row.id)
            )).scalar_one()
            changed.append((row.name, used, RETIRED.get(name, "")))
            if args.apply:
                row.active = want_active

        if args.apply:
            await db.commit()

    print(f"{verb} {len(targets)} cocktail(s)\n")
    for name, used, why in changed:
        note = f"  — {used} event(s) already use it, history kept" if used else ""
        print(f"  → {name}{note}")
        if why:
            print(f"      {why}")
    for name in already:
        print(f"  · {name} — already {'active' if want_active else 'retired'}")
    for name in missing:
        print(f"  ? {name} — no cocktail by that name in this database")

    if not changed:
        print("\nNothing to change.")
    elif not args.apply:
        print(f"\nDry run. Re-run with --apply to change {len(changed)}.")
    else:
        print(f"\n✓ {len(changed)} changed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

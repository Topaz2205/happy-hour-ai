"""
Check that the live schema matches what the code expects — and repair it.

WHY THIS EXISTS
---------------
`alembic upgrade head` only applies migrations Alembic believes are pending.
If a database's alembic_version row says it is current while a column is
actually stale — a database created before a migration existed, a version
stamped by hand, a table recreated by create_all — then upgrading is a no-op
and nothing reports a problem. The failure surfaces much later as a confusing
error about the *data*: "null value in column budget violates not-null
constraint", when the row was perfectly valid and the column was wrong.

This checks the handful of properties the application actually depends on,
reports what it finds, and repairs drift. Each entry says why the column is
the way it is, so a future change is a decision rather than a mystery.

    python scripts/verify_schema.py           # check and repair
    python scripts/verify_schema.py --check   # report only, exit 1 on drift
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import engine

# (table, column, property, expected, repair SQL, why)
EXPECTATIONS = [
    ("events", "budget", "is_nullable", "YES",
     "ALTER TABLE events ALTER COLUMN budget DROP NOT NULL",
     "Plenty of real events are planned before anyone sets a budget. The "
     "engine already treats a missing budget as 'cost it, report no over/under "
     "status'; requiring one here would mean inventing a number."),
    ("suppliers", "is_retailer", "exists", True,
     "ALTER TABLE suppliers ADD COLUMN is_retailer BOOLEAN NOT NULL DEFAULT false",
     "Separates a shop you can order from a price-book record imported from a "
     "spreadsheet."),
    ("suppliers", "search_url_template", "exists", True,
     "ALTER TABLE suppliers ADD COLUMN search_url_template VARCHAR(500)",
     "The shop's own verified search endpoint, used to build buy links."),
    ("suppliers", "prefers_hebrew_query", "exists", True,
     "ALTER TABLE suppliers ADD COLUMN prefers_hebrew_query BOOLEAN NOT NULL DEFAULT true",
     "Israeli shops index local trade names, so Hebrew search terms win."),
    ("suppliers", "minimum_order", "exists", True,
     "ALTER TABLE suppliers ADD COLUMN minimum_order NUMERIC(10,2)",
     "The smallest order a shop accepts. Separate from delivery, and the "
     "constraint that actually blocks a small basket — the juice supplier "
     "will not take an order under ₪200 however cheap the juice is."),
    ("ingredients", "substitute_group", "exists", True,
     "ALTER TABLE ingredients ADD COLUMN substitute_group VARCHAR(50)",
     "Lets one white rum stand in for another without letting a gin do it. "
     "Category is too coarse for that; this is the finer grouping."),
]


async def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report only, do not repair")
    args = ap.parse_args()

    drift, repaired = [], []

    async with engine.begin() as conn:
        for table, column, prop, expected, repair_sql, why in EXPECTATIONS:
            row = (await conn.execute(text("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = :t AND column_name = :c
            """), {"t": table, "c": column})).first()

            if prop == "exists":
                actual_ok = row is not None
            else:
                actual_ok = row is not None and row[0] == expected
                if row is None:
                    actual_ok = False

            if actual_ok:
                continue

            found = "missing" if row is None else f"{prop}={row[0]}"
            drift.append((table, column, found, why))

            if args.check:
                continue
            try:
                await conn.execute(text(repair_sql))
                repaired.append(f"{table}.{column}")
            except Exception as e:
                print(f"  ✗ could not repair {table}.{column}: {e}")

    if not drift:
        print("✓ Schema matches what the code expects.")
        return 0

    print(f"Found {len(drift)} column(s) out of step with the code:\n")
    for table, column, found, why in drift:
        print(f"  {table}.{column}  ({found})")
        print(f"      {why}\n")

    if args.check:
        print("Run without --check to repair.")
        return 1

    if repaired:
        print("✓ Repaired: " + ", ".join(repaired))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

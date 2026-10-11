"""
Load the public Happy Hour AI dataset into an empty PostgreSQL database.

The public dataset contains:
- classic cocktail recipes
- ingredients
- products and mappings
- public retailer listings and price snapshots
- equipment
- house-made / supermarket purchase channels

It deliberately excludes private business data, private signature recipes,
historical BOM prices, companies and user-created events.

Safe to re-run: inserts use ON CONFLICT DO NOTHING.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import MetaData, Table
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.sqltypes import Date, DateTime

from app.db.session import engine


SEED_FILE = Path(__file__).parent / "public_data" / "public_seed.json"

TABLE_ORDER = [
    "ingredients",
    "cocktails",
    "products",
    "suppliers",
    "cocktail_ingredients",
    "ingredient_aliases",
    "supplier_products",
    "ingredient_product_mapping",
]


def convert_value(column, value):
    if value is None:
        return None

    if isinstance(column.type, PGUUID):
        if isinstance(value, UUID):
            return value
        return UUID(str(value))

    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    if isinstance(column.type, Date) and isinstance(value, str):
        return date.fromisoformat(value)

    return value


def validate_seed(data):
    required = set(TABLE_ORDER)

    missing_sections = required - set(data)
    if missing_sections:
        raise RuntimeError(
            "Public seed missing sections: "
            + ", ".join(sorted(missing_sections))
        )

    private_names = {
        "Private Historical Prices",
        "Manual Entry",
    }

    supplier_names = {
        supplier.get("name")
        for supplier in data.get("suppliers", [])
    }

    leaked = private_names & supplier_names

    if leaked:
        raise RuntimeError(
            "Private suppliers found in public seed: "
            + ", ".join(sorted(leaked))
        )

    cocktail_names = {
        cocktail.get("name")
        for cocktail in data.get("cocktails", [])
    }

    if len(cocktail_names) != 30:
        raise RuntimeError(
            f"Expected 30 public cocktails, found {len(cocktail_names)}"
        )


async def reflect_table(conn, name):
    def load(sync_conn):
        metadata = MetaData()
        return Table(name, metadata, autoload_with=sync_conn)

    return await conn.run_sync(load)


async def seed():
    if not SEED_FILE.exists():
        raise RuntimeError(f"Public seed file not found: {SEED_FILE}")

    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    validate_seed(data)

    print("Happy Hour AI — Public Seed")
    print("===========================")
    print(f"Source: {SEED_FILE}")
    print()

    async with engine.begin() as conn:
        for table_name in TABLE_ORDER:
            rows = data.get(table_name, [])

            if not rows:
                print(f"- {table_name}: 0 rows")
                continue

            table = await reflect_table(conn, table_name)
            allowed_columns = set(table.c.keys())

            converted_rows = []

            for row in rows:
                converted = {}

                for key, value in row.items():
                    if key not in allowed_columns:
                        continue

                    converted[key] = convert_value(
                        table.c[key],
                        value,
                    )

                converted_rows.append(converted)

            stmt = (
                pg_insert(table)
                .values(converted_rows)
                .on_conflict_do_nothing()
            )

            result = await conn.execute(stmt)

            print(
                f"- {table_name}: "
                f"{len(converted_rows)} seed rows "
                f"({result.rowcount} inserted)"
            )

    print()
    print("✅ Public seed complete")


if __name__ == "__main__":
    asyncio.run(seed())

"""
Add the suppliers researched on 23 Aug 2026.

    python scripts/add_suppliers_2026_08.py [--apply]

Every URL below was loaded successfully during research. None is guessed.

ON SEARCH PATTERNS — READ BEFORE ADDING MORE
--------------------------------------------
A search URL is only recorded where a search was actually executed and the page
came back with the query echoed and matching products. Several of these sites
run WooCommerce and look like they must accept `?s=`, and testing that exact
assumption returned the homepage or was blocked by robots.txt. A guessed pattern
does not fail loudly — it silently sends a customer to a homepage or a 404 while
the button still says "buy". Sites without a verified pattern get a homepage
link, which is honest about what it can do.

Two patterns are marked PARTIAL: the endpoint is real and returns a search page,
but results are rendered by JavaScript so the fetch could not confirm they track
the query. They are stored as homepage links until someone checks in a browser.
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models import Supplier

# name_he, name_en, url, search_template|None, category, note
# `note` is documentation for whoever reads this file — the Supplier table
# has no notes column, and adding one for prose was not worth a migration.
SUPPLIERS = [
    # ── Equipment — the three Topaz named ──────────────────────────────────
    ("ארגל", "Argal", "https://shop.argal.co.il/", None, "equipment",
     "Serving and bar equipment. Real webshop with wholesale pricing to private "
     "customers, free delivery over ₪400, showrooms in TLV/Haifa/Jerusalem. Has a "
     "'הקוקטייל המושלם' category. Search is robots-blocked — homepage link only."),

    ("\"אול סאל\" טרדינג ירושלים", "Wholesale Trading",
     "https://www.wholesale-trading.co.il/", None, "equipment",
     "B2B catalogue, 10,000+ SKUs, 40 years. Bar section: pourers, shakers, bar "
     "mats, glass washers, bottle racks. No public prices — needs an account. "
     "NOTE: not the same company as olsale.co.il, which is unrelated."),

    ("יעקב סוכנויות יבוא יצוא", "Jacobs Agencies",
     "https://www.jacobsagencies.com/", None, "equipment",
     "Wholesale importer, Rishon LeZion. Real bar glassware range — coupes, "
     "Nick & Nora, gimlet, hi/low-ball. Minimum order applies, no public prices."),

    # ── Equipment — found, and the two best fits ───────────────────────────
    ("קוקטייל ארט", "Cocktail Art", "https://cocktailart.co.il/",
     "https://cocktailart.co.il/?s={query}&post_type=product", "equipment",
     "Pure-play cocktail and bar specialist. Search VERIFIED — a query for "
     "'שייקר' returned Cobbler and Tin-Tin shakers. Best category fit found."),

    ("אקוויפ", "EQUIP", "https://equip-online.co.il/",
     "https://equip-online.co.il/?s={query}&post_type=product", "equipment",
     "Foodservice equipment with a 'ציוד בר וקוקטיילים' category. Search "
     "VERIFIED with live prices. Cheapest verified equipment seen. Free "
     "delivery over ₪299."),

    ("בר פרודקטס ישראל", "Bar Products Israel", "https://www.barproducts.co.il/",
     None, "equipment",
     "Cocktail tooling, free delivery over ₪599. Search endpoint is real and "
     "echoes the query, but results are JS-rendered and unconfirmed — PARTIAL, "
     "so homepage only until checked in a browser."),

    ("שופבר", "ShopBar", "https://shopbar.co.il/", None, "equipment",
     "Shakers, jiggers, strainers, muddlers, tiki and acrylic glassware, plus "
     "party extras. Free delivery over ₪299. Both `?s=` and `/search?q=` were "
     "tested and both failed — homepage only."),

    # ── Alcohol ───────────────────────────────────────────────────────────
    ("דרך היין", "Wine Route", "https://www.wineroute.co.il/", None, "alcohol",
     "Largest wine retailer in Israel by its own claim; also whisky, beer, "
     "cider. Members club pricing, free delivery over ₪300, many branches. "
     "Search returned 404 on the pattern tested — homepage only."),

    ("משקאות המשמח", "Hamesameach", "https://www.hamesameach.co.il/", None, "alcohol",
     "Boutique wine plus a wide spirits range. Runs mix-and-match deals "
     "(2 bottles ₪109) which matter for event buying. Free delivery over ₪399 — "
     "the lowest threshold found. Search returned the homepage — not recorded."),

    ("עולם היין", "Olam HaYain", "https://olamhayain.co.il/", None, "alcohol",
     "Wholesale-and-retail spirits and wine, physical stores, free delivery "
     "over ₪299. Search returned the homepage on both patterns tested."),

    ("בית היין", "Wine House", "https://winehouse.co.il/", None, "alcohol",
     "Wine and full spirits range, TLV and Netanya. Free delivery over ₪600. "
     "Search is robots-blocked — homepage only."),

    ("איידרינק", "iDrink", "https://www.idrink.co.il/", None, "alcohol",
     "Broad spirits range at near-wholesale pricing. Search endpoint is real "
     "but returned identical results for two different queries — PARTIAL, so "
     "homepage only until confirmed."),
]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    added, skipped = [], []
    async with AsyncSessionLocal() as db:
        for name_he, name_en, url, search, category, note in SUPPLIERS:
            existing = (await db.execute(
                select(Supplier).where(Supplier.name == name_he)
            )).scalar_one_or_none()
            if existing:
                skipped.append(name_he)
                continue
            added.append((name_he, name_en, "search" if search else "homepage", category))
            if args.apply:
                db.add(Supplier(
                    name=name_he,
                    is_retailer=True,
                    search_url_template=search,
                    prefers_hebrew_query=True,
                    website=url,
                ))
        if args.apply:
            await db.commit()

    print(f"{len(added)} to add, {len(skipped)} already present\n")
    for name_he, name_en, kind, cat in added:
        mark = "search ✓" if kind == "search" else "homepage"
        print(f"  {cat:<10} {mark:<9} {name_he}  ({name_en})")
    print(f"\n{sum(1 for a in added if a[2]=='search')} of {len(added)} have a "
          f"verified search pattern. The rest link to the homepage on purpose.")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""
A price you cannot order is not a price.

WHY THIS FILE EXISTS
--------------------
Two separate faults hid the same real product, and both were silent.

The first: the juice supplier's lime juice had been priced from a live page
since the first round of research — ₪19 for a litre — and the shop comparison
never showed it. `/compare-shops` filters on `Supplier.is_retailer`, which is
right, but the legacy data import created its suppliers without setting the flag and it
defaults to false. A real shop was filed as a spreadsheet row, and every liquor
shop truthfully reported "Fresh Lime Juice — not stocked here", which together
read as though nobody sells lime juice.

The second: that shop takes no order under ₪200. An event needs one bottle.
Showing ₪19 and stopping there quotes a price for an order the shop refuses.

So: retailer status and minimum order are explicit facts in the public dataset,
and the comparison carries those facts through to the buying experience.
"""
import sys
import re
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

BACKEND = Path(__file__).parent.parent
EVENTS = (BACKEND / "app" / "api" / "events.py").read_text(encoding="utf-8")
MODEL = (BACKEND / "app" / "models" / "supplier.py").read_text(encoding="utf-8")
PUBLIC_SEED = json.loads(
    (BACKEND / "scripts" / "public_data" / "public_seed.json").read_text(encoding="utf-8")
)
SUPPLIERS = {s["name"]: s for s in PUBLIC_SEED["suppliers"]}
SUPPLIER_PRODUCTS = PUBLIC_SEED["supplier_products"]
VERIFY = (BACKEND / "scripts" / "verify_schema.py").read_text(encoding="utf-8")


class TestTheMinimumIsCarriedAllTheWay:
    def test_the_supplier_can_hold_one(self):
        assert "minimum_order" in MODEL

    def test_it_is_nullable(self):
        """
        "This shop publishes no minimum" and "this shop's minimum is zero" are
        different statements, and only the first is true of most shops. A
        non-nullable column with a 0 default would assert the second everywhere.
        """
        line = next(l for l in MODEL.splitlines() if "minimum_order" in l
                    and "mapped_column" in l)
        assert "float | None" in line
        assert "nullable=False" not in line

    def test_the_comparison_reports_it(self):
        for field in ("minimum_order", "below_minimum", "short_of_minimum_by"):
            assert field in EVENTS, f"/compare-shops does not report {field}"

    def test_the_split_reports_which_legs_fall_under(self):
        """
        Splitting is exactly what shrinks each shop's share, so the split is
        where a minimum bites hardest. It must not be reported only per shop.
        """
        assert "split_below_minimum" in EVENTS
        assert '"below_minimum": split_below_minimum' in EVENTS

    def test_the_shortfall_is_reported_not_just_the_fact(self):
        """
        "Under the minimum" ends the conversation; "₪181 short" continues it.
        """
        assert "short_of_minimum_by" in EVENTS
        assert "short_by" in EVENTS


class TestBelowMinimumIsNotConflatedWithUnknownDelivery:
    def test_they_are_separate_fields(self):
        """
        An unknown delivery cost makes a total unquotable. A minimum makes the
        order impossible. Collapsing them would tell the buyer to phone the shop
        when what they actually need to do is buy more.
        """
        assert "delivered_total_unknown_because" in EVENTS
        assert "below_minimum" in EVENTS
        # and the minimum must not be folded into the delivery decision
        # Exactly the delivery decision, and nothing after it. Running the
        # window on to shops.append swept in the minimum's own calculation,
        # which sits between the two and is not part of the decision.
        window = EVENTS[EVENTS.index("clears = free_over is not None"):]
        window = window[:window.index("delivery, delivery_known = None, False")]
        # Comments are stripped first. The paragraph explaining *why* the two are
        # separate sits in this window and would otherwise trip the check that
        # they are — the scan must read the code, not the prose about it.
        window = "\n".join(l for l in window.splitlines()
                           if not l.strip().startswith("#"))
        assert "minimum" not in window, (
            "the minimum leaked into the delivery calculation; it is a separate "
            "constraint and must not change whether a delivered total is known")


class TestZeroIsNotTreatedAsAbsent:
    def test_the_guard_uses_is_not_none(self):
        """
        Same trap as the budget. `if minimum` treats a published ₪0 minimum as
        no minimum — harmless here, but the habit is what caused a 500 in the
        budget code, so it is pinned rather than left to luck.
        """
        for line in EVENTS.splitlines():
            if "minimum" in line and re.search(r"\bif\s+minimum\b\s*(and|:|\))", line):
                assert "is not None" in line, f"truthiness guard: {line.strip()}"


class TestTheRetailerFlagIsSetDeliberately:
    def test_sahut_is_a_retailer(self):
        assert SUPPLIERS["סחוט (Sahut)"].get("is_retailer") is True

    def test_non_shops_stay_non_retailers(self):
        for name in ("House-made", "Supermarket"):
            assert SUPPLIERS[name].get("is_retailer") is not True

        assert "Manual Entry" not in SUPPLIERS

    def test_sahut_minimum_order_is_public_data(self):
        assert SUPPLIERS["סחוט (Sahut)"].get("minimum_order") == 200

    def test_sahut_listings_have_a_purchase_destination(self):
        supplier = SUPPLIERS["סחוט (Sahut)"]
        supplier_id = supplier["id"]

        listings = [
            row for row in SUPPLIER_PRODUCTS
            if row["supplier_id"] == supplier_id
        ]

        assert listings

        for row in listings:
            assert (
                row.get("product_url")
                or supplier.get("search_url_template")
                or supplier.get("website")
            )


class TestSchemaDriftIsDetectable:
    def test_verify_schema_knows_about_the_new_column(self):
        """
        `alembic upgrade head` reporting success is not proof the column exists —
        that lesson cost a day. Every column the app depends on is listed here.
        """
        assert "minimum_order" in VERIFY

    def test_it_also_knows_about_substitute_group(self):
        assert "substitute_group" in VERIFY

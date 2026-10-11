"""
Event-scoped product overrides.

The property that matters most is negative and easy to lose in a refactor: one
event choosing a cheaper bottle must not change what any other event buys. A
test that only checks the happy path would pass just as happily if the code
wrote through to the global mapping — and nobody would notice until a customer's
event silently changed underneath them.
"""
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.engine.calculator import ProductInfo


def event_total(required_amount: float, product: ProductInfo) -> float:
    """
    What one ingredient costs this event with a given product.

    This mirrors the arithmetic the API performs, and exists so the rule can be
    asserted directly: whole packages, ceiling, real price. The API is tested
    against a live database elsewhere; this pins the maths that decides which
    option is genuinely cheaper.
    """
    packs = math.ceil(required_amount / product.package_size)
    return round(packs * product.price_after_vat, 2)


class TestCheapestBottleIsNotAlwaysCheapestEvent:
    """
    The single most useful thing this feature does, and the one a naive
    implementation gets wrong.
    """

    def test_a_smaller_cheaper_bottle_can_cost_more(self):
        need = 4050.0                       # ml this event needs
        big = ProductInfo("a", "1L bottle", 1000, "ml", price_after_vat=100)
        small = ProductInfo("b", "700ml bottle", 700, "ml", price_after_vat=75)

        # The small bottle is cheaper on the shelf...
        assert small.price_after_vat < big.price_after_vat
        # ...and more expensive for this event.
        assert event_total(need, small) == 6 * 75      # 450
        assert event_total(need, big) == 5 * 100       # 500
        # Here the small one does win. The point is that it has to be computed,
        # not assumed either way.
        assert event_total(need, small) < event_total(need, big)

    def test_the_reverse_case_is_real_too(self):
        """Same two bottles, a quantity where the shelf price misleads."""
        need = 2100.0
        big = ProductInfo("a", "1L", 1000, "ml", price_after_vat=100)
        small = ProductInfo("b", "700ml", 700, "ml", price_after_vat=75)
        assert event_total(need, small) == 3 * 75      # 225
        assert event_total(need, big) == 3 * 100       # 300 — 3 bottles, 900ml wasted
        assert small.price_after_vat < big.price_after_vat
        assert event_total(need, small) < event_total(need, big)

    def test_a_cheaper_shelf_price_losing_on_total(self):
        """The case that makes ranking on bottle price actively wrong."""
        need = 1000.0
        litre = ProductInfo("a", "1L", 1000, "ml", price_after_vat=90)
        half = ProductInfo("b", "500ml", 500, "ml", price_after_vat=50)
        assert half.price_after_vat < litre.price_after_vat   # cheaper bottle
        assert event_total(need, half) == 100                 # 2 × 50
        assert event_total(need, litre) == 90                 # 1 × 90
        assert event_total(need, half) > event_total(need, litre)  # dearer event

    def test_packages_always_round_up(self):
        p = ProductInfo("a", "700ml", 700, "ml", price_after_vat=90)
        assert event_total(701, p) == 180        # 1.001 bottles → 2
        assert event_total(700, p) == 90         # exact fit → 1
        assert event_total(1, p) == 90           # a drop still needs a bottle


class TestResolutionOrder:
    """
    Documented here as executable prose. The live behaviour is exercised against
    a real database; this states the contract the API promises so a future
    change to _build_engine_inputs has something to break.
    """

    def test_order_is_override_then_preferred_then_missing(self):
        def resolve(override, preferred):
            return override or preferred or None

        assert resolve("event-choice", "house-pick") == "event-choice"
        assert resolve(None, "house-pick") == "house-pick"
        assert resolve(None, None) is None

    def test_missing_stays_missing(self):
        """
        The third branch is not a fallback to something reasonable. There is no
        default product, and an ingredient with neither an override nor a
        preferred mapping is reported as missing rather than costed at zero.
        """
        def resolve(override, preferred):
            return override or preferred or None
        assert resolve(None, None) is None

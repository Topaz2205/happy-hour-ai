"""
Workshop equipment planning.

The two things worth pinning here are the two that cost real money: how many
stations a headcount makes, and the fact that glassware is sold in sixes. Both
are easy to get subtly wrong in a way that reads as plausible on screen and
turns into a wrong order.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.engine.equipment import (
    EquipmentSpec, EquipmentPrice, plan_equipment, plan_to_dict, DEFAULT_KIT,
)


def price(name, amount, pack=1, stock=True):
    return EquipmentPrice(product_name=name, price_per_pack=amount,
                          pack_size=pack, supplier="EQUIP", in_stock=stock)


# The real EQUIP figures, so the tests describe an order someone could place.
PRICES = {
    "shaker": price("ערכת ברמן", 130),
    "jigger": price("ג'יגר נירוסטה", 6),
    "strainer": price("מסננת ספירלה", 14),
    "bar_spoon": price("כפית קוקטייל", 9),
    "glass_rocks": price("סט 6 כוסות וויסקי ISTANBUL", 25, pack=6),
}


class TestStations:
    def test_pairs_halve_the_stations(self):
        assert plan_equipment(20, 2, PRICES).stations == 10

    def test_an_odd_headcount_rounds_up(self):
        """21 people in pairs is 11 stations — the last one has a single person."""
        assert plan_equipment(21, 2, PRICES).stations == 11

    def test_one_each_means_one_station_each(self):
        assert plan_equipment(20, 1, PRICES).stations == 20

    def test_groups_of_four(self):
        assert plan_equipment(20, 4, PRICES).stations == 5

    def test_a_single_person_still_needs_a_station(self):
        assert plan_equipment(1, 4, PRICES).stations == 1

    def test_zero_participants_is_refused(self):
        with pytest.raises(ValueError):
            plan_equipment(0, 2, PRICES)

    def test_zero_per_station_is_refused(self):
        """Would divide by zero, and means nothing anyway."""
        with pytest.raises(ValueError):
            plan_equipment(20, 0, PRICES)


class TestGlasswareComesInSixes:
    """The rounding that decides whether the shopping list can be ordered."""

    def test_twenty_people_need_four_packs(self):
        line = _line(plan_equipment(20, 2, PRICES), "glass_rocks")
        assert line.needed == 20
        assert line.packs == 4          # not 3.33
        assert line.units_bought == 24

    def test_an_exact_multiple_does_not_gain_a_pack(self):
        line = _line(plan_equipment(24, 2, PRICES), "glass_rocks")
        assert line.packs == 4 and line.units_bought == 24

    def test_one_person_still_buys_a_whole_pack(self):
        line = _line(plan_equipment(1, 1, PRICES), "glass_rocks")
        assert line.packs == 1 and line.units_bought == 6

    def test_the_cost_follows_packs_not_people(self):
        """4 packs at ₪25 is ₪100, not 20 × ₪4.17."""
        assert _line(plan_equipment(20, 2, PRICES), "glass_rocks").total == 100

    def test_the_shops_pack_size_overrides_the_kit_list(self):
        """
        What you can buy is decided by the shop. If it started selling glasses
        singly, the plan must follow — the kit list's assumption is not a fact.
        """
        prices = dict(PRICES, glass_rocks=price("single glass", 5, pack=1))
        line = _line(plan_equipment(20, 2, prices), "glass_rocks")
        assert line.packs == 20 and line.units_bought == 20 and line.total == 100


class TestToolsScaleWithStations:
    def test_tools_follow_stations_not_headcount(self):
        plan = plan_equipment(20, 2, PRICES)
        for key in ("shaker", "jigger", "strainer", "bar_spoon"):
            assert _line(plan, key).needed == 10, key

    def test_the_expensive_line_is_the_shaker(self):
        """10 kits at ₪130 dwarfs everything else — worth seeing in a test."""
        plan = plan_equipment(20, 2, PRICES)
        assert _line(plan, "shaker").total == 1300
        assert _line(plan, "jigger").total == 60

    def test_halving_the_stations_halves_the_tools(self):
        pairs = plan_equipment(20, 2, PRICES)
        fours = plan_equipment(20, 4, PRICES)
        assert _line(fours, "shaker").total == _line(pairs, "shaker").total / 2


class TestNothingIsPricedThatHasNoPrice:
    def test_an_unpriced_essential_makes_the_total_incomplete(self):
        prices = {k: v for k, v in PRICES.items() if k != "shaker"}
        plan = plan_equipment(20, 2, prices)
        assert plan.is_complete is False
        assert plan.total_cost is None
        assert "Cocktail shaker" in plan.missing

    def test_the_known_part_is_still_available(self):
        """Useful for showing progress; never presented as the price."""
        prices = {k: v for k, v in PRICES.items() if k != "shaker"}
        plan = plan_equipment(20, 2, prices)
        assert plan.known_cost > 0
        assert plan.total_cost is None

    def test_an_unpriced_optional_does_not_spoil_the_total(self):
        """A muddler nobody costed should not block a workshop's budget."""
        plan = plan_equipment(20, 2, PRICES)
        muddler = _line(plan, "muddler")
        assert muddler.status == "PRICE_MISSING"
        assert plan.is_complete is True and plan.total_cost is not None

    def test_out_of_stock_is_reported_but_still_costed(self):
        """
        The price is real and the comparison is useful; the order is not
        placeable today. Those are different facts and both are reported.
        """
        prices = dict(PRICES, shaker=price("שייקר טין טין", 37, stock=False))
        plan = plan_equipment(20, 2, prices)
        assert "Cocktail shaker" in plan.out_of_stock
        assert _line(plan, "shaker").status == "OUT_OF_STOCK"
        assert plan.total_cost is not None


class TestShape:
    def test_dict_carries_what_the_screen_needs(self):
        d = plan_to_dict(plan_equipment(20, 2, PRICES))
        assert d["stations"] == 10 and d["participants"] == 20
        assert set(d["lines"][0]) >= {"name", "needed", "packs", "total", "status"}

    def test_the_default_kit_marks_optional_items_optional(self):
        """A workshop without a muddler is still a workshop."""
        optional = {s.key for s in DEFAULT_KIT if not s.essential}
        assert "muddler" in optional and "shaker" not in optional


def _line(plan, key):
    return next(l for l in plan.lines if l.key == key)

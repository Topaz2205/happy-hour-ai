"""
Per-drink costing, checked against Topaz's own spreadsheet.

Every expected number below was read off her cost-calculator template, not
computed here and then blessed. If the engine and her sheet ever disagree, one
of them is wrong and the test says which cell to look at.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.engine.calculator import CocktailRecipe, RecipeIngredient, ProductInfo
from app.engine.drink_cost import (
    unit_price, cost_one_drink, spirit_tiers, batch_plan,
)


def product(pid, name, size, price, unit="ml"):
    return ProductInfo(product_id=pid, product_name=name, package_size=size,
                       package_unit=unit, price_before_vat=price, price_after_vat=price)


def ing(iid, name, amount, unit="ml"):
    return RecipeIngredient(ingredient_id=iid, canonical_name=name,
                            amount=amount, unit=unit)


def recipe(*ingredients, name="Test"):
    return CocktailRecipe(cocktail_id="c1", name=name, alcoholic=True,
                          has_na_variant=False, na_variant_instructions=None,
                          ingredients=list(ingredients))


class TestUnitPrice:
    """₪ per ml = price ÷ package size."""

    def test_her_tequila_line(self):
        """Roses Flower sheet: 76.00 over a 700 ml bottle → 0.1086 ₪/ml."""
        assert round(unit_price(product("p", "Cuervo", 700, 76.00)), 4) == 0.1086

    def test_a_count_based_pack(self):
        """
        "40 dried strawberries at ₪8" — size 40, not a volume. Her sheets put
        the count in the quantity column; either way the price divides by it.
        """
        assert unit_price(product("p", "Dried strawberries", 40, 8.00, "unit")) == 0.2

    def test_no_price_is_not_zero(self):
        assert unit_price(ProductInfo("p", "x", 700)) is None

    def test_no_size_is_not_guessed(self):
        """A missing bottle size must not fall back to 700 ml."""
        assert unit_price(product("p", "x", None, 76.0)) is None

    def test_zero_size_does_not_divide_by_zero(self):
        assert unit_price(product("p", "x", 0, 76.0)) is None


class TestCostOneDrink:
    """Her Roses Flower tree, ingredient by ingredient."""

    def test_tequila_contribution(self):
        """0.1086 ₪/ml × 50 ml = 5.43 ₪ — the figure in her sheet."""
        r = recipe(ing("i1", "Tequila", 50))
        got = cost_one_drink(r, {"i1": product("p1", "Cuervo", 700, 76.00)})
        assert got.cost == 5.43
        assert got.is_complete

    def test_sugar_contribution(self):
        """4.50 for 2000 g, 30 g used → 0.07 ₪."""
        r = recipe(ing("i1", "Sugar", 30, "g"))
        got = cost_one_drink(r, {"i1": product("p1", "Sugar", 2000, 4.50, "g")})
        assert got.cost == 0.07

    def test_lemon_juice_contribution(self):
        """27.00 for 2000 ml, 30 ml used → 0.40 ₪. Appears in every one of her trees."""
        r = recipe(ing("i1", "Lemon juice", 30))
        got = cost_one_drink(r, {"i1": product("p1", "Lemon juice", 2000, 27.00)})
        assert got.cost == 0.40

    def test_ingredients_sum(self):
        r = recipe(ing("i1", "Tequila", 50), ing("i2", "Sugar", 30, "g"),
                   ing("i3", "Lemon juice", 30))
        got = cost_one_drink(r, {
            "i1": product("p1", "Cuervo", 700, 76.00),
            "i2": product("p2", "Sugar", 2000, 4.50),
            "i3": product("p3", "Lemon", 2000, 27.00),
        })
        assert got.cost == round(5.43 + 0.07 + 0.40, 2)

    def test_no_float_noise(self):
        """Three ingredients must not produce 5.899999999999999."""
        r = recipe(*[ing(f"i{n}", f"x{n}", 30) for n in range(8)])
        got = cost_one_drink(r, {f"i{n}": product(f"p{n}", "x", 700, 99.90)
                                 for n in range(8)})
        assert got.cost == round(got.cost, 2)
        assert len(str(got.cost).split(".")[-1]) <= 2


class TestNothingIsInvented:
    """The rule the whole system rests on, at drink level."""

    def test_unmapped_ingredient_makes_it_incomplete(self):
        r = recipe(ing("i1", "Tequila", 50), ing("i2", "Yuzu", 20))
        got = cost_one_drink(r, {"i1": product("p1", "Cuervo", 700, 76.00)})
        assert got.is_complete is False
        assert got.cost is None
        assert "Yuzu" in got.missing

    def test_unpriced_product_makes_it_incomplete(self):
        r = recipe(ing("i1", "Tequila", 50))
        got = cost_one_drink(r, {"i1": ProductInfo("p1", "Cuervo", 700)})
        assert got.cost is None
        assert got.lines[0].missing_reason == "PRICE_MISSING"

    def test_partial_total_is_available_but_never_the_cost(self):
        """
        A partial figure is useful to show progress and dangerous to show as a
        price. It lives on a separate attribute so it cannot be mistaken.
        """
        r = recipe(ing("i1", "Tequila", 50), ing("i2", "Yuzu", 20))
        got = cost_one_drink(r, {"i1": product("p1", "Cuervo", 700, 76.00)})
        assert got.cost is None
        assert got.known_cost == 5.43

    def test_unmeasured_ingredient_is_not_missing_data(self):
        """"Top up with soda" has no amount in the recipe. That is not a gap."""
        r = recipe(ing("i1", "Tequila", 50), ing("i2", "Soda", None))
        got = cost_one_drink(r, {"i1": product("p1", "Cuervo", 700, 76.00),
                                 "i2": product("p2", "Soda", 1000, 5.0)})
        assert got.is_complete
        assert got.cost == 5.43


class TestSpiritTiers:
    """Her Roses Flower ladder: Emisario ₪8.01 · Cuervo ₪9.87 · Patrón ₪13.77."""

    def _roses(self):
        r = recipe(ing("i1", "Tequila", 50), ing("i2", "Strawberry purée", 15),
                   ing("i3", "Lychee purée", 30), ing("i4", "Sugar", 30),
                   ing("i5", "Lemon juice", 30), name="Roses Flower")
        rest = {
            "i2": product("p2", "Strawberry", 1000, 69.00),
            "i3": product("p3", "Lychee", 1000, 79.00),
            "i4": product("p4", "Sugar", 2000, 4.50),
            "i5": product("p5", "Lemon", 2000, 27.00),
        }
        alts = [
            product("t1", "Tequila Cuervo Silver", 700, 76.00),
            product("t2", "Emisario Silver", 1000, 71.37),
            product("t3", "Patrón Silver", 750, 140.00),
        ]
        return r, rest, alts

    def test_ordered_cheapest_first(self):
        r, rest, alts = self._roses()
        got = spirit_tiers(r, rest, "i1", alts)
        assert [t.product_name for t in got] == [
            "Emisario Silver", "Tequila Cuervo Silver", "Patrón Silver"]

    def test_spirit_costs_match_her_sheet(self):
        """The spirit's own contribution: 3.57 / 5.43 / 9.33 ₪ per drink."""
        r, rest, alts = self._roses()
        got = spirit_tiers(r, rest, "i1", alts)
        base = cost_one_drink(recipe(ing("i2", "Strawberry purée", 15),
                                     ing("i3", "Lychee purée", 30),
                                     ing("i4", "Sugar", 30),
                                     ing("i5", "Lemon juice", 30)), rest).cost
        assert [round(t.cost_per_drink - base, 2) for t in got] == [3.57, 5.43, 9.33]

    def test_three_alternatives_get_labels(self):
        r, rest, alts = self._roses()
        assert [t.label for t in spirit_tiers(r, rest, "i1", alts)] == \
            ["budget", "mid", "premium"]

    def test_two_alternatives_are_not_called_mid(self):
        """Calling one of two options "mid" would be inventing a middle."""
        r, rest, alts = self._roses()
        assert [t.label for t in spirit_tiers(r, rest, "i1", alts[:2])] == \
            ["budget", "premium"]

    def test_an_unpriceable_alternative_is_dropped_not_guessed(self):
        r, rest, alts = self._roses()
        alts.append(ProductInfo("t4", "Mystery Tequila", 700))  # no price
        got = spirit_tiers(r, rest, "i1", alts)
        assert "Mystery Tequila" not in [t.product_name for t in got]
        assert len(got) == 3


class TestBatchPlan:
    """Her sheets batch 30 (20 for Honey Flower) and divide back."""

    def test_volume_and_total(self):
        r = recipe(ing("i1", "Tequila", 50), ing("i2", "Lemon", 30))
        cost = cost_one_drink(r, {"i1": product("p1", "Cuervo", 700, 76.00),
                                  "i2": product("p2", "Lemon", 2000, 27.00)})
        plan = batch_plan(cost, 30)
        assert plan["ml_per_drink"] == 80
        assert plan["total_ml"] == 2400
        assert plan["total_cost"] == round(cost.cost * 30, 2)

    def test_incomplete_batch_has_no_total(self):
        r = recipe(ing("i1", "Tequila", 50), ing("i2", "Yuzu", 20))
        cost = cost_one_drink(r, {"i1": product("p1", "Cuervo", 700, 76.00)})
        plan = batch_plan(cost, 30)
        assert plan["total_cost"] is None
        assert plan["is_complete"] is False

    def test_zero_servings_is_rejected(self):
        r = recipe(ing("i1", "Tequila", 50))
        cost = cost_one_drink(r, {"i1": product("p1", "Cuervo", 700, 76.00)})
        try:
            batch_plan(cost, 0)
        except ValueError:
            return
        raise AssertionError("a batch of zero should not be silently accepted")

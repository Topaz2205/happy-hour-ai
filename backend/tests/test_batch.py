"""
Batch scaling.

The arithmetic is simple, which is exactly why it is worth pinning: this is the
sheet someone reads while physically making 200 drinks, and a wrong figure here
is wasted money and a ruined event rather than a bad pixel.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.engine.calculator import CocktailRecipe, RecipeIngredient, ProductInfo
from app.engine.batch import (
    scale_recipe, batch_to_dict, ADD_DURING_SERVICE, NOT_IN_MASTER_RECIPE,
)


def ing(iid, name, amount, unit="ml"):
    return RecipeIngredient(ingredient_id=iid, canonical_name=name,
                            amount=amount, unit=unit)


def recipe(*ingredients, name="Margarita"):
    return CocktailRecipe(cocktail_id="c1", name=name, alcoholic=True,
                          has_na_variant=False, na_variant_instructions=None,
                          ingredients=list(ingredients))


MARGARITA = recipe(
    ing("i1", "Olmeca Silver Tequila", 45),
    ing("i2", "Dry Curacao", 22.5),
    ing("i3", "Fresh Lime Juice", 30),
)


class TestScaling:
    def test_multiplies_each_line(self):
        got = scale_recipe(MARGARITA, 20)
        assert [l.total for l in got.lines] == [900, 450, 600]

    def test_a_batch_of_one_is_the_recipe(self):
        got = scale_recipe(MARGARITA, 1)
        assert [l.total for l in got.lines] == [45, 22.5, 30]

    def test_measured_volume_is_the_sum_of_ml_lines(self):
        got = scale_recipe(MARGARITA, 20)
        assert got.measured_volume_ml == 900 + 450 + 600

    def test_no_float_noise(self):
        """
        22.5 × 125 is 2812.4999999999995 in binary floating point.

        The first version of this test counted characters after the decimal
        point, which was a bad way to ask the question: round() on two ints
        returns an int, so 45 × 125 came back as `5625` with no decimal point
        at all and the check tripped over its own string handling. Comparing
        the values directly says what is actually meant.
        """
        got = scale_recipe(MARGARITA, 125)
        assert [l.total for l in got.lines] == [5625, 2812.5, 3750]
        for l in got.lines:
            assert l.total == round(l.total, 1)

    def test_zero_servings_is_refused(self):
        with pytest.raises(ValueError):
            scale_recipe(MARGARITA, 0)

    def test_negative_servings_is_refused(self):
        with pytest.raises(ValueError):
            scale_recipe(MARGARITA, -5)


class TestUnmeasuredIngredientsAreNeverGuessed:
    """The rule the whole system rests on, at batch level."""

    def test_a_missing_amount_stays_missing(self):
        r = recipe(ing("i1", "Rum", 60), ing("i2", "Soda Water", None))
        got = scale_recipe(r, 50)
        assert got.lines[1].total is None
        assert got.has_unmeasured is True

    def test_a_service_unit_says_add_during_service(self):
        r = recipe(ing("i1", "Angostura Bitters", None, "dashes"))
        assert scale_recipe(r, 30).lines[0].note == ADD_DURING_SERVICE

    def test_an_unexplained_gap_says_so_differently(self):
        """
        "2 dashes of bitters" and "somebody forgot to fill this in" are not the
        same problem, and the person reading the sheet is the one who can tell
        them apart — but only if the sheet distinguishes them.
        """
        r = recipe(ing("i1", "Mystery Syrup", None, "ml"))
        assert scale_recipe(r, 30).lines[0].note == NOT_IN_MASTER_RECIPE

    def test_unmeasured_lines_do_not_join_the_volume(self):
        r = recipe(ing("i1", "Rum", 60), ing("i2", "Soda", None))
        assert scale_recipe(r, 10).measured_volume_ml == 600

    def test_the_names_are_reported_so_they_can_be_shown(self):
        r = recipe(ing("i1", "Rum", 60), ing("i2", "Soda", None), ing("i3", "Mint", None))
        assert scale_recipe(r, 10).unmeasured_names == ["Soda", "Mint"]


class TestBottleCounts:
    def _products(self):
        return {
            "i1": ProductInfo("p1", "Olmeca Silver", 700, "ml", price_after_vat=90),
            "i2": ProductInfo("p2", "Dry Curacao", 700, "ml", price_after_vat=120),
            "i3": ProductInfo("p3", "Lime Juice", 1000, "ml", price_after_vat=27),
        }

    def test_rounds_up_because_bottles_are_whole(self):
        """900ml of a 700ml bottle is two bottles, not 1.29."""
        got = scale_recipe(MARGARITA, 20, self._products())
        assert got.lines[0].bottles_exact == 1.29
        assert got.lines[0].bottles_to_buy == 2

    def test_an_exact_fit_does_not_gain_a_spare(self):
        r = recipe(ing("i1", "Tequila", 70))
        got = scale_recipe(r, 10, {"i1": ProductInfo("p", "x", 700, "ml")})
        assert got.lines[0].bottles_to_buy == 1

    def test_no_product_means_no_bottle_count(self):
        got = scale_recipe(MARGARITA, 20)
        assert all(l.bottles_to_buy is None for l in got.lines)

    def test_a_product_without_a_size_is_not_given_a_default(self):
        """There is no such thing as a default bottle size."""
        got = scale_recipe(MARGARITA, 20, {"i1": ProductInfo("p1", "Olmeca", None)})
        assert got.lines[0].bottles_to_buy is None
        assert got.lines[0].total == 900   # the volume is still right

    def test_zero_size_does_not_divide_by_zero(self):
        got = scale_recipe(MARGARITA, 20, {"i1": ProductInfo("p1", "x", 0)})
        assert got.lines[0].bottles_to_buy is None


class TestSameRecipeAsEverythingElse:
    def test_scaling_is_linear(self):
        """
        Ten batches of 10 must equal one batch of 100. If they ever differ, the
        batch sheet and the shopping list are describing different events.
        """
        one = scale_recipe(MARGARITA, 100).lines
        ten = scale_recipe(MARGARITA, 10).lines
        assert [l.total for l in one] == [round(l.total * 10, 1) for l in ten]

    def test_dict_shape_carries_everything_the_ui_needs(self):
        d = batch_to_dict(scale_recipe(MARGARITA, 20))
        assert d["servings"] == 20 and len(d["lines"]) == 3
        assert set(d["lines"][0]) >= {"name", "unit", "per_serving", "total",
                                      "bottles_to_buy", "note"}

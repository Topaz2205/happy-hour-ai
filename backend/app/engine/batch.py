"""
Scale one recipe to any number of servings.

WHERE THE NUMBERS COME FROM
---------------------------
The canonical recipe, and nothing else. This does not hold a second copy of any
recipe, and it never asks a model for a quantity — batching is multiplication,
and multiplication belongs in Python.

WHAT IT REFUSES TO DO
---------------------
Guess. A recipe line with no amount — mint "to taste", soda "top up", a garnish
— stays without an amount here and is labelled for the person reading it. A
batch sheet that invents 200ml of something because a number looked missing is
worse than one that says "add during service": the first is wrong quietly, the
second is right out loud.

Bottle counts round UP, because nobody can buy 8.04 bottles, and the exact
figure is kept alongside so the spare is explainable rather than mysterious.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.engine.calculator import CocktailRecipe, ProductInfo

# A recipe line can be unmeasured for two different reasons, and the person
# holding the sheet needs to be able to tell them apart.
ADD_DURING_SERVICE = "Add during service"
NOT_IN_MASTER_RECIPE = "Quantity not defined in master recipe"

# Units where "top it up" is the normal instruction rather than missing data.
_SERVICE_UNITS = {"dash", "dashes", "splash", "top", "to taste", "garnish", "wedge", "twist"}


@dataclass
class BatchLine:
    ingredient_id: str
    name: str
    unit: str
    per_serving: Optional[float]
    total: Optional[float]
    # Bottles only where a real package size is known. Never derived from a
    # default bottle size, because there is no such thing as a default bottle.
    bottles_exact: Optional[float] = None
    bottles_to_buy: Optional[int] = None
    package_size: Optional[float] = None
    package_unit: Optional[str] = None
    product_name: Optional[str] = None
    note: Optional[str] = None


@dataclass
class BatchResult:
    cocktail_id: str
    name: str
    servings: int
    lines: list[BatchLine] = field(default_factory=list)
    # Total liquid volume, in ml, of the measured lines only. Stated as such,
    # because a batch containing an unmeasured top-up is genuinely larger than
    # this and pretending otherwise would size someone's container wrongly.
    measured_volume_ml: Optional[float] = None
    has_unmeasured: bool = False

    @property
    def unmeasured_names(self) -> list[str]:
        return [l.name for l in self.lines if l.total is None]


def scale_recipe(
    recipe: CocktailRecipe,
    servings: int,
    products: Optional[dict[str, ProductInfo]] = None,
) -> BatchResult:
    """
    One recipe, multiplied out to `servings`.

    `products` is optional: without it the batch still gives volumes, which is
    all a bartender needs. With it, volumes also become bottle counts, which is
    what the person doing the buying needs.
    """
    if servings <= 0:
        raise ValueError("servings must be a positive whole number")

    products = products or {}
    lines: list[BatchLine] = []
    volume = 0.0
    any_measured = False

    for ing in recipe.ingredients:
        product = products.get(ing.ingredient_id)
        line = BatchLine(
            ingredient_id=ing.ingredient_id,
            name=ing.canonical_name,
            unit=ing.unit,
            per_serving=ing.amount,
            total=None,
            product_name=product.product_name if product else None,
        )

        if ing.amount is None:
            line.note = (ADD_DURING_SERVICE
                         if (ing.unit or "").lower() in _SERVICE_UNITS
                         else NOT_IN_MASTER_RECIPE)
            lines.append(line)
            continue

        # Rounded to a tenth: batching produces figures like 2812.4999999999995,
        # and a prep sheet showing that has lost the reader's trust before they
        # have read the second row.
        line.total = round(ing.amount * servings, 1)
        any_measured = True
        if (ing.unit or "").lower() == "ml":
            volume += line.total

        size = product.package_size if product else None
        if size and size > 0:
            line.package_size = float(size)
            line.package_unit = product.package_unit if product else None
            line.bottles_exact = round(line.total / float(size), 2)
            line.bottles_to_buy = math.ceil(line.total / float(size))

        lines.append(line)

    return BatchResult(
        cocktail_id=recipe.cocktail_id,
        name=recipe.name,
        servings=servings,
        lines=lines,
        measured_volume_ml=round(volume, 1) if any_measured else None,
        has_unmeasured=any(l.total is None for l in lines),
    )


def batch_to_dict(result: BatchResult) -> dict:
    """Shape for the API. Kept next to the engine so the two cannot drift."""
    return {
        "cocktail_id": result.cocktail_id,
        "name": result.name,
        "servings": result.servings,
        "measured_volume_ml": result.measured_volume_ml,
        "has_unmeasured": result.has_unmeasured,
        "unmeasured": result.unmeasured_names,
        "lines": [
            {
                "ingredient_id": l.ingredient_id,
                "name": l.name,
                "unit": l.unit,
                "per_serving": l.per_serving,
                "total": l.total,
                "bottles_exact": l.bottles_exact,
                "bottles_to_buy": l.bottles_to_buy,
                "package_size": l.package_size,
                "package_unit": l.package_unit,
                "product_name": l.product_name,
                "note": l.note,
            }
            for l in result.lines
        ],
    }

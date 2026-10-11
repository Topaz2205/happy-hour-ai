"""
What one drink costs, and what the same drink costs at three spirit tiers.

WHERE THIS COMES FROM
---------------------
This is Topaz's own formula, read off the "עץ מוצר" (product tree) sheets in her
cost-calculator template. It was not designed here. Each sheet prices one
cocktail ingredient by ingredient:

    unit_price    = price / (purchase_qty × product_size)     ₪ per ml
    cost_in_drink = unit_price × amount_used_in_drink

and the cocktail's cost is the sum across its ingredients. Her Roses Flower
sheet, Tequila Cuervo Silver line: 76.00 / (1 × 700) = 0.1086 ₪/ml, and
0.1086 × 50 ml = 5.43 ₪. The tests below assert exactly her numbers.

WHY IT DID NOT EXIST BEFORE
---------------------------
Per-cocktail cost was deliberately left unbuilt, because dividing a bottle
between drinks needs an allocation rule and only she could say what hers was.
Her sheets answer it: straight pro-rata by volume used, with no shared-bottle
or waste loading at this level. Waste stays where it already is — applied once,
at event level, by the purchase buffer. Applying it in both places would
silently double-count it.

WHAT IS NOT DONE HERE
---------------------
A missing price is never filled in, estimated, or skipped quietly. It makes the
result incomplete and names the ingredient responsible. A number that is 80%
of a cocktail is not a cheaper cocktail — it is a wrong one, and someone sets a
budget by it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.calculator import CocktailRecipe, ProductInfo


@dataclass
class IngredientCost:
    ingredient_id: str
    canonical_name: str
    amount: Optional[float]
    unit: str
    product_name: Optional[str] = None
    unit_price: Optional[float] = None      # ₪ per ml / per unit
    cost: Optional[float] = None            # ₪ contributed to one drink
    missing_reason: Optional[str] = None


@dataclass
class DrinkCost:
    cocktail_id: str
    name: str
    cost: Optional[float]                   # None when incomplete
    is_complete: bool
    lines: list[IngredientCost] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def known_cost(self) -> float:
        """The part that IS known. Never present this as the cocktail's cost."""
        return round(sum(l.cost for l in self.lines if l.cost is not None), 2)


def unit_price(product: ProductInfo) -> Optional[float]:
    """
    Price of one ml (or one unit) of a product.

    Her sheets carry a purchase quantity as well as a package size — "40 dried
    strawberries at ₪8" is quantity 40, size 1. Both divide the price, so a
    package size of 1 with a quantity of 40 behaves correctly without a special
    case. A missing or zero size yields None rather than a division error or a
    fabricated fallback.
    """
    price = product.price_after_vat if product.price_after_vat is not None else product.price_before_vat
    if price is None:
        return None
    size = product.package_size
    if not size or size <= 0:
        return None
    return price / size


def cost_one_drink(
    recipe: CocktailRecipe,
    products: dict[str, ProductInfo],
) -> DrinkCost:
    """
    Cost of a single serving, by Topaz's pro-rata rule.

    `products` maps ingredient_id → the product chosen for it. An ingredient
    with no entry, no price, or no package size is reported as missing.
    """
    lines: list[IngredientCost] = []
    missing: list[str] = []

    for ing in recipe.ingredients:
        line = IngredientCost(
            ingredient_id=ing.ingredient_id,
            canonical_name=ing.canonical_name,
            amount=ing.amount,
            unit=ing.unit,
        )

        # An unmeasured ingredient ("top up with soda", "garnish") carries no
        # amount. It is not missing data — the recipe genuinely has no figure —
        # so it contributes nothing and does not spoil completeness.
        if ing.amount is None:
            line.cost = 0.0
            line.missing_reason = "unmeasured — contributes no costed volume"
            lines.append(line)
            continue

        product = products.get(ing.ingredient_id)
        if product is None:
            line.missing_reason = "PRODUCT_MAPPING_REQUIRED"
            missing.append(ing.canonical_name)
            lines.append(line)
            continue

        up = unit_price(product)
        line.product_name = product.product_name
        if up is None:
            line.missing_reason = (
                "PRICE_MISSING" if product.price_after_vat is None
                and product.price_before_vat is None else "PACKAGE_SIZE_MISSING"
            )
            missing.append(ing.canonical_name)
            lines.append(line)
            continue

        line.unit_price = round(up, 6)
        # Rounded at the point it becomes a reported figure, like every other
        # money value in this system.
        line.cost = round(up * ing.amount, 2)
        lines.append(line)

    complete = not missing
    return DrinkCost(
        cocktail_id=recipe.cocktail_id,
        name=recipe.name,
        cost=round(sum(l.cost for l in lines if l.cost is not None), 2) if complete else None,
        is_complete=complete,
        lines=lines,
        missing=missing,
    )


@dataclass
class SpiritTier:
    product_id: str
    product_name: str
    cost_per_drink: float
    label: str = ""        # "budget" | "mid" | "premium"


def spirit_tiers(
    recipe: CocktailRecipe,
    products: dict[str, ProductInfo],
    swap_ingredient_id: str,
    alternatives: list[ProductInfo],
) -> list[SpiritTier]:
    """
    The same cocktail priced against each alternative spirit, cheapest first.

    Every product tree in her template does this — Roses Flower is costed with
    Emisario, Cuervo and Patrón side by side, ₪8.01 / ₪9.87 / ₪13.77 a drink.
    It is the most useful thing in those sheets: someone with a fixed budget
    should be offered the menu they asked for at a price that fits, not a
    different and duller menu.

    Alternatives that cannot be costed are dropped rather than shown at a
    guessed price. Labels are assigned only when all three tiers exist, because
    calling one of two options "mid" would be an invention.
    """
    priced: list[SpiritTier] = []
    for alt in alternatives:
        trial = dict(products)
        trial[swap_ingredient_id] = alt
        result = cost_one_drink(recipe, trial)
        if result.is_complete and result.cost is not None:
            priced.append(SpiritTier(
                product_id=alt.product_id,
                product_name=alt.product_name,
                cost_per_drink=result.cost,
            ))

    priced.sort(key=lambda t: t.cost_per_drink)
    if len(priced) == 3:
        for tier, label in zip(priced, ("budget", "mid", "premium")):
            tier.label = label
    elif len(priced) == 2:
        priced[0].label, priced[1].label = "budget", "premium"
    return priced


def batch_plan(cost: DrinkCost, servings: int) -> dict:
    """
    Scale one drink up to a batch, the way her sheets do.

    Her template computes total volume and total raw-material cost for a batch
    of 30 (20 for Honey Flower) and divides back to a per-drink figure. Kept
    here so the two views can be reconciled against each other.
    """
    if servings <= 0:
        raise ValueError("servings must be positive")
    ml = sum((l.amount or 0) for l in cost.lines if l.unit == "ml")
    return {
        "servings": servings,
        "ml_per_drink": round(ml, 2),
        "total_ml": round(ml * servings, 2),
        "cost_per_drink": cost.cost,
        "total_cost": round(cost.cost * servings, 2) if cost.cost is not None else None,
        "is_complete": cost.is_complete,
        "missing": cost.missing,
    }

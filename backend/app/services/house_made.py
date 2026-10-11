"""
House-made ingredients: things you produce rather than buy.

Simple syrup has no supplier price because nobody sells it to you — you make it
from sugar and water. Until it carries a cost, every cocktail using it is
under-costed, and simple syrup alone appears in 9 of the 34 classics.

The cost is computed from the real price of the inputs already in the database,
so it stays correct when sugar prices change: re-run the script and it updates.
Nothing here is a guessed price.

YIELD is the one number that isn't measured from your data. Dissolving sugar
into water produces less volume than the two added together, because the sugar
occupies space between water molecules. The figures below are the standard
bartending yields; if you measure your own, change them here and re-run.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InputLine:
    """One input to a house recipe. `free` inputs cost nothing (tap water)."""
    ingredient_name: str
    amount_ml: float
    free: bool = False


@dataclass(frozen=True)
class HouseRecipe:
    ingredient_name: str          # the ingredient this produces
    yield_ml: float               # how much finished product one batch makes
    inputs: list[InputLine]
    method: str
    yield_note: str

    def cost_per_ml(self, price_per_ml: dict[str, float]) -> tuple[float | None, list[str]]:
        """
        Cost of one ml of the finished product.

        Returns (cost, problems). Cost is None when an input has no price —
        never zero, and never a guess.
        """
        problems: list[str] = []
        total = 0.0
        for line in self.inputs:
            if line.free:
                continue
            unit = price_per_ml.get(line.ingredient_name)
            if unit is None:
                problems.append(
                    f"{self.ingredient_name}: input '{line.ingredient_name}' has no "
                    f"price on file, so the batch cost cannot be worked out."
                )
                continue
            total += unit * line.amount_ml

        if problems or self.yield_ml <= 0:
            return None, problems
        return total / self.yield_ml, problems


# ── The recipes ───────────────────────────────────────────────────────────────
# Simple syrup as given by the bar: equal volumes of white sugar and water,
# warmed until the sugar dissolves.
HOUSE_RECIPES: list[HouseRecipe] = [
    HouseRecipe(
        ingredient_name="Simple Syrup (1:1)",
        yield_ml=1500.0,
        inputs=[
            InputLine("Sugar", 1000.0),
            InputLine("Water", 1000.0, free=True),
        ],
        method=(
            "Equal volumes white sugar and water. Heat the water (kettle or pan), "
            "stir the sugar in until fully dissolved, cool before bottling."
        ),
        yield_note=(
            "1000ml sugar + 1000ml water yields about 1500ml of syrup, not 2000ml — "
            "the sugar dissolves into the water rather than adding to it."
        ),
    ),
    HouseRecipe(
        ingredient_name="Rich Syrup (2:1)",
        yield_ml=2000.0,
        inputs=[
            InputLine("Sugar", 2000.0),
            InputLine("Water", 1000.0, free=True),
        ],
        method=(
            "Two parts sugar to one part water by volume. Heat the water, stir the "
            "sugar in until dissolved, cool before bottling."
        ),
        yield_note="2000ml sugar + 1000ml water yields roughly 2000ml of syrup.",
    ),
]

HOUSE_SUPPLIER_NAME = "House-made"

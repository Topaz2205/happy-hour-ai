"""
An event without a budget is a normal event.

This exists because it was not treated as one. `GET /api/events/{id}` cast the
budget with a bare float(), so opening an event that had never been given a
budget returned a 500 — and since that endpoint is what the whole workspace
loads from, every tab went dark at once. The agent had the same bug twice over,
so asking it anything about such an event took the panel down too.

The rule: a budget is nullable, an event without one is still fully costable,
and it simply receives no over/under verdict. These tests hold every place that
reads a budget to that rule.
"""
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

BACKEND = Path(__file__).parent.parent
SOURCES = [
    BACKEND / "app" / "api" / "events.py",
    BACKEND / "app" / "api" / "agent.py",
    BACKEND / "app" / "api" / "plan.py",
]


def _casts(text: str) -> list[str]:
    """
    Every budget-to-float conversion, with the expression it sits in.

    Reading one line at a time was not good enough: a conditional split across
    two lines looked unguarded to the scan and produced a false alarm on code
    that was correct. Each cast is returned with the following two lines
    attached so a guard on the next line is visible.
    """
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if re.search(r"float\(\s*\w+\.budget\s*\)", line):
            out.append(" ".join(l.strip() for l in lines[i:i + 3]))
    return out


class TestEveryBudgetCastIsGuarded:
    def test_no_bare_float_of_a_budget_anywhere(self):
        """
        A bare float(event.budget) is a 500 waiting for the first event somebody
        plans without a budget — which is most of them, since the budget is
        usually decided after seeing what things cost.
        """
        offenders = []
        for path in SOURCES:
            text = path.read_text(encoding="utf-8")
            for line in _casts(text):
                # Guarded either on the same line, or by an enclosing check that
                # this crude scan cannot see; the ones we care about are the
                # inline conversions in response builders.
                if "is not None" not in line and "if" not in line:
                    offenders.append(f"{path.name}: {line}")
        assert not offenders, "unguarded budget cast(s):\n  " + "\n  ".join(offenders)

    def test_guards_use_is_not_none_not_truthiness(self):
        """
        `if event.budget else None` treats a budget of ₪0 as no budget at all.
        Zero is a strange thing to set, but it is a statement — "no budget" is
        the absence of one. Only `is not None` tells them apart, and conflating
        them would silently drop an over-budget verdict for anyone who typed 0.
        """
        offenders = []
        for path in SOURCES:
            for line in _casts(path.read_text(encoding="utf-8")):
                if re.search(r"if\s+\w+\.budget\s+else", line):
                    offenders.append(f"{path.name}: {line}")
        assert not offenders, "truthiness guard(s) that mishandle 0:\n  " + "\n  ".join(offenders)


class TestBudgetlessEventsStillCost:
    """The behaviour the nullability is for."""

    def test_the_engine_costs_without_a_budget(self):
        from app.engine.calculator import calculate_event, MenuAllocation

        # No menu, no products — enough to prove budget=None is accepted and
        # produces a total rather than an exception or a verdict.
        result = calculate_event(
            guests=50, drinks_per_guest=2.5, non_alcoholic_pct=0.25,
            waste_buffer_pct=0.08, menu=[], recipes={}, ingredient_products={},
            budget=None,
        )
        assert result.total_drinks > 0
        assert result.budget_variance is None
        assert result.budget_status in (None, "NO_BUDGET")

    def test_a_zero_budget_is_not_the_same_as_none(self):
        """
        Zero is a verdict; None is the absence of one.

        The first version of this test used an empty menu, which produces no
        cost at all — so both cases came back None and the test proved nothing
        either way. Distinguishing them needs an event that actually costs
        something, so this one buys a real bottle.
        """
        from app.engine.calculator import (
            calculate_event, MenuAllocation, CocktailRecipe, RecipeIngredient,
            IngredientWithProduct, ProductInfo,
        )

        recipe = CocktailRecipe(
            cocktail_id="c1", name="Test", alcoholic=True,
            has_na_variant=False, na_variant_instructions=None,
            ingredients=[RecipeIngredient(
                ingredient_id="i1", canonical_name="Gin", amount=50, unit="ml")],
        )
        products = {"i1": IngredientWithProduct(
            ingredient_id="i1", canonical_name="Gin", category="spirit", unit="ml",
            product=ProductInfo("p1", "A gin", 700, "ml",
                                price_before_vat=80, price_after_vat=94.4),
        )}

        def run(budget):
            return calculate_event(
                guests=50, drinks_per_guest=2.5, non_alcoholic_pct=0.25,
                waste_buffer_pct=0.08,
                menu=[MenuAllocation(cocktail_id="c1", allocation_pct=1.0)],
                recipes={"c1": recipe}, ingredient_products=products,
                budget=budget,
            )

        costed = run(None)
        assert costed.total_cost and costed.total_cost > 0, "the event must actually cost something"

        zero = run(0.0)
        # Zero produces a real verdict: everything is over a budget of nothing.
        assert zero.budget_variance is not None
        assert zero.budget_status is not None
        # None produces no verdict at all, while still costing the event.
        assert costed.budget_variance is None
        assert costed.budget_status != zero.budget_status

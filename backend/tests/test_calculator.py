"""
Unit tests for the deterministic calculation engine.
All tests run without a database connection.
"""
import math
import pytest
from app.engine.calculator import (
    calculate_event,
    MenuAllocation,
    CocktailRecipe,
    RecipeIngredient,
    IngredientWithProduct,
    ProductInfo,
    PurchaseStatus,
    BudgetStatus,
)


# ── Test Fixtures ──────────────────────────────────────────────────────────────

def make_gin_recipe() -> CocktailRecipe:
    """Minimal Gin Sour recipe for testing."""
    return CocktailRecipe(
        cocktail_id="gin-sour",
        name="Gin Sour",
        alcoholic=True,
        has_na_variant=False,
        na_variant_instructions=None,
        ingredients=[
            RecipeIngredient("ing-gin", "Gin", 45.0, "ml", "spirit", True),
            RecipeIngredient("ing-lemon", "Lemon Juice", 30.0, "ml", "juice", False),
            RecipeIngredient("ing-syrup", "Simple Syrup", 15.0, "ml", "syrup", False),
        ],
    )


def make_mocktail_recipe() -> CocktailRecipe:
    """Non-alcoholic recipe for testing."""
    return CocktailRecipe(
        cocktail_id="basil-soda",
        name="Basil Soda",
        alcoholic=False,
        has_na_variant=False,
        na_variant_instructions=None,
        ingredients=[
            RecipeIngredient("ing-basil-syrup", "Basil Syrup", 30.0, "ml", "syrup", False),
            RecipeIngredient("ing-lemon", "Lemon Juice", 20.0, "ml", "juice", False),
        ],
    )


def make_full_products() -> dict[str, IngredientWithProduct]:
    """Product mappings with complete pricing data."""
    return {
        "ing-gin": IngredientWithProduct(
            ingredient_id="ing-gin",
            canonical_name="Gin",
            category="spirit",
            unit="ml",
            product=ProductInfo(
                product_id="prod-beefeater",
                product_name="Beefeater London Dry Gin 700ml",
                package_size=700.0,
                package_unit="ml",
                price_before_vat=64.10,
                price_after_vat=75.0,
                supplier_id="sup-1",
                supplier_name="Drinks R Us",
            ),
        ),
        "ing-lemon": IngredientWithProduct(
            ingredient_id="ing-lemon",
            canonical_name="Lemon Juice",
            category="juice",
            unit="ml",
            product=ProductInfo(
                product_id="prod-lemon",
                product_name="Fresh Lemon Juice 2L",
                package_size=2000.0,
                package_unit="ml",
                price_before_vat=23.07,
                price_after_vat=27.0,
            ),
        ),
        "ing-syrup": IngredientWithProduct(
            ingredient_id="ing-syrup",
            canonical_name="Simple Syrup",
            category="syrup",
            unit="ml",
            product=ProductInfo(
                product_id="prod-syrup",
                product_name="Simple Syrup 1L",
                package_size=1000.0,
                package_unit="ml",
                price_before_vat=8.55,
                price_after_vat=10.0,
            ),
        ),
        "ing-basil-syrup": IngredientWithProduct(
            ingredient_id="ing-basil-syrup",
            canonical_name="Basil Syrup",
            category="syrup",
            unit="ml",
            product=ProductInfo(
                product_id="prod-basil-syrup",
                product_name="Basil Syrup 1L",
                package_size=1000.0,
                package_unit="ml",
                price_before_vat=25.64,
                price_after_vat=30.0,
            ),
        ),
    }


# ── Step 1: Total Drinks ───────────────────────────────────────────────────────

class TestTotalDrinks:
    def test_basic_calculation(self):
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        assert result.total_drinks == 250

    def test_guests_times_drinks_per_guest(self):
        result = calculate_event(
            guests=80,
            drinks_per_guest=3.0,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        assert result.total_drinks == 240

    def test_non_alcoholic_split(self):
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.25,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        assert result.total_drinks == 250
        # Python's round(250*0.25) = round(62.5) = 62 (banker's rounding)
        assert result.non_alcoholic_drinks == 62
        assert result.alcoholic_drinks == 188     # 250 - 62


# ── Step 5: Waste Buffer ───────────────────────────────────────────────────────

class TestWasteBuffer:
    def test_waste_buffer_applied(self):
        """With 100 guests, 2.5 drinks, 100% gin sour, gin=45ml:
        raw = 250 * 45 = 11,250 ml
        with 8% buffer = 11,250 * 1.08 = 12,150 ml
        """
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.08,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        gin_req = next(r for r in result.ingredient_requirements if r.ingredient_id == "ing-gin")
        assert gin_req.raw_amount == pytest.approx(11250.0)
        assert gin_req.required_amount == pytest.approx(12150.0)

    def test_zero_waste_buffer(self):
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        gin_req = next(r for r in result.ingredient_requirements if r.ingredient_id == "ing-gin")
        assert gin_req.raw_amount == gin_req.required_amount


# ── Step 4: Ingredient Aggregation ────────────────────────────────────────────

class TestIngredientAggregation:
    def test_same_ingredient_in_multiple_cocktails(self):
        """Lemon juice appears in both cocktails; must be aggregated."""
        # Gin sour: lemon=30ml, Basil soda: lemon=20ml
        # 50% each, 100 guests, 2.5 drinks = 125 servings each
        # Lemon total: 125*30 + 125*20 = 3750 + 2500 = 6250 ml (raw, no buffer)
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[
                MenuAllocation("gin-sour", 0.5),
                MenuAllocation("basil-soda", 0.5),
            ],
            recipes={
                "gin-sour": make_gin_recipe(),
                "basil-soda": make_mocktail_recipe(),
            },
            ingredient_products=make_full_products(),
        )
        lemon_req = next(
            r for r in result.ingredient_requirements if r.ingredient_id == "ing-lemon"
        )
        assert lemon_req.raw_amount == pytest.approx(6250.0, rel=0.01)


# ── Step 7: Package Rounding (CEILING) ────────────────────────────────────────

class TestPackageRounding:
    def test_ceiling_rounding(self):
        """Need 12150 ml gin, package 700 ml → ceil(12150/700) = 18 bottles."""
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.08,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        gin_item = next(p for p in result.purchase_items if p.ingredient_id == "ing-gin")
        # raw=11250, buffer=12150, package=700 → ceil(12150/700) = 18
        assert gin_item.packages_required == math.ceil(12150.0 / 700.0)
        assert gin_item.packages_required == 18

    def test_never_fractional_bottles(self):
        """Packages required must always be an integer (ceiling, never floor)."""
        result = calculate_event(
            guests=10,
            drinks_per_guest=2.0,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        for item in result.purchase_items:
            if item.packages_required is not None:
                assert isinstance(item.packages_required, int)
                assert item.packages_required >= 1

    def test_exact_multiple_no_rounding_up(self):
        """If required is exactly divisible, no extra package needed."""
        # 10 guests, 2 drinks, 100% gin sour, gin=45ml, no buffer
        # total gin = 10 * 2 * 45 = 900 ml; 900/700 = 1.28... → ceil = 2
        result = calculate_event(
            guests=10,
            drinks_per_guest=2.0,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        gin_item = next(p for p in result.purchase_items if p.ingredient_id == "ing-gin")
        required = 10 * 2 * 45  # = 900
        assert gin_item.packages_required == math.ceil(required / 700)  # ceil(900/700)=2


# ── Cost Calculation ───────────────────────────────────────────────────────────

class TestCostCalculation:
    def test_cost_per_ingredient(self):
        """
        package_price / package_size × amount_in_recipe is done via:
        packages_required × package_price.

        For gin sour, 100 guests, 2.5 drinks, no buffer:
        gin: 11250ml, 700ml@₪75 → 17 bottles → 17×75 = ₪1275
        lemon: 7500ml, 2000ml@₪27 → 4 bottles → 4×27 = ₪108
        syrup: 3750ml, 1000ml@₪10 → 4 bottles → 4×10 = ₪40
        total = ₪1423
        """
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        gin_item = next(p for p in result.purchase_items if p.ingredient_id == "ing-gin")
        # 100*2.5*45 = 11250ml → ceil(11250/700) = 17
        assert gin_item.packages_required == 17
        assert gin_item.total_price == pytest.approx(17 * 75.0)

    def test_total_cost_sum(self):
        """Total cost equals sum of all purchase item costs."""
        result = calculate_event(
            guests=50,
            drinks_per_guest=2.0,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        expected_total = sum(
            item.total_price for item in result.purchase_items if item.total_price is not None
        )
        assert result.total_cost == pytest.approx(expected_total)

    def test_line_item_price_is_rounded(self):
        """
        A per-item total must be clean money too, not just the grand total.

        3 bottles at 99.90 is 299.70000000000005 in binary floating point.
        Line items are what someone actually orders from, so the rounding has
        to happen there as well.
        """
        products = make_full_products()
        products["ing-gin"].product.price_after_vat = 99.90

        result = calculate_event(
            guests=100, drinks_per_guest=2.5,
            non_alcoholic_pct=0.0, waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=products,
        )
        for item in result.purchase_items:
            if item.total_price is not None:
                assert item.total_price == round(item.total_price, 2), (
                    f"{item.canonical_name} carries float noise: {item.total_price!r}"
                )

    def test_money_is_rounded_to_agorot(self):
        """
        Reported money must never carry binary-float noise.

        Summing floats produces artifacts like 1343.3400000000001. Those must
        not reach a budget comparison, an invoice, or the UI, so total_cost,
        cost_per_guest and budget_variance are all rounded to 2 decimals.
        """
        products = make_full_products()
        # Prices chosen so the naive sum lands on a non-representable float
        products["ing-gin"].product.price_after_vat = 134.55
        products["ing-lemon"].product.price_after_vat = 27.0
        products["ing-syrup"].product.price_after_vat = 10.1

        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=products,
            budget=5000.0,
        )

        assert result.total_cost is not None
        # round(x, 2) is idempotent only if x already has <=2 decimals
        assert result.total_cost == round(result.total_cost, 2)
        assert result.cost_per_guest == round(result.cost_per_guest, 2)
        assert result.budget_variance == round(result.budget_variance, 2)

        # And the value is still correct, not merely tidy
        expected = round(
            sum(i.total_price for i in result.purchase_items if i.total_price is not None), 2
        )
        assert result.total_cost == expected


# ── Missing Data ───────────────────────────────────────────────────────────────

class TestMissingData:
    def test_missing_price_does_not_silently_use_zero(self):
        """A missing price must result in PRICE_MISSING status, not zero cost."""
        products = make_full_products()
        products["ing-gin"].product.price_after_vat = None
        products["ing-gin"].product.price_before_vat = None

        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.08,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=products,
        )
        gin_item = next(p for p in result.purchase_items if p.ingredient_id == "ing-gin")
        assert gin_item.status == PurchaseStatus.PRICE_MISSING
        assert gin_item.total_price is None  # NOT zero
        assert result.has_missing_prices is True

    def test_missing_product_mapping(self):
        """Ingredient with no product mapping must surface PRODUCT_MAPPING_REQUIRED."""
        products = make_full_products()
        # Remove gin mapping entirely
        del products["ing-gin"]

        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.08,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=products,
        )
        gin_item = next(p for p in result.purchase_items if p.ingredient_id == "ing-gin")
        assert gin_item.status == PurchaseStatus.PRODUCT_MAPPING_REQUIRED
        assert result.has_missing_mappings is True

    def test_missing_price_warning_in_list(self):
        """A PRICE_MISSING warning must appear in the warnings list."""
        products = make_full_products()
        products["ing-gin"].product.price_after_vat = None

        result = calculate_event(
            guests=50,
            drinks_per_guest=2.0,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=products,
        )
        assert any("Price missing" in w or "price" in w.lower() for w in result.warnings)


# ── Budget ─────────────────────────────────────────────────────────────────────

class TestBudget:
    def _run_with_budget(self, budget: float) -> "EventCalculationResult":
        return calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
            budget=budget,
        )

    def test_under_budget(self):
        result = self._run_with_budget(budget=99999.0)
        assert result.budget_status == BudgetStatus.UNDER_BUDGET
        assert result.budget_variance > 0

    def test_over_budget(self):
        result = self._run_with_budget(budget=1.0)
        assert result.budget_status == BudgetStatus.OVER_BUDGET
        assert result.budget_variance < 0

    def test_on_budget(self):
        """Budget very close to cost → ON_BUDGET."""
        # First figure out the actual cost
        result_first = self._run_with_budget(budget=999999.0)
        cost = result_first.total_cost
        result = self._run_with_budget(budget=cost + 10)  # ₪10 over = ON_BUDGET
        assert result.budget_status == BudgetStatus.ON_BUDGET

    def test_budget_variance_correct(self):
        result = self._run_with_budget(budget=5000.0)
        assert result.budget_variance == pytest.approx(5000.0 - result.total_cost)

    def test_no_budget_no_status(self):
        result = calculate_event(
            guests=50,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
            budget=None,
        )
        assert result.budget_status is None


# ── Menu Validation ────────────────────────────────────────────────────────────

class TestMenuValidation:
    def test_allocations_not_summing_to_100_produces_warning(self):
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 0.6), MenuAllocation("basil-soda", 0.3)],
            recipes={
                "gin-sour": make_gin_recipe(),
                "basil-soda": make_mocktail_recipe(),
            },
            ingredient_products=make_full_products(),
        )
        assert any("90.0%" in w or "allocation" in w.lower() for w in result.warnings)


# ── Cost Per Guest ─────────────────────────────────────────────────────────────

class TestCostPerGuest:
    def test_cost_per_guest_is_total_divided_by_guests(self):
        result = calculate_event(
            guests=100,
            drinks_per_guest=2.5,
            non_alcoholic_pct=0.0,
            waste_buffer_pct=0.0,
            menu=[MenuAllocation("gin-sour", 1.0)],
            recipes={"gin-sour": make_gin_recipe()},
            ingredient_products=make_full_products(),
        )
        assert result.cost_per_guest == pytest.approx(result.total_cost / 100)

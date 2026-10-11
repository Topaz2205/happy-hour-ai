"""
Happy Hour AI — Deterministic Calculation Engine
=================================================
All quantity and cost calculations happen here.
The Claude AI agent calls tools that invoke this module.
The LLM NEVER performs calculations itself.

Architecture rule: This module has NO async I/O.
It receives pre-fetched data dictionaries and returns pure results.
"""
import math
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PurchaseStatus(str, Enum):
    OK = "OK"
    PRICE_MISSING = "PRICE_MISSING"
    PRODUCT_MAPPING_REQUIRED = "PRODUCT_MAPPING_REQUIRED"
    SUPPLIER_NOT_MAPPED = "SUPPLIER_NOT_MAPPED"
    PACKAGE_SIZE_MISSING = "PACKAGE_SIZE_MISSING"


class BudgetStatus(str, Enum):
    UNDER_BUDGET = "UNDER_BUDGET"
    ON_BUDGET = "ON_BUDGET"
    OVER_BUDGET = "OVER_BUDGET"


@dataclass
class RecipeIngredient:
    """An ingredient line in a cocktail recipe."""
    ingredient_id: str
    canonical_name: str
    amount: Optional[float]  # None = unmeasured (e.g. "top up with soda")
    unit: str = "ml"
    category: str = "other"
    alcoholic: bool = False


@dataclass
class CocktailRecipe:
    """A cocktail recipe with all ingredients."""
    cocktail_id: str
    name: str
    alcoholic: bool
    has_na_variant: bool
    na_variant_instructions: Optional[str]
    ingredients: list[RecipeIngredient]


@dataclass
class MenuAllocation:
    """A cocktail in the event menu with its share."""
    cocktail_id: str
    allocation_pct: float  # 0.0–1.0; sum of all must ~= 1.0


@dataclass
class ProductInfo:
    """A purchasable product for an ingredient."""
    product_id: str
    product_name: str
    package_size: Optional[float]  # ml or units
    package_unit: str = "ml"
    price_before_vat: Optional[float] = None
    price_after_vat: Optional[float] = None
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    product_url: Optional[str] = None


@dataclass
class IngredientWithProduct:
    """An ingredient mapped to its preferred purchasable product."""
    ingredient_id: str
    canonical_name: str
    category: str
    unit: str
    product: Optional[ProductInfo] = None


@dataclass
class IngredientRequirement:
    """How much of an ingredient is needed (after aggregation + waste buffer)."""
    ingredient_id: str
    canonical_name: str
    category: str
    unit: str
    raw_amount: float    # before waste buffer
    required_amount: float  # after waste buffer (= raw × (1 + buffer))


@dataclass
class PurchaseItem:
    """A purchase line item: ingredient → product → packages."""
    ingredient_id: str
    canonical_name: str
    category: str
    product_id: Optional[str]
    product_name: Optional[str]
    required_amount: float
    unit: str
    package_size: Optional[float]
    package_unit: Optional[str]
    packages_required: Optional[int]  # CEILING; None if size unknown
    unit_price: Optional[float]       # None if PRICE_MISSING
    total_price: Optional[float]      # None if PRICE_MISSING
    status: PurchaseStatus
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    product_url: Optional[str] = None


@dataclass
class EventCalculationResult:
    """Full result of running the calculation engine."""
    # Inputs (echoed back for traceability)
    guests: int
    drinks_per_guest: float
    non_alcoholic_pct: float
    waste_buffer_pct: float

    # Step 1–2 outputs
    total_drinks: int
    alcoholic_drinks: int
    non_alcoholic_drinks: int

    # Per cocktail breakdown
    cocktail_servings: dict[str, int]  # cocktail_id → servings

    # Step 3–5 outputs
    ingredient_requirements: list[IngredientRequirement]

    # Step 6–9 outputs
    purchase_items: list[PurchaseItem]

    # Step 10 outputs
    total_cost: Optional[float]         # None if any PRICE_MISSING
    cost_per_guest: Optional[float]     # None if total_cost is None
    budget: Optional[float]
    budget_variance: Optional[float]    # budget - total_cost; None if total_cost is None
    budget_status: Optional[BudgetStatus]

    # Data quality
    warnings: list[str]
    has_missing_prices: bool
    has_missing_mappings: bool

    # Category cost breakdown
    cost_by_category: dict[str, Optional[float]]


def validate_menu(menu: list[MenuAllocation]) -> list[str]:
    """Validate that menu allocations sum to ~100%."""
    warnings = []
    total = sum(a.allocation_pct for a in menu)
    if abs(total - 1.0) > 0.01:
        warnings.append(
            f"Menu allocations sum to {total:.1%}, not 100%. "
            f"Expected 1.0, got {total:.4f}."
        )
    return warnings


def calculate_event(
    guests: int,
    drinks_per_guest: float,
    non_alcoholic_pct: float,
    waste_buffer_pct: float,
    menu: list[MenuAllocation],
    recipes: dict[str, CocktailRecipe],      # cocktail_id → CocktailRecipe
    ingredient_products: dict[str, IngredientWithProduct],  # ingredient_id → product
    budget: Optional[float] = None,
) -> EventCalculationResult:
    """
    Main entry point for the calculation engine.

    Parameters
    ----------
    guests: Number of event attendees
    drinks_per_guest: Expected drinks per person (default 2.5)
    non_alcoholic_pct: Fraction of guests wanting non-alcoholic (0.0–1.0)
    waste_buffer_pct: Safety buffer for spillage/overage (default 0.08)
    menu: List of cocktails with their percentage of total drinks
    recipes: Pre-fetched recipe data from DB (ingredient_id → CocktailRecipe)
    ingredient_products: Pre-fetched product mapping from DB
    budget: Optional budget for comparison

    Returns
    -------
    EventCalculationResult with all quantities, costs, and warnings
    """
    warnings = list(validate_menu(menu))

    # ── STEP 1: Total drinks ─────────────────────────────────────────────────
    total_drinks = round(guests * drinks_per_guest)
    alcoholic_drinks = round(total_drinks * (1.0 - non_alcoholic_pct))
    non_alcoholic_drinks = total_drinks - alcoholic_drinks

    # ── STEP 2: Per-cocktail servings ────────────────────────────────────────
    cocktail_servings: dict[str, int] = {}
    for allocation in menu:
        servings = round(total_drinks * allocation.allocation_pct)
        cocktail_servings[allocation.cocktail_id] = servings

    # ── STEP 3: Expand recipes → raw ingredient requirements ─────────────────
    # ingredient_id → raw_total_amount
    raw_amounts: dict[str, float] = {}

    for allocation in menu:
        cid = allocation.cocktail_id
        servings = cocktail_servings[cid]
        recipe = recipes.get(cid)

        if recipe is None:
            warnings.append(f"Recipe not found for cocktail_id={cid}. Skipped.")
            continue

        for ing in recipe.ingredients:
            if ing.amount is None:
                # Unmeasured ingredient (e.g. "top with soda") — cannot calculate
                warnings.append(
                    f"'{ing.canonical_name}' in '{recipe.name}' has no measured amount. "
                    f"Excluded from calculation."
                )
                continue
            key = ing.ingredient_id
            raw_amounts[key] = raw_amounts.get(key, 0.0) + (ing.amount * servings)

    # ── STEP 4: Aggregate (already done above via dict accumulation) ──────────

    # ── STEP 5: Apply waste buffer ───────────────────────────────────────────
    ingredient_requirements: list[IngredientRequirement] = []

    for ing_id, raw_amt in raw_amounts.items():
        # Find ingredient metadata
        prod_info = ingredient_products.get(ing_id)
        if prod_info is None:
            # We know about this ingredient from recipe but have no product info at all
            req = IngredientRequirement(
                ingredient_id=ing_id,
                canonical_name=f"UNKNOWN({ing_id})",
                category="other",
                unit="ml",
                raw_amount=raw_amt,
                required_amount=raw_amt * (1.0 + waste_buffer_pct),
            )
        else:
            req = IngredientRequirement(
                ingredient_id=ing_id,
                canonical_name=prod_info.canonical_name,
                category=prod_info.category,
                unit=prod_info.unit,
                raw_amount=raw_amt,
                required_amount=raw_amt * (1.0 + waste_buffer_pct),
            )
        ingredient_requirements.append(req)

    # Sort: spirits first, then by category, then name
    category_order = {
        "spirit": 0, "wine": 1, "beer": 2, "liqueur": 3,
        "bitters": 4, "syrup": 5, "juice": 6, "mixer": 7,
        "garnish": 8, "other": 9
    }
    ingredient_requirements.sort(
        key=lambda r: (category_order.get(r.category, 9), r.canonical_name)
    )

    # ── STEPS 6–9: Map to products, calculate packages and costs ─────────────
    purchase_items: list[PurchaseItem] = []
    has_missing_prices = False
    has_missing_mappings = False

    for req in ingredient_requirements:
        prod_info_wrapper = ingredient_products.get(req.ingredient_id)

        if prod_info_wrapper is None or prod_info_wrapper.product is None:
            # No product mapping at all
            has_missing_mappings = True
            warnings.append(
                f"⚠️  No purchasing product mapped for '{req.canonical_name}'. "
                f"Cannot calculate cost."
            )
            purchase_items.append(PurchaseItem(
                ingredient_id=req.ingredient_id,
                canonical_name=req.canonical_name,
                category=req.category,
                product_id=None,
                product_name=None,
                required_amount=req.required_amount,
                unit=req.unit,
                package_size=None,
                package_unit=None,
                packages_required=None,
                unit_price=None,
                total_price=None,
                status=PurchaseStatus.PRODUCT_MAPPING_REQUIRED,
            ))
            continue

        product = prod_info_wrapper.product

        # Step 7: Package quantity (CEILING)
        packages_required: Optional[int] = None
        if product.package_size is not None and product.package_size > 0:
            packages_required = math.ceil(req.required_amount / product.package_size)
        else:
            has_missing_prices = True
            warnings.append(
                f"⚠️  Package size unknown for '{product.product_name}'. "
                f"Cannot calculate package count."
            )

        # Step 8–9: Cost calculation
        unit_price: Optional[float] = None
        total_price: Optional[float] = None
        status = PurchaseStatus.OK

        if product.price_after_vat is not None and product.package_size is not None:
            unit_price = product.price_after_vat  # price per package
            # Round at the point the figure becomes a reported line item.
            # 3 × 99.90 is 299.70000000000005 in binary floating point, and that
            # must never reach a shopping list someone orders from.
            total_price = (
                round(packages_required * product.price_after_vat, 2)
                if packages_required else None
            )
        else:
            has_missing_prices = True
            status = PurchaseStatus.PRICE_MISSING
            warnings.append(
                f"⚠️  Price missing for '{product.product_name}'. "
                f"Cost cannot be calculated."
            )

        if packages_required is None:
            status = PurchaseStatus.PACKAGE_SIZE_MISSING

        if product.supplier_id is None:
            if status == PurchaseStatus.OK:
                status = PurchaseStatus.SUPPLIER_NOT_MAPPED

        purchase_items.append(PurchaseItem(
            ingredient_id=req.ingredient_id,
            canonical_name=req.canonical_name,
            category=req.category,
            product_id=product.product_id,
            product_name=product.product_name,
            required_amount=req.required_amount,
            unit=req.unit,
            package_size=product.package_size,
            package_unit=product.package_unit,
            packages_required=packages_required,
            unit_price=unit_price,
            total_price=total_price,
            status=status,
            supplier_id=product.supplier_id,
            supplier_name=product.supplier_name,
            product_url=product.product_url,
        ))

    # ── STEP 10: Total cost, budget comparison ───────────────────────────────
    total_cost: Optional[float] = None
    cost_per_guest: Optional[float] = None
    budget_variance: Optional[float] = None
    budget_status: Optional[BudgetStatus] = None

    known_costs = [
        item.total_price
        for item in purchase_items
        if item.total_price is not None
    ]

    # Money is rounded to agorot at the point it becomes a reported figure.
    # Summing binary floats leaves artifacts (…3400000000001) that must never
    # reach an invoice, a budget comparison, or the UI.
    if not has_missing_prices and not has_missing_mappings and known_costs:
        total_cost = round(sum(known_costs), 2)
        cost_per_guest = round(total_cost / guests, 2) if guests > 0 else None
    elif known_costs:
        # Partial cost — sum what we know, note it's incomplete
        total_cost = round(sum(known_costs), 2)
        cost_per_guest = round(total_cost / guests, 2) if guests > 0 else None
        warnings.insert(0,
            f"⚠️  Partial cost only: ₪{total_cost:,.0f} of known items. "
            f"Missing prices/mappings prevent full cost calculation."
        )

    if total_cost is not None and budget is not None:
        budget_variance = round(budget - total_cost, 2)
        if budget_variance > 50:
            budget_status = BudgetStatus.UNDER_BUDGET
        elif budget_variance < -50:
            budget_status = BudgetStatus.OVER_BUDGET
        else:
            budget_status = BudgetStatus.ON_BUDGET

    # Cost breakdown by category.
    # If any item in a category is missing a price, the category total is
    # unknown regardless of the order in which purchase items are processed.
    cost_by_category: dict[str, Optional[float]] = {}
    for item in purchase_items:
        cat = item.category

        if item.total_price is None:
            cost_by_category[cat] = None
            continue

        if cat not in cost_by_category:
            cost_by_category[cat] = item.total_price
        elif cost_by_category[cat] is not None:
            cost_by_category[cat] += item.total_price

    return EventCalculationResult(
        guests=guests,
        drinks_per_guest=drinks_per_guest,
        non_alcoholic_pct=non_alcoholic_pct,
        waste_buffer_pct=waste_buffer_pct,
        total_drinks=total_drinks,
        alcoholic_drinks=alcoholic_drinks,
        non_alcoholic_drinks=non_alcoholic_drinks,
        cocktail_servings=cocktail_servings,
        ingredient_requirements=ingredient_requirements,
        purchase_items=purchase_items,
        total_cost=total_cost,
        cost_per_guest=cost_per_guest,
        budget=budget,
        budget_variance=budget_variance,
        budget_status=budget_status,
        warnings=warnings,
        has_missing_prices=has_missing_prices,
        has_missing_mappings=has_missing_mappings,
        cost_by_category=cost_by_category,
    )

"""
מודול 2 — מוצרים ומחירים
=========================

מה המודול הזה יודע:
- אילו Products קיימים
- באילו Suppliers הם נמכרים
- מחיר של SupplierProduct
- גודל האריזה הספציפי אצל אותו ספק
- האם הרשומה עדכנית / זמינה
- השוואת מחיר בין Listings תקינים

מה הוא לא יודע:
- קוקטיילים
- מהו "רום לבן" במתכון
- איזה מוצר מחליף איזה מרכיב
- כמה אורחים יש
- כמה צריך לקנות לאירוע

הדאטה לא נשמר כאן Hard-coded.
הוא נקרא מהטבלאות Product / Supplier / SupplierProduct.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Product, Supplier, SupplierProduct
from app.engine.calculator import ProductInfo


ProductId = uuid.UUID | str


# ============================================================
# UNIT NORMALIZATION
# ============================================================

# יחידות שניתן לנרמל בלי לנחש.
#
# המנוע עובד עם יחידות בסיס:
#
#   litre -> ml
#   kg    -> g
#   unit  -> pieces
#
# אם אנחנו לא מכירים יחידה מסוימת,
# אנחנו לא ממציאים המרה.
_UNIT_NORMALIZATION: dict[str, tuple[str, float]] = {
    "ml": ("ml", 1.0),
    "milliliter": ("ml", 1.0),
    "milliliters": ("ml", 1.0),

    "l": ("ml", 1000.0),
    "liter": ("ml", 1000.0),
    "liters": ("ml", 1000.0),
    "litre": ("ml", 1000.0),
    "litres": ("ml", 1000.0),

    "g": ("g", 1.0),
    "gram": ("g", 1.0),
    "grams": ("g", 1.0),

    "kg": ("g", 1000.0),
    "kilogram": ("g", 1000.0),
    "kilograms": ("g", 1000.0),

    "piece": ("pieces", 1.0),
    "pieces": ("pieces", 1.0),
    "unit": ("pieces", 1.0),
    "units": ("pieces", 1.0),
}


def _as_uuid(value: ProductId) -> uuid.UUID:
    """ממיר str או UUID ל-UUID."""

    if isinstance(value, uuid.UUID):
        return value

    return uuid.UUID(str(value))


# ============================================================
# PACKAGE SIZE
# ============================================================

def normalize_package(
    size: float | None,
    unit: str | None,
) -> tuple[float | None, str]:
    """
    מנרמל יחידות רק כשיש המרה ודאית.

    דוגמאות:

        1 L  -> 1000 ml
        1 kg -> 1000 g

    יחידה לא מוכרת נשמרת כמו שהיא.

    לא מנחשים.
    """

    raw_unit = (unit or "ml").strip().lower()

    normalized_unit, multiplier = _UNIT_NORMALIZATION.get(
        raw_unit,
        (raw_unit, 1.0),
    )

    if size is None:
        return None, normalized_unit

    return float(size) * multiplier, normalized_unit


def effective_package(
    listing: SupplierProduct,
) -> tuple[float | None, str]:
    """
    מחזיר את גודל האריזה האמיתי אצל הספק.

    סדר העדיפות:

    1. SupplierProduct.package_size
       הגודל שמופיע אצל החנות בפועל.

    2. Product.package_size
       הגודל הכללי של המוצר.

    למה?

    אותו מוצר יכול להימכר:

        חנות A -> 700ml
        חנות B -> 1000ml

    ולכן הגודל של החנות חייב לנצח.

    זה מונע את טעות 700ml מול 1L.
    """

    product = listing.product

    if listing.package_size is not None:

        size = float(listing.package_size)

        unit = listing.package_unit or (
            product.package_unit
            if product
            else "ml"
        )

    else:

        size = (
            float(product.package_size)
            if product is not None
            and product.package_size is not None
            else None
        )

        unit = (
            product.package_unit
            if product
            else "ml"
        )

    return normalize_package(size, unit)


# ============================================================
# PRICE
# ============================================================

def effective_price_after_vat(
    listing: SupplierProduct,
) -> float | None:
    """
    המחיר שמשמש את החישוב.

    משתמשים במחיר כולל מע"מ.

    None אומר:
        אין מחיר ידוע.

    None אף פעם לא הופך ל-0.
    """

    if listing.price_after_vat is None:
        return None

    return float(listing.price_after_vat)


# ============================================================
# LISTING STATUS / WARNINGS
# ============================================================

def listing_problems(
    listing: SupplierProduct,
) -> tuple[str, ...]:
    """
    מחזיר את כל האזהרות / הבעיות שיש ב-Listing.

    חשוב מאוד:

    "המחיר היסטורי" הוא אזהרה,
    אבל הוא לא בהכרח מונע חישוב.

    לדוגמה:

        מחיר = 76 ₪
        גודל = 700ml
        historical = True

    עדיין אפשר לחשב:

        108.57 ₪ לליטר

    אבל צריך להציג למשתמש:
        ⚠ המחיר היסטורי

    בעיות אחרות כמו מחיר חסר או גודל חסר
    כן מונעות השוואה.
    """

    problems: list[str] = []

    if not listing.available:
        problems.append("המוצר לא זמין")

    if listing.is_historical:
        problems.append("המחיר היסטורי")

    if (
        listing.supplier is not None
        and not listing.supplier.active
    ):
        problems.append("הספק לא פעיל")

    if effective_price_after_vat(listing) is None:
        problems.append("אין מחיר עדכני כולל מע״מ")

    size, _unit = effective_package(listing)

    if size is None:
        problems.append("גודל האריזה לא ידוע")

    elif size <= 0:
        problems.append("גודל האריזה אינו תקין")

    return tuple(problems)


def is_comparable(
    listing: SupplierProduct,
) -> bool:
    """
    האם אפשר לבצע חישוב והשוואת מחיר על ה-Listing.

    מחיר היסטורי עדיין ניתן להשוואה.

    כלומר:

        historical=True
        price=76
        size=700ml

    -> אפשר לחשב מחיר לליטר.

    הוא עדיין יסומן באזהרה דרך listing_problems().

    מה כן פוסל Listing:

    - אינו זמין
    - ספק אינו פעיל
    - אין מחיר
    - אין גודל
    - גודל <= 0
    """

    if not listing.available:
        return False

    if (
        listing.supplier is not None
        and not listing.supplier.active
    ):
        return False

    price = effective_price_after_vat(listing)

    if price is None:
        return False

    size, _unit = effective_package(listing)

    if size is None:
        return False

    if size <= 0:
        return False

    return True


# ============================================================
# UNIT PRICE
# ============================================================

def price_per_base_unit(
    listing: SupplierProduct,
) -> tuple[float, str] | None:
    """
    מחיר ליחידת בסיס.

    נוזלים:
        ₪ / ml

    משקל:
        ₪ / g

    יחידות:
        ₪ / piece

    מחיר היסטורי עדיין יכול להשתתף,
    כל עוד המחיר והגודל ידועים.
    """

    if not is_comparable(listing):
        return None

    price = effective_price_after_vat(listing)
    size, unit = effective_package(listing)

    if (
        price is None
        or size is None
        or size <= 0
    ):
        return None

    return price / size, unit


def per_litre(
    listing: SupplierProduct,
) -> float | None:
    """
    מחיר לליטר.

    עובד רק עבור מוצרים שניתנים לנרמול ל-ml.

    לדוגמה:

        price = 76
        size  = 700ml

        76 / 700 * 1000

        = 108.57 ₪ לליטר

    עבור מוצר ב-pieces:

        per_litre -> None

    וזה תקין.
    """

    result = price_per_base_unit(listing)

    if result is None:
        return None

    price_per_unit, unit = result

    if unit != "ml":
        return None

    return price_per_unit * 1000


# ============================================================
# CHEAPEST LISTING
# ============================================================

def cheapest(
    listings: Sequence[SupplierProduct],
) -> SupplierProduct | None:
    """
    מחזיר את ה-Listing הזול ביותר ליחידת בסיס.

    לדוגמה:

        Bacardi
        1000ml
        110 ₪
        -> 0.11 ₪ / ml

        Captain
        700ml
        94 ₪
        -> 0.134 ₪ / ml

    Bacardi זול יותר למרות שמחיר המדף גבוה יותר.

    לא משווים יחידות מסוגים שונים:

        ml מול pieces
        ml מול g
        pieces מול g

    אם מגיעות יחידות שונות באותה רשימה,
    זו שגיאת נתונים / קלט.
    """

    comparable: list[
        tuple[SupplierProduct, float, str]
    ] = []

    for listing in listings:

        result = price_per_base_unit(listing)

        if result is None:
            continue

        unit_price, unit = result

        comparable.append(
            (
                listing,
                unit_price,
                unit,
            )
        )

    if not comparable:
        return None

    units = {
        unit
        for _listing, _price, unit
        in comparable
    }

    if len(units) != 1:
        raise ValueError(
            "Cannot compare listings "
            f"with different base units: "
            f"{sorted(units)}"
        )

    return min(
        comparable,
        key=lambda item: item[1],
    )[0]


# ============================================================
# PRODUCT -> CALCULATOR
# ============================================================

def to_product_info(
    product: Product,
    listing: SupplierProduct | None = None,
) -> ProductInfo:
    """
    ממיר Product + SupplierProduct
    ל-ProductInfo שמנוע החישוב מכיר.

    אם קיבלנו Listing:

        SupplierProduct.package_size

    גובר על:

        Product.package_size

    אם אין Listing:

        עדיין יודעים איזה Product זה,
        אבל אין מחיר ספק.
    """

    if listing is not None:

        package_size, package_unit = (
            effective_package(listing)
        )

    else:

        package_size, package_unit = (
            normalize_package(
                (
                    float(product.package_size)
                    if product.package_size is not None
                    else None
                ),
                product.package_unit,
            )
        )

    return ProductInfo(
        product_id=str(product.id),

        product_name=product.name,

        package_size=package_size,

        package_unit=package_unit,

        price_before_vat=(
            float(listing.price_before_vat)
            if listing is not None
            and listing.price_before_vat is not None
            else None
        ),

        price_after_vat=(
            float(listing.price_after_vat)
            if listing is not None
            and listing.price_after_vat is not None
            else None
        ),

        supplier_id=(
            str(listing.supplier_id)
            if listing is not None
            and listing.supplier_id is not None
            else None
        ),

        supplier_name=(
            listing.supplier.name
            if listing is not None
            and listing.supplier is not None
            else None
        ),

        product_url=(
            listing.product_url
            if listing is not None
            else None
        ),
    )


# ============================================================
# DATABASE LISTINGS
# ============================================================

async def get_listings(
    db: AsyncSession,
    product_ids: Iterable[ProductId],
    *,
    include_historical: bool = False,
) -> dict[str, list[SupplierProduct]]:
    """
    טוען Listings זמינים עבור Products.

    include_historical=False

        רק המחירים העדכניים.

    include_historical=True

        גם מחירים היסטוריים.

    למה צריך היסטוריים?

    כי לפעמים זה המידע היחיד שיש.

    עדיף:

        מחיר היסטורי + אזהרה

    מאשר:

        מוצר נעלם מהעלות לחלוטין.

    Module 3 אחראי לתת עדיפות למחיר עדכני
    ורק אם אין כזה להשתמש בהיסטורי.
    """

    ids = [
        _as_uuid(value)
        for value in product_ids
    ]

    if not ids:
        return {}

    conditions = [
        SupplierProduct.product_id.in_(ids),

        SupplierProduct.available == True,  # noqa: E712
    ]

    if not include_historical:

        conditions.append(
            SupplierProduct.is_historical == False  # noqa: E712
        )

    result = await db.execute(
        select(SupplierProduct)
        .options(
            selectinload(
                SupplierProduct.product
            ),
            selectinload(
                SupplierProduct.supplier
            ),
        )
        .where(*conditions)
        .order_by(
            SupplierProduct.product_id,

            # מחירים עדכניים קודם.
            SupplierProduct.is_historical,

            # בתוך אותה קבוצה:
            # האחרון שנבדק קודם.
            SupplierProduct
            .last_checked_at
            .desc()
            .nullslast(),
        )
    )

    grouped: dict[
        str,
        list[SupplierProduct],
    ] = {}

    for listing in result.scalars().all():

        grouped.setdefault(
            str(listing.product_id),
            [],
        ).append(listing)

    return grouped


async def get_current_listings(
    db: AsyncSession,
    product_ids: Iterable[ProductId],
) -> dict[str, list[SupplierProduct]]:
    """
    מחזיר רק Listings עם מחיר עדכני.

    נשמרת כפונקציה נפרדת כדי שקוד קיים
    שמשתמש בה לא יצטרך להשתנות.
    """

    return await get_listings(
        db,
        product_ids,
        include_historical=False,
    )


# ============================================================
# ORDERABLE SHOP
# ============================================================

def is_orderable_shop(
    listing: SupplierProduct,
) -> bool:
    """
    האם מדובר בחנות שאפשר לבצע ממנה הזמנה בפועל.

    חשוב:

    is_retailer=False לא אומר שהמחיר לא שימושי.

    לדוגמה:

        מחיר היסטורי
        חומר גלם תוצרת בית
        מחיר שהוזן ידנית

    עדיין יכולים להיות שימושיים לחישוב עלות,
    אבל הם לא חנות שאפשר לבצע ממנה הזמנה.

    לכן זה מופרד מ-is_comparable().
    """

    supplier = listing.supplier

    if supplier is None:
        return False

    return (
        bool(supplier.active)
        and bool(supplier.is_retailer)
    )


# ============================================================
# MINIMUM ORDER
# ============================================================

def order_shortfall(
    supplier: Supplier,
    basket_total: float,
) -> float | None:
    """
    כמה כסף חסר עד מינימום ההזמנה.

    לדוגמה:

        minimum_order = 200
        basket_total  = 155

        -> 45 ₪ חסרים.

    None אומר:

        אין מינימום

    או:

        כבר עברנו את המינימום.
    """

    minimum = supplier.minimum_order

    if minimum is None:
        return None

    minimum = float(minimum)

    if basket_total >= minimum:
        return None

    return round(
        minimum - basket_total,
        2,
    )


# ============================================================
# DELIVERY
# ============================================================

def delivery_cost(
    supplier: Supplier,
    basket_total: float,
) -> float | None:
    """
    דמי משלוח לסל.

    מחזיר:

        0.0
            אם עוברים את הסף למשלוח חינם.

        מספר
            אם דמי המשלוח ידועים.

        None
            אם לא יודעים.

    לעולם לא ממציאים דמי משלוח.
    """

    free_over = supplier.free_delivery_over
    fee = supplier.delivery_fee

    if (
        free_over is not None
        and basket_total >= float(free_over)
    ):
        return 0.0

    if fee is None:
        return None

    return float(fee)


# ============================================================
# CHEAPEST BY PRODUCT
# ============================================================

def cheapest_by_product(
    listings_by_product:
    dict[str, list[SupplierProduct]],
) -> dict[str, SupplierProduct]:
    """
    בוחר לכל Product
    את ה-Listing הזול ביותר מתוך הרשימה שנשלחה.

    חשוב:

    אם רוצים רק מחיר עדכני,
    צריך לקרוא קודם ל-get_current_listings().

    אם הרשימה כוללת historical,
    cheapest יכול לחשב אותם.

    Module 3 הוא זה שנותן עדיפות:
        current -> historical fallback.
    """

    result: dict[
        str,
        SupplierProduct,
    ] = {}

    for (
        product_id,
        listings,
    ) in listings_by_product.items():

        best = cheapest(listings)

        if best is not None:
            result[product_id] = best

    return result
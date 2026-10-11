"""
מודול 3 — החיבור בין מתכון למוצר
=================================

מה המודול הזה יודע:
- איזה מוצר עונה על מרכיב שבמתכון
- מה האירוע הזה בחר, בשונה מההמלצה הכללית
- אילו מוצרים אחרים יכולים למלא את אותו מקום
- מה חסר, ולמה

מה הוא לא יודע:
- כמה אורחים יש
- כמה מ״ל צריך
- כמה זה עולה בסך הכל

זה הלב של המערכת.
מודול 1 אומר "רום לבן". מודול 2 אומר "רום קריביקה, ₪64, עולם היין".
המודול הזה הוא היחיד שמוסמך לומר שאלה אותו דבר.

הדאטה לא נשמר כאן Hard-coded.
הוא נקרא מהטבלאות IngredientProductMapping ו-
EventIngredientProductOverride.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Ingredient, Product
from app.models.product import IngredientProductMapping
from app.models.event import EventIngredientProductOverride
from app.engine.calculator import IngredientWithProduct, ProductInfo

from app.services.module1_recipes import can_substitute
from app.services.module2_products import cheapest, get_listings, to_product_info


IngredientId = uuid.UUID | str
EventId = uuid.UUID | str


def _as_uuid(value: IngredientId) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value

    return uuid.UUID(str(value))


# ── למה IngredientProductMapping ולא Product.ingredient_id ────────────────
#
# בדאטהבייס יש שתי דרכים להגיד "המוצר הזה הוא המרכיב הזה":
#
#     Product.ingredient_id        עמודה ישירה על המוצר
#     IngredientProductMapping     טבלת קשר נפרדת
#
# שתיהן קיימות, שתיהן מתוחזקות, ואפשר שיסתרו זו את זו.
#
# המודול הזה בוחר בטבלת הקשר, משלוש סיבות:
#
#   1. זו הדרך שמנוע החישוב כבר משתמש בה היום. בחירה אחרת הייתה
#      משנה תוצאות בלי שאיש ביקש.
#   2. היא מאפשרת כמה מוצרים לאותו מרכיב, וזה בדיוק מה שנדרש כדי
#      להציע חלופה. עמודה אחת על המוצר מאפשרת רק אחד.
#   3. יש עליה preferred ו-substitution_allowed — עובדות שאין להן
#      מקום על העמודה הישירה.
#
# Product.ingredient_id נשאר כקיצור דרך שסקריפטי הייבוא ומסך המיפוי
# משתמשים בו. הוא לא מקור האמת לחישוב.


@dataclass(frozen=True)
class Match:
    """
    ההחלטה על מרכיב אחד: איזה מוצר נבחר, ולמה דווקא הוא.
    """

    ingredient_id: str
    ingredient_name: str

    product: Product | None
    source: str
    # "event"    האירוע הזה בחר במפורש
    # "house"    ההמלצה הכללית
    # "missing"  אין מיפוי בכלל

    reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.product is not None


async def get_matches(
    db: AsyncSession,
    ingredient_ids: Iterable[IngredientId],
    event_id: EventId | None = None,
) -> dict[str, Match]:
    """
    לכל מרכיב — איזה מוצר קונים בשבילו.

    סדר הפתרון, ושלושת השלבים חשובים בסדר הזה
    ------------------------------------------

        1. הבחירה של האירוע הזה, אם יש
        2. ההמלצה הכללית (preferred)
        3. כלום — מדווח כחסר, אף פעם לא ניחוש

    הבחירה של האירוע גוברת כי היא האמירה הספציפית יותר: הבית ממליץ
    על אולמקה, האירוע הזה קונה משהו אחר. ההמלצה הכללית לא משתנה
    בגלל זה, ואף אירוע אחר לא מושפע.

    השלב השלישי הוא לא כישלון של הקוד. "אין לזה מוצר" היא תשובה
    לגיטימית שמישהו צריך לראות ולהחליט לגביה, ומספר שהומצא במקומה
    הוא בדיוק מה שמייצר הצעת מחיר שגויה.
    """
    ids = [_as_uuid(value) for value in ingredient_ids]

    if not ids:
        return {}

    # ── שלב 2 קודם: ההמלצה הכללית ────────────────────────────────────
    mapping_result = await db.execute(
        select(IngredientProductMapping)
        .options(
            selectinload(IngredientProductMapping.product),
            selectinload(IngredientProductMapping.ingredient),
        )
        .where(
            IngredientProductMapping.ingredient_id.in_(ids),
            IngredientProductMapping.preferred == True,  # noqa: E712
        )
    )

    house = {
        str(m.ingredient_id): m
        for m in mapping_result.scalars().all()
    }

    # ── שלב 1: מה שהאירוע הזה בחר ────────────────────────────────────
    chosen: dict[str, EventIngredientProductOverride] = {}

    if event_id is not None:
        override_result = await db.execute(
            select(EventIngredientProductOverride)
            .options(
                selectinload(EventIngredientProductOverride.product)
            )
            .where(
                EventIngredientProductOverride.event_id
                == _as_uuid(event_id),

                EventIngredientProductOverride.ingredient_id.in_(ids),
            )
        )

        chosen = {
            str(o.ingredient_id): o
            for o in override_result.scalars().all()
        }

    # שמות המרכיבים, גם לאלה שאין להם מיפוי בכלל
    ing_result = await db.execute(
        select(Ingredient).where(Ingredient.id.in_(ids))
    )

    names = {
        str(i.id): i.canonical_name
        for i in ing_result.scalars().all()
    }

    matches: dict[str, Match] = {}

    for ingredient_id in [str(i) for i in ids]:

        name = names.get(ingredient_id, "?")

        override = chosen.get(ingredient_id)

        if override is not None and override.product is not None:
            matches[ingredient_id] = Match(
                ingredient_id=ingredient_id,
                ingredient_name=name,
                product=override.product,
                source="event",
                reason=override.reason,
            )
            continue

        mapping = house.get(ingredient_id)

        if mapping is not None and mapping.product is not None:
            matches[ingredient_id] = Match(
                ingredient_id=ingredient_id,
                ingredient_name=name,
                product=mapping.product,
                source="house",
                reason=mapping.notes,
            )
            continue

        matches[ingredient_id] = Match(
            ingredient_id=ingredient_id,
            ingredient_name=name,
            product=None,
            source="missing",
            reason=f"אין מוצר משויך ל'{name}', אז אי אפשר לתמחר אותו.",
        )

    return matches


@dataclass(frozen=True)
class Pricing:
    """
    מה שהמנוע צריך, ולצידו מה שאדם צריך לדעת על המחירים האלה.

    products    מרכיב -> מוצר ומחיר. זה מה שנכנס למנוע.
    historical  מרכיבים שתומחרו ממחיר ישן ולא ממדף עדכני
    unpriced    מרכיבים שאין להם מחיר בכלל
    """

    products: dict[str, IngredientWithProduct]
    historical: list[str]
    unpriced: list[str]


def _pick_listing(listings: list) -> tuple[object | None, bool]:
    """
    איזו רשומה מייצגת את המוצר הזה, ומהו המחיר שלו לאירוע.

    מחזיר (רשומה, האם המחיר היסטורי).

    למה הזול ביותר ולא הראשונה
    --------------------------
    זה היה באג אמיתי בשני המסלולים. הקאווה איבריקה נמכרת בארבע
    חנויות — ₪35, ₪38, ₪42, ₪60 — ולכולן אותו last_checked_at,
    אז המיון שרירותי. הקוד הקיים נפל על ₪42 והגרסה הראשונה שלי
    על ₪60. אף אחד מהם לא בחר, שניהם פשוט לקחו את מה שיצא ראשון.

    ₪35 מול ₪60 זה כמעט פי שניים על כל בקבוק.

    עדכני קודם, היסטורי כגיבוי
    --------------------------
    מחיר היסטורי נבחר רק כשאין שום מחיר עדכני. הוא עדיף על
    כלום — אנגוסטורה וסודה קיימים רק ברשימה הישנה — אבל מי
    שמסתמך עליו חייב לדעת, ולכן הדגל חוזר החוצה.
    """
    if not listings:
        return None, False

    current = [l for l in listings if not l.is_historical]
    old = [l for l in listings if l.is_historical]

    for group, is_old in ((current, False), (old, True)):
        if not group:
            continue
        try:
            best = cheapest(group)
        except ValueError:
            # יחידות בסיס שונות לאותו מוצר — שגיאת נתונים, לא
            # החלטת מחיר. לא בוחרים שרירותית, מדווחים.
            best = None
        if best is not None:
            return best, is_old
        # אין רשומה ברת-השוואה בקבוצה הזו; לפחות נשמור את זהות
        # המוצר, גם אם בלי מחיר.
        return group[0], is_old

    return None, False


async def resolve_pricing(
    db: AsyncSession,
    ingredient_ids: Iterable[IngredientId],
    event_id: EventId | None = None,
) -> Pricing:
    """
    מה שמנוע החישוב מצפה לקבל: מרכיב אחד, מוצר אחד, מחיר אחד.

    למה זה עובר דרך to_product_info של מודול 2
    ------------------------------------------
    כי שם מטופל גודל האריזה הנכון, וזה לא פרט טכני.

    הקוד שקיים היום ב-_build_engine_inputs בונה את ProductInfo ככה:

        package_size = float(prod.package_size)      # events.py:218

    כלומר לוקח את הגודל מ-Product ו**מתעלם מ-SupplierProduct.package_size** —
    בדיוק העמודה שנוספה למערכת כדי לתקן את טעות ה-700 מול 1000.
    קמפרי ואפרול נמכרים בליטר בשתי החנויות שנבדקו, והרשומה אמרה 700,
    אז המחיר למ״ל יצא גבוה בכ-30%.

    effective_package של מודול 2 נותן עדיפות לגודל של החנות, ורק
    בהיעדרו נופל לגודל של המוצר. המעבר דרכו הוא כל התיקון.
    """
    matches = await get_matches(db, ingredient_ids, event_id)

    product_ids = [
        str(m.product.id)
        for m in matches.values()
        if m.product is not None
    ]

    # כולל היסטורי, כי לחלק מהמרכיבים זה הנתון היחיד שקיים.
    # הבחירה בין עדכני להיסטורי נעשית ב-_pick_listing, לא כאן.
    listings_by_product = await get_listings(
        db, product_ids, include_historical=True
    )

    ing_result = await db.execute(
        select(Ingredient).where(
            Ingredient.id.in_([_as_uuid(i) for i in matches])
        )
    )

    ingredients = {
        str(i.id): i
        for i in ing_result.scalars().all()
    }

    out: dict[str, IngredientWithProduct] = {}
    historical: list[str] = []
    unpriced: list[str] = []

    for ingredient_id, match in matches.items():

        ingredient = ingredients.get(ingredient_id)

        if ingredient is None:
            continue

        product_info: ProductInfo | None = None

        if match.product is not None:

            listings = listings_by_product.get(
                str(match.product.id),
                [],
            )

            listing, from_old_list = _pick_listing(listings)

            product_info = to_product_info(match.product, listing)

            if product_info.price_after_vat is None:
                unpriced.append(ingredient.canonical_name)
            elif from_old_list:
                historical.append(ingredient.canonical_name)

        else:
            unpriced.append(ingredient.canonical_name)

        out[ingredient_id] = IngredientWithProduct(
            ingredient_id=ingredient_id,
            canonical_name=ingredient.canonical_name,
            category=ingredient.category or "other",
            unit=ingredient.unit_type or "ml",
            product=product_info,
        )

    return Pricing(products=out, historical=historical, unpriced=unpriced)


async def to_engine_inputs(
    db: AsyncSession,
    ingredient_ids: Iterable[IngredientId],
    event_id: EventId | None = None,
) -> dict[str, IngredientWithProduct]:
    """
    רק מה שהמנוע צריך — מרכיב אחד, מוצר אחד, מחיר אחד.

    זהה לשלישייה ש-_build_engine_inputs מחזירה, כדי שאפשר יהיה
    להחליף אותה בלי לגעת בשום דבר אחר.

    האזהרות על מחירים היסטוריים וחסרים זמינות ב-resolve_pricing.
    """
    return (await resolve_pricing(db, ingredient_ids, event_id)).products


async def find_alternatives(
    db: AsyncSession,
    ingredient_id: IngredientId,
) -> list[Product]:
    """
    מה עוד יכול למלא את המקום הזה.

    הכלל של טופז: כשאין את המותג שבמתכון, מציעים אחר מאותו סוג.
    "לא חייב להיות רום מסוים — כל רום שירצו."

    איך זה עובד
    -----------
    המתכון מבקש Havana Club. ה-substitute_group שלו הוא "white_rum".
    כל מרכיב אחר עם אותה קבוצה הוא מקום לגיטימי לחפש בו מוצרים.

    ומה שלא קורה
    ------------
    מרכיב שה-substitute_group שלו None לא מקבל שום הצעה. זו לא
    מגבלה טכנית — זו אמירה. נגרוני עם מרר אדום אחר הוא משקה אחר,
    ו"לא נמצא" נכון יותר מהחלפה שאף אחד לא ביקש.

    can_substitute של מודול 1 הוא שמכריע. המודול הזה רק מחפש.
    """
    wanted = await db.get(Ingredient, _as_uuid(ingredient_id))

    if wanted is None or wanted.substitute_group is None:
        return []

    family_result = await db.execute(
        select(Ingredient).where(
            Ingredient.substitute_group == wanted.substitute_group
        )
    )

    family = [
        i for i in family_result.scalars().all()
        if can_substitute(wanted.substitute_group, i.substitute_group)
    ]

    if not family:
        return []

    product_result = await db.execute(
        select(Product)
        .join(
            IngredientProductMapping,
            IngredientProductMapping.product_id == Product.id,
        )
        .where(
            IngredientProductMapping.ingredient_id.in_(
                [i.id for i in family]
            ),
            Product.active == True,  # noqa: E712
        )
    )

    # אותו מוצר יכול להיות ממופה לכמה מרכיבים באותה קבוצה
    seen: set[str] = set()
    unique: list[Product] = []

    for product in product_result.scalars().all():

        key = str(product.id)

        if key not in seen:
            seen.add(key)
            unique.append(product)

    return unique


def unresolved(matches: dict[str, Match]) -> list[Match]:
    """המרכיבים שאין להם מוצר. אלה שדורשים החלטה של אדם."""
    return [m for m in matches.values() if not m.resolved]

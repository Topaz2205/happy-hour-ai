"""
מודול 1 — מתכונים
==================

מה המודול הזה יודע:
- אילו קוקטיילים קיימים ב-DB
- אילו מרכיבים יש בכל קוקטייל
- כמה מכל מרכיב יש במתכון
- אילו שורות מדודות ואילו ללא כמות

מה הוא לא יודע:
- מוצרים מסחריים
- ספקים / חנויות
- מחירים
- תחליפים
- אורחים / אירועים / כמה צריך לקנות

הדאטה לא נשמר כאן Hard-coded.
הוא נקרא מהטבלאות Cocktail / CocktailIngredient / Ingredient.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Cocktail, CocktailIngredient
from app.engine.calculator import CocktailRecipe, RecipeIngredient


CocktailId = uuid.UUID | str


def _as_uuid(value: CocktailId) -> uuid.UUID:
    """המרת ID שמגיע כ-string או UUID ל-UUID אמיתי."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def to_engine_recipe(cocktail: Cocktail) -> CocktailRecipe:
    """
    ממיר Cocktail מה-DB למבנה שה-calculation engine כבר מכיר.

    amount=None נשמר כ-None ולא מומצאת כמות.
    הסדר נשמר לפי sort_order של המתכון.
    """
    lines = sorted(
        cocktail.ingredients,
        key=lambda ci: ci.sort_order or 0,
    )

    ingredients = [
        RecipeIngredient(
            ingredient_id=str(ci.ingredient.id),
            canonical_name=ci.ingredient.canonical_name,
            amount=float(ci.amount) if ci.amount is not None else None,
            unit=ci.unit or ci.ingredient.unit_type or "ml",
            category=ci.ingredient.category or "other",
            alcoholic=bool(ci.ingredient.alcoholic),
        )
        for ci in lines
        if ci.ingredient is not None
    ]

    return CocktailRecipe(
        cocktail_id=str(cocktail.id),
        name=cocktail.name,
        alcoholic=bool(cocktail.alcoholic),
        has_na_variant=bool(cocktail.non_alc_variant),
        na_variant_instructions=cocktail.non_alc_variant,
        ingredients=ingredients,
    )


def measured_lines(recipe: CocktailRecipe) -> list[RecipeIngredient]:
    """שורות עם כמות מדויקת."""
    return [line for line in recipe.ingredients if line.amount is not None]


def unmeasured_lines(recipe: CocktailRecipe) -> list[RecipeIngredient]:
    """
    שורות שקיימות במתכון אבל אין להן כמות מדויקת.

    הן לא נמחקות ולא הופכות ל-0.
    מודול חישוב/תכנון מאוחר יותר יחליט איך לטפל בהן.
    """
    return [line for line in recipe.ingredients if line.amount is None]


async def get_recipe(
    db: AsyncSession,
    cocktail_id: CocktailId,
) -> CocktailRecipe | None:
    """טוען מתכון אחד מה-DB."""
    cid = _as_uuid(cocktail_id)

    result = await db.execute(
        select(Cocktail)
        .options(
            selectinload(Cocktail.ingredients)
            .selectinload(CocktailIngredient.ingredient)
        )
        .where(Cocktail.id == cid)
    )

    cocktail = result.scalar_one_or_none()

    if cocktail is None:
        return None

    return to_engine_recipe(cocktail)


async def get_recipes(
    db: AsyncSession,
    cocktail_ids: Iterable[CocktailId],
) -> dict[str, CocktailRecipe]:
    """
    טוען כמה מתכונים ב-query מרוכז אחד.

    מחזיר:
        cocktail_id -> CocktailRecipe

    לא מסנן active בכוונה:
    אירוע ישן צריך להמשיך להיות ניתן לחישוב גם אם קוקטייל
    הוצא בעתיד מהתפריט הפעיל.
    """
    ids = [_as_uuid(value) for value in cocktail_ids]

    if not ids:
        return {}

    result = await db.execute(
        select(Cocktail)
        .options(
            selectinload(Cocktail.ingredients)
            .selectinload(CocktailIngredient.ingredient)
        )
        .where(Cocktail.id.in_(ids))
    )

    cocktails = result.scalars().all()

    return {
        str(cocktail.id): to_engine_recipe(cocktail)
        for cocktail in cocktails
    }


def substitute_groups(cocktail: Cocktail) -> dict[str, str | None]:
    """
    לכל מרכיב במתכון — לאיזו קבוצת תחליפים הוא שייך.

        {"<ingredient_id>": "white_rum", "<ingredient_id>": None}

    למה זה כאן, במודול שמצהיר שהוא לא יודע על תחליפים
    -------------------------------------------------
    המודול הזה עדיין לא מחליף כלום, וגם לא צריך. אבל הוא היחיד
    שקורא את שורות ה-Ingredient של המתכון, ובלי שהוא ידווח את
    ה-substitute_group — מודול 3 לא יוכל לדעת שרום מחליף רום.

    זו עובדה על המרכיב, לא החלטה על החלפה. ההחלטה נשארת במודול 3.

    None הוא אמירה ולא חוסר מידע
    ----------------------------
    None פירושו "אין לזה תחליף". שמונה מרכיבים במערכת מסתמכים על
    זה: קמפרי, אפרול, פרנט ברנקה, שרטרז ירוק, לוקסרדו מרסקינו,
    קינה, קרם דה קקאו, אנגוסטורה. נגרוני עם מרר אדום אחר הוא משקה
    אחר, ו"לא במלאי" נכון יותר מהחלפה שאף אחד לא ביקש.

    לא נדרשת שאילתה נוספת: ci.ingredient כבר נטען ב-selectinload.
    """
    return {
        str(ci.ingredient.id): ci.ingredient.substitute_group
        for ci in cocktail.ingredients
        if ci.ingredient is not None
    }


def can_substitute(
    wanted_group: str | None,
    candidate_group: str | None,
) -> bool:
    """
    האם מרכיב מקבוצה אחת יכול למלא את מקומו של מרכיב מקבוצה אחרת.

    שלושה מקרים, ורק אחד מהם מחזיר True:

        "white_rum", "white_rum"   -> True    רום מחליף רום
        "white_rum", "gin"         -> False   ג'ין הוא לא רום
        None, כל דבר               -> False   אין תחליף, גם לא None אחר

    המקרה האחרון הוא החשוב: שני מרכיבים בלי קבוצה אינם "מאותה
    קבוצה". קמפרי ואפרול שניהם None, ואפרול הוא לא קמפרי.
    """
    if wanted_group is None or candidate_group is None:
        return False

    return wanted_group == candidate_group


async def get_all_active_recipes(
    db: AsyncSession,
) -> dict[str, CocktailRecipe]:
    """טוען את ספריית הקוקטיילים הפעילה מה-DB."""
    result = await db.execute(
        select(Cocktail)
        .options(
            selectinload(Cocktail.ingredients)
            .selectinload(CocktailIngredient.ingredient)
        )
        .where(Cocktail.active == True)  # noqa: E712
        .order_by(Cocktail.name)
    )

    cocktails = result.scalars().all()

    return {
        str(cocktail.id): to_engine_recipe(cocktail)
        for cocktail in cocktails
    }

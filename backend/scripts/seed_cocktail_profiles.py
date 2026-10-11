import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import Cocktail


def taste(sweet, sour, bitter, salty=0, umami=0, spicy=0):
    return {
        "sweet": sweet,
        "sour": sour,
        "bitter": bitter,
        "salty": salty,
        "umami": umami,
        "spicy": spicy,
    }


RAW_PROFILES = {
    "Aperol Spritz": (
        taste(3, 0, 3), 2, "aperitivo",
        ["refreshing", "summer", "fizzy", "aperitif", "easy_drinking"],
    ),
    "Boulevardier": (
        taste(2, 0, 4), 5, "whiskey",
        ["bitter", "rich", "herbal", "spirit_forward", "winter"],
    ),
    "Corpse Reviver #2": (
        taste(2, 4, 1), 4, "gin",
        ["citrusy", "crisp", "refreshing", "classic"],
    ),
    "Daiquiri": (
        taste(2, 5, 0), 4, "rum",
        ["refreshing", "citrusy", "summer", "clean", "classic"],
    ),
    "Espresso Martini": (
        taste(3, 0, 2), 4, "vodka",
        ["coffee", "rich", "dessert", "smooth", "after_dinner"],
    ),
    "French 75 (Cognac)": (
        taste(2, 4, 0), 3, "cognac",
        ["refreshing", "fizzy", "citrusy", "elegant", "celebration"],
    ),
    "French 75 (Gin)": (
        taste(2, 4, 0), 3, "gin",
        ["refreshing", "fizzy", "citrusy", "elegant", "celebration"],
    ),
    "Gin Gimlet": (
        taste(2, 5, 0), 4, "gin",
        ["citrusy", "refreshing", "crisp", "classic"],
    ),
    "Hanky Panky": (
        taste(2, 0, 4), 5, "gin",
        ["herbal", "bitter", "spirit_forward", "rich", "complex"],
    ),
    "Industry Sour": (
        taste(2, 4, 4), 4, "herbal_liqueur",
        ["sour", "bitter", "herbal", "complex", "bold"],
    ),
    "Jasmine": (
        taste(2, 4, 3), 4, "gin",
        ["citrusy", "bittersweet", "refreshing", "complex"],
    ),
    "Last Word": (
        taste(3, 4, 2), 4, "gin",
        ["herbal", "citrusy", "complex", "classic"],
    ),
    "Maid in Cuba": (
        taste(3, 4, 0), 3, "rum",
        ["refreshing", "summer", "minty", "fizzy", "easy_drinking"],
    ),
    "Manhattan": (
        taste(2, 0, 2), 5, "whiskey",
        ["spirit_forward", "rich", "classic", "winter"],
    ),
    "Margarita": (
        taste(2, 5, 0), 4, "tequila",
        ["citrusy", "refreshing", "summer", "classic"],
    ),
    "Martini, Dirty": (
        taste(0, 0, 1, salty=5, umami=2), 5, "vodka",
        ["savory", "briny", "dry", "spirit_forward", "classic"],
    ),
    "Martini, Dry": (
        taste(0, 0, 1), 5, "vodka",
        ["dry", "crisp", "spirit_forward", "classic"],
    ),
    "Martini, Wet": (
        taste(1, 0, 1), 4, "vodka",
        ["dry", "herbal", "spirit_forward", "classic"],
    ),
    "Mojito": (
        taste(3, 4, 0), 3, "rum",
        ["refreshing", "summer", "minty", "fizzy", "easy_drinking"],
    ),
    "Moscow Mule": (
        taste(2, 2, 0, spicy=4), 3, "vodka",
        ["refreshing", "spicy", "fizzy", "citrusy", "easy_drinking"],
    ),
    "Negroni": (
        taste(2, 0, 5), 5, "gin",
        ["bitter", "herbal", "spirit_forward", "classic", "aperitif"],
    ),
    "Old Cuban": (
        taste(3, 3, 1), 4, "rum",
        ["refreshing", "minty", "fizzy", "elegant", "celebration"],
    ),
    "Old Fashioned": (
        taste(1, 0, 2), 5, "whiskey",
        ["spirit_forward", "rich", "classic", "winter"],
    ),
    "Sbagliato": (
        taste(3, 0, 4), 2, "aperitivo",
        ["bitter", "refreshing", "fizzy", "aperitif", "easy_drinking"],
    ),
    "Side Car": (
        taste(2, 4, 0), 4, "cognac",
        ["citrusy", "crisp", "classic"],
    ),
    "Toronto": (
        taste(1, 0, 3), 5, "whiskey",
        ["bitter", "herbal", "spirit_forward", "rich", "complex"],
    ),
    "Vermouth Cocktail": (
        taste(2, 0, 2), 2, "vermouth",
        ["herbal", "aperitif", "light", "easy_drinking"],
    ),
    "Vesper Martini": (
        taste(1, 0, 1), 5, "gin",
        ["dry", "crisp", "spirit_forward", "strong", "classic"],
    ),
    "Whiskey Sour": (
        taste(3, 4, 1), 4, "whiskey",
        ["citrusy", "sour", "silky", "classic"],
    ),
    "White Lady": (
        taste(2, 4, 0), 4, "gin",
        ["citrusy", "crisp", "refreshing", "classic"],
    ),
}


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Cocktail).where(
                Cocktail.name.in_(list(RAW_PROFILES.keys()))
            )
        )

        cocktails = result.scalars().all()
        by_name = {c.name: c for c in cocktails}

        updated = 0
        missing = []

        for name, data in RAW_PROFILES.items():
            cocktail = by_name.get(name)

            if cocktail is None:
                missing.append(name)
                continue

            taste_profile, strength, base_spirit, style_tags = data

            cocktail.taste_profile = taste_profile
            cocktail.strength = strength
            cocktail.base_spirit = base_spirit
            cocktail.style_tags = style_tags

            updated += 1

        await db.commit()

        print(f"✅ Updated {updated} cocktail profiles")

        if missing:
            print("⚠️ Missing cocktails:")
            for name in missing:
                print("-", name)
        else:
            print("✅ All 30 cocktail names matched the DB")


if __name__ == "__main__":
    asyncio.run(main())

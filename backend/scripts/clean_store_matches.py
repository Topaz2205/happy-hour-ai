import html
import json
import re
from pathlib import Path

SOURCE = Path("data/relevant_store_matches.json")
OUTPUT = Path("data/relevant_store_matches_clean.json")


REJECT = {
    "Angostura Aromatic Bitters": [
        "cocoa", "cacao", "קקאו",
        "orange", "אורנג", "תפוז",
        "rum", "רום",
    ],

    "Aperol": [
        "spritz", "שפריץ", "prosecco", "פרוסקו",
    ],

    "Beefeater London Dry Gin": [
        "beefeater 24", "ביפיטר 24",
        "pink", "פינק", "תות",
    ],

    "Beluga Noble Vodka": [
        "gold", "גולד",
        "trans atlantic", "טרנס אטלנטיק",
        "adriatic", "אדריאטיק",
        "botanical", "בוטניקל",
        "miniature", "מיניאטורה",
    ],

    "Campari": [
        "spritz", "שפריץ",
        "soda", "סודה",
        "negroni", "נגרוני",
    ],

    "Cognac VS": [
        "whisky", "whiskey", "וויסקי",
        "חביות", "חבית",
        "reserve", "רזרב",
        "napoleon", "נפוליאון",
    ],

    "Dry Curacao Pierre Ferrand": [
        "cognac", "קוניאק",
        "reserve", "רזרב",
        "selection", "סלקסיון",
    ],

    "Fernet Branca": [
        "mint", "menta", "מנטה",
    ],

    "Four Roses Bourbon": [
        "small batch", "סמול באץ",
        "single barrel", "סינגל בארל",
    ],

    "Fresh Lemon Juice": [
        "ליים",
    ],

    "Green Chartreuse": [
        "yellow", "צהוב",
    ],

    "Havana Club Añejo 3 Años Rum": [
        "7 years", "7 שנים",
        "anejo 7", "אנייחו 7",
        "especial", "אספסיאל",
    ],

    "Mancino Secco Dry Vermouth": [
        "rosso", "רוסו",
        "glasses", "כוסות",
    ],

    "Olmeca Silver Tequila": [
        "gold", "גולד",
        "anejo", "אנייחו",
        "altos", "אלטוס",
    ],

    "Red Vermouth": [
        "glasses", "כוסות",
    ],

    "Soda Water": [
        "campari", "קמפרי",
    ],
}


REQUIRE = {
    "Dry Curacao Pierre Ferrand": [
        "curacao", "curaçao", "קורסאו",
    ],

    "Havana Club Añejo 3 Años Rum": [
        "3 years", "3 שנים", "3yo",
    ],

    "Olmeca Silver Tequila": [
        "silver", "סילבר",
    ],

    "Green Chartreuse": [
        "green", "ירוק",
    ],
}


def norm(value):
    value = html.unescape(str(value or "")).lower()

    value = (
        value
        .replace("״", '"')
        .replace("׳", "'")
        .replace("’", "'")
    )

    return " ".join(
        re.sub(
            r"[^a-z0-9\u0590-\u05ff]+",
            " ",
            value,
        ).split()
    )


def contains_any(text, words):
    text = norm(text)

    return any(
        norm(word) in text
        for word in words
    )


def clean_variant(ingredient, match):
    name = match["product"]

    bad = REJECT.get(ingredient, [])

    if bad and contains_any(name, bad):
        return False

    required = REQUIRE.get(ingredient)

    if required and not contains_any(
        name,
        required,
    ):
        return False

    return True


def infer_package_size(name, current):
    """
    Return total ml represented by the listed price.

    Example:
      20 x 330ml -> 6600ml package
      24 x 325ml -> 7800ml package
      'Aperol litre' -> 1000ml
    """

    text = norm(name)

    size = (
        float(current)
        if current is not None
        else None
    )

    # "ליטר" with no numeric amount means 1 litre.
    if size is None:
        if (
            "ליטר" in text
            or re.search(r"\b1\s*l\b", text)
            or "1lt" in text
        ):
            size = 1000.0

    # Multipacks: the price is for the whole pack.
    pack = None

    patterns = [
        r"\b(\d{1,2})\s*יח\b",
        r"\b(\d{1,2})\s*יחידות\b",
        r"\bpack\s*(?:of\s*)?(\d{1,2})\b",
        r"\bbox\s*(?:of\s*)?(\d{1,2})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)

        if m:
            pack = int(m.group(1))
            break

    if pack and size:
        # Only multiply when the parsed size clearly looks
        # like one bottle/can, not an already-total package.
        if size <= 2000:
            size *= pack

    return size


data = json.loads(
    SOURCE.read_text()
)

cleaned = []

removed_count = 0
missing_size_count = 0

for row in data["ingredients"]:
    ingredient = row["ingredient"]
    stores = {}

    for store, matches in row["stores"].items():
        accepted = []

        for match in matches:

            if not clean_variant(
                ingredient,
                match,
            ):
                removed_count += 1
                continue

            match = dict(match)

            match["package_size_ml"] = (
                infer_package_size(
                    match["product"],
                    match.get("size_ml"),
                )
            )

            if (
                match["package_size_ml"]
                is None
            ):
                missing_size_count += 1

            accepted.append(match)

        if accepted:
            stores[store] = accepted

    cleaned.append(
        {
            "ingredient_id": row["ingredient_id"],
            "ingredient": ingredient,
            "store_count": len(stores),
            "stores": stores,
        }
    )


cleaned.sort(
    key=lambda r: (
        r["store_count"],
        r["ingredient"].lower(),
    )
)

OUTPUT.write_text(
    json.dumps(
        {
            "stores": data["stores"],
            "ingredients": cleaned,
        },
        ensure_ascii=False,
        indent=2,
    )
)


print()
print("🍹 STRICT STORE MATCH REPORT")
print("=" * 90)

three = [
    x for x in cleaned
    if x["store_count"] >= 3
]

two = [
    x for x in cleaned
    if x["store_count"] == 2
]

one = [
    x for x in cleaned
    if x["store_count"] == 1
]

zero = [
    x for x in cleaned
    if x["store_count"] == 0
]

print(f"✅ 3+ stores: {len(three)}")
print(f"🟡 2 stores:  {len(two)}")
print(f"🟠 1 store:   {len(one)}")
print(f"🔴 0 stores:  {len(zero)}")

print()
print("0–1 STORE ITEMS")
print("-" * 90)

for row in zero + one:
    shops = (
        ", ".join(row["stores"].keys())
        or "NONE"
    )

    print(
        f"{row['ingredient']:<45} "
        f"{row['store_count']} | {shops}"
    )

print()
print("DATA QUALITY")
print("-" * 90)
print("Rejected wrong variants:", removed_count)
print("Accepted matches still missing size:", missing_size_count)

print()
print("Saved:", OUTPUT)
print("DATABASE UNCHANGED.")

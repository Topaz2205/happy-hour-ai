"""
Turn a plain-language event description into structured parameters.

Pure Python, no LLM. This is what makes the front door work with no API key:
"50 אנשים, מרגריטות, 5000 שקל" and "50 people, margaritas, budget 5000" both
resolve to the same parameters.

Design rule, same as the rest of the system: never guess silently. Anything the
parser could not find comes back as a stated default in `defaults_used`, so the
UI can show the person what was assumed rather than pretending it was told.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Cocktail keywords ─────────────────────────────────────────────────────────
# Maps what a person types (Hebrew or English, however they spell it) to the
# cocktail name as stored in the database. Hebrew has no single accepted
# transliteration for most of these, so several spellings map to one drink.
COCKTAIL_KEYWORDS: dict[str, str] = {
    # Margarita
    "margarita": "Margarita", "margaritas": "Margarita",
    "מרגריטה": "Margarita", "מרגריטות": "Margarita", "מרגריטס": "Margarita",
    # Mojito
    "mojito": "Mojito", "mojitos": "Mojito",
    "מוחיטו": "Mojito", "מוהיטו": "Mojito",
    # Negroni
    "negroni": "Negroni", "נגרוני": "Negroni", "negronis": "Negroni",
    # Spritz
    "spritz": "Aperol Spritz", "aperol": "Aperol Spritz",
    "ספריץ": "Aperol Spritz", "אפרול": "Aperol Spritz",
    # Martini family
    "martini": "Martini, Dry", "מרטיני": "Martini, Dry",
    "espresso martini": "Espresso Martini", "אספרסו מרטיני": "Espresso Martini",
    "vesper": "Vesper Martini", "ווספר": "Vesper Martini",
    # Daiquiri
    "daiquiri": "Daiquiri", "דאקירי": "Daiquiri", "דייקירי": "Daiquiri",
    # Old Fashioned
    "old fashioned": "Old Fashioned", "oldfashioned": "Old Fashioned",
    "אולד פאשן": "Old Fashioned", "אולד פשן": "Old Fashioned",
    # Moscow Mule
    "moscow mule": "Moscow Mule", "mule": "Moscow Mule",
    "מוסקו מיול": "Moscow Mule", "מיול": "Moscow Mule",
    # Whiskey Sour
    "whiskey sour": "Whiskey Sour", "whisky sour": "Whiskey Sour",
    "סאוור": "Whiskey Sour", "וויסקי סאוור": "Whiskey Sour",
    # Manhattan
    "manhattan": "Manhattan", "מנהטן": "Manhattan",
    # Gimlet
    "gimlet": "Gin Gimlet", "גימלט": "Gin Gimlet",
    # Bellini
    "bellini": "Bellini", "בליני": "Bellini",
    # French 75
    "french 75": "French 75 (Gin)", "פרנץ 75": "French 75 (Gin)",
    # Cosmopolitan-ish / White Lady
    "white lady": "White Lady", "וייט ליידי": "White Lady",
    # Boulevardier
    "boulevardier": "Boulevardier", "בולברדייה": "Boulevardier",
    # Basil smash
    "basil smash": "Basil Smash (Classic)", "בזיל סמאש": "Basil Smash (Classic)",
    # Last Word
    "last word": "Last Word", "לאסט וורד": "Last Word",
    # Side Car
    "sidecar": "Side Car", "side car": "Side Car", "סייד קאר": "Side Car",
}

# Spirit words → the cocktails that lead with that spirit. Used when someone
# names a spirit rather than a drink ("something with gin").
SPIRIT_KEYWORDS: dict[str, list[str]] = {
    "gin":     ["Gin Gimlet", "Negroni", "French 75 (Gin)", "White Lady", "Martini, Dry"],
    "ג'ין":    ["Gin Gimlet", "Negroni", "French 75 (Gin)", "White Lady", "Martini, Dry"],
    "גין":     ["Gin Gimlet", "Negroni", "French 75 (Gin)", "White Lady", "Martini, Dry"],
    "vodka":   ["Moscow Mule", "Espresso Martini", "Vesper Martini"],
    "וודקה":   ["Moscow Mule", "Espresso Martini", "Vesper Martini"],
    "rum":     ["Daiquiri", "Mojito", "Old Cuban", "Maid in Cuba"],
    "רום":     ["Daiquiri", "Mojito", "Old Cuban", "Maid in Cuba"],
    "tequila": ["Margarita"],
    "טקילה":   ["Margarita"],
    "whiskey": ["Whiskey Sour", "Old Fashioned", "Manhattan", "Boulevardier"],
    "whisky":  ["Whiskey Sour", "Old Fashioned", "Manhattan", "Boulevardier"],
    "ויסקי":   ["Whiskey Sour", "Old Fashioned", "Manhattan", "Boulevardier"],
    "וויסקי":  ["Whiskey Sour", "Old Fashioned", "Manhattan", "Boulevardier"],
}

# Words that mean "how many people"
_GUEST_WORDS = r"(?:people|guests|persons|pax|אנשים|איש|עובדים|אורחים|משתתפים)"
# Words that mean money
_MONEY_WORDS = r"(?:₪|nis|ils|shekels?|shekel|שקל|שקלים|ש\"ח|תקציב|budget)"


@dataclass
class ParsedRequest:
    guests: Optional[int] = None
    budget: Optional[float] = None
    requested_cocktails: list[str] = field(default_factory=list)
    # Kept apart on purpose. A drink the person NAMED is a firm request and
    # defines the menu; one merely implied by a spirit ("something with gin")
    # is a suggestion that may be dropped or added to.
    named_cocktails: list[str] = field(default_factory=list)
    implied_cocktails: list[str] = field(default_factory=list)
    requested_count: Optional[int] = None
    drinks_per_guest: Optional[float] = None
    defaults_used: list[str] = field(default_factory=list)
    unmatched_terms: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "guests": self.guests,
            "budget": self.budget,
            "requested_cocktails": self.requested_cocktails,
            "named_cocktails": self.named_cocktails,
            "implied_cocktails": self.implied_cocktails,
            "requested_count": self.requested_count,
            "drinks_per_guest": self.drinks_per_guest,
            "defaults_used": self.defaults_used,
            "unmatched_terms": self.unmatched_terms,
        }


def _find_guests(text: str) -> Optional[int]:
    """A number sitting next to a people-word, in either order."""
    patterns = [
        rf"(\d{{1,5}})\s*{_GUEST_WORDS}",      # "50 people" / "50 אנשים"
        rf"{_GUEST_WORDS}\s*(?:ל|for)?\s*(\d{{1,5}})",  # "אנשים 50"
        rf"(?:ל|for)\s*(\d{{1,5}})\s*{_GUEST_WORDS}",   # "ל50 אנשים"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 5000:
                return n

    # Bare "for 30" / "ל30" with no people-word — very common ("mojitos for 30").
    # Only accepted in a plausible headcount range, and never when the number is
    # actually money, which would otherwise read "budget 5000" as 5000 guests.
    for m in re.finditer(r"(?:\bfor\b|ל)\s*(\d{1,4})", text, re.IGNORECASE):
        n = int(m.group(1))
        if not (2 <= n <= 2000):
            continue
        window = text[max(0, m.start() - 12): m.end() + 12]
        if re.search(_MONEY_WORDS, window, re.IGNORECASE):
            continue
        return n
    return None


def _find_budget(text: str) -> Optional[float]:
    """
    A number sitting next to a money word. Handles '5000 שקל', '₪5,000',
    'budget 5000', and the common '6000 אלף שקל' (literally "6000 thousand
    shekel") which people write meaning plain 6000.
    """
    cleaned = text.replace(",", "")
    patterns = [
        rf"{_MONEY_WORDS}\s*(?:של\s*)?(\d{{2,7}})",    # "budget 5000", "₪5000"
        rf"(\d{{2,7}})\s*(?:אלף\s*)?{_MONEY_WORDS}",   # "5000 שקל", "6000 אלף שקל"
    ]
    for pat in patterns:
        m = re.search(pat, cleaned, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 0 < val <= 10_000_000:
                return val
    return None


# Words meaning a serving someone drinks, as opposed to a kind of cocktail.
_SERVING_WORDS = r"(?:\u05db\u05d5\u05e1\u05d5\u05ea|\u05db\u05d5\u05e1|\u05de\u05e9\u05e7\u05d0\u05d5\u05ea|drinks?|glasses?|servings?)"
# Phrases marking "per person".
_PER_PERSON = r"(?:\u05db\u05dc \u05d0\u05d7\u05d3|\u05dc\u05d0\u05d3\u05dd|\u05dc\u05d0\u05d9\u05e9|\u05dc\u05d0\u05d5\u05e8\u05d7|each|per person|per guest|apiece)"


def _find_drinks_per_guest(text: str) -> Optional[float]:
    """
    How many drinks ONE guest has — not how many kinds of cocktail there are.

    "\u05e9\u05db\u05dc \u05d0\u05d7\u05d3 \u05d9\u05e9\u05ea\u05d4 4 \u05db\u05d5\u05e1\u05d5\u05ea" is 4 per person; "3 \u05e7\u05d5\u05e7\u05d8\u05d9\u05d9\u05dc\u05d9\u05dd" is three kinds.
    A serving word or an explicit per-person phrase is required, so the two
    never get confused — reading one as the other changes every quantity in
    the event.
    """
    patterns = [
        rf"(\d+(?:\.\d+)?)\s*{_SERVING_WORDS}",
        rf"{_PER_PERSON}[^.\n]{{0,20}}?(\d+(?:\.\d+)?)",
        rf"(\d+(?:\.\d+)?)\s*[^.\n]{{0,12}}?{_PER_PERSON}",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            n = float(m.group(1))
            # This range is a PARSING guard, not a rule about your event: it
            # stops a budget or a year in the same sentence being mistaken for
            # a per-guest figure. Anything a person would plausibly mean is
            # inside it, and nothing inside it is refused.
            if 0.5 <= n <= 40:
                return n
    return None


def _find_cocktail_count(text: str) -> Optional[int]:
    """"3 cocktails" / "3 קוקטיילים" — how many different drinks they want."""
    pat = r"(\d{1,2})\s*(?:different\s*)?(?:cocktails?|drinks?|קוקטיילים|קוקטייל|סוגים)"
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12:
            return n
    return None


def _find_cocktails(text: str) -> tuple[list[str], list[str]]:
    """
    Return (named cocktails, spirit-implied cocktails).

    Longer keywords are matched first so "espresso martini" wins over "martini".
    """
    lowered = text.lower()
    named: list[str] = []

    for kw in sorted(COCKTAIL_KEYWORDS, key=len, reverse=True):
        if kw in lowered:
            name = COCKTAIL_KEYWORDS[kw]
            if name not in named:
                # Don't let a shorter keyword re-match inside one already consumed
                lowered = lowered.replace(kw, " ")
                named.append(name)

    implied: list[str] = []
    for kw, names in SPIRIT_KEYWORDS.items():
        if kw in lowered:
            for n in names:
                if n not in named and n not in implied:
                    implied.append(n)

    return named, implied


def parse(text: str, *, default_guests: int = 50, default_budget: float | None = None) -> ParsedRequest:
    """
    Extract what we can. Everything not found is recorded in `defaults_used`
    so the interface can tell the person what was assumed.
    """
    result = ParsedRequest()
    text = (text or "").strip()

    result.guests = _find_guests(text)
    if result.guests is None:
        result.guests = default_guests
        result.defaults_used.append(f"guest count not given — assumed {default_guests}")

    result.budget = _find_budget(text)
    if result.budget is None and default_budget is not None:
        result.budget = default_budget
        result.defaults_used.append(f"budget not given — assumed ₪{default_budget:,.0f}")
    elif result.budget is None:
        result.defaults_used.append("no budget given — costs shown without a target")

    result.drinks_per_guest = _find_drinks_per_guest(text)

    result.requested_count = _find_cocktail_count(text)
    # "4 glasses each" is consumption, never a variety count.
    if result.drinks_per_guest is not None and result.requested_count == int(result.drinks_per_guest):
        result.requested_count = None

    named, implied = _find_cocktails(text)
    result.named_cocktails = named
    result.implied_cocktails = implied
    result.requested_cocktails = named + implied
    if named:
        # Only the explicitly named ones are a firm request; spirit matches are
        # suggestions, and the caller may drop them to hit a requested count.
        result.unmatched_terms = []
    if not result.requested_cocktails:
        result.defaults_used.append("no specific drinks named — chose a balanced classic mix")

    return result

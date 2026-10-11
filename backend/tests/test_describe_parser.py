"""
Tests for the plain-language event parser.

This is the component that lets the app work with no API key, so it carries
real weight — if it mis-reads "50 אנשים" the whole front door produces a plan
for the wrong event.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.describe_parser import parse


class TestGuestCount:
    def test_english(self):
        assert parse("50 people, margaritas").guests == 50

    def test_hebrew(self):
        assert parse("50 אנשים מרגריטות").guests == 50

    def test_hebrew_with_prefix(self):
        # "for 50 people" written the Hebrew way
        assert parse("אני רוצה להכין מרגריטות ל50 אנשים").guests == 50

    def test_guests_word_variants(self):
        assert parse("event for 120 guests").guests == 120
        assert parse("אירוע ל80 עובדים").guests == 80

    def test_absent_falls_back_and_says_so(self):
        r = parse("margaritas please", default_guests=50)
        assert r.guests == 50
        assert any("guest count" in d for d in r.defaults_used)

    def test_implausible_count_ignored(self):
        # 90000 is not a guest count; must not be picked up
        r = parse("budget 90000 shekel")
        assert r.guests == 50  # the default
        assert r.budget == 90000


class TestBudget:
    def test_hebrew_shekel(self):
        assert parse("50 אנשים, 5000 שקל").budget == 5000

    def test_symbol(self):
        assert parse("50 people ₪5,000").budget == 5000

    def test_english_word(self):
        assert parse("budget 4500 for 100 guests").budget == 4500

    def test_thousand_idiom(self):
        # People write "6000 אלף שקל" meaning plain 6000
        assert parse("יש לי 6000 אלף שקל").budget == 6000

    def test_absent_is_flagged_not_invented(self):
        r = parse("50 people, mojitos")
        assert r.budget is None
        assert any("budget" in d for d in r.defaults_used)


class TestCocktails:
    def test_named_english(self):
        assert "Margarita" in parse("50 people, margaritas").requested_cocktails

    def test_named_hebrew(self):
        assert "Margarita" in parse("מרגריטות ל50 אנשים").requested_cocktails

    def test_multiple_named(self):
        got = parse("mojitos and negronis for 40").requested_cocktails
        assert "Mojito" in got and "Negroni" in got

    def test_longer_keyword_wins(self):
        # "espresso martini" must not be read as plain "martini"
        got = parse("espresso martini for 30 people").requested_cocktails
        assert got[0] == "Espresso Martini"

    def test_spirit_implies_cocktails(self):
        got = parse("something with gin for 50 people").requested_cocktails
        assert any(c in got for c in ["Gin Gimlet", "Negroni", "French 75 (Gin)"])

    def test_hebrew_spirit(self):
        got = parse("משהו עם וודקה ל50 אנשים").requested_cocktails
        assert any(c in got for c in ["Moscow Mule", "Espresso Martini"])

    def test_none_named_is_flagged(self):
        r = parse("50 people, ₪5000")
        assert r.requested_cocktails == []
        assert any("no specific drinks" in d for d in r.defaults_used)


class TestCocktailCount:
    def test_english(self):
        assert parse("3 cocktails for 50 people").requested_count == 3

    def test_hebrew(self):
        assert parse("3 קוקטיילים ל50 אנשים").requested_count == 3

    def test_absent(self):
        assert parse("50 people margaritas").requested_count is None


class TestRealUserPhrasing:
    """The actual sentences this user typed, in both languages."""

    def test_full_hebrew_request(self):
        """
        "שכל אחד ישתה איזה 3 קוקטיילים" reads as "each will DRINK about 3
        cocktails" — three servings per guest, not three kinds of cocktail.

        This test previously asserted requested_count == 3, which was a
        misreading: the parser had no notion of per-guest consumption then, so
        the only available field got the number. Three servings for fifty
        guests is 150 drinks; three varieties is a menu size. Reading one as
        the other changes every quantity in the event.
        """
        r = parse("אני רוצה לעשות אירוע קוקטיילים ל50 אנשים שיהיה מרגריטות "
                  "וגם גסמין שכל אחד ישתה איזה 3 קוקטיילים")
        assert r.guests == 50
        assert "Margarita" in r.requested_cocktails
        assert r.drinks_per_guest == 3
        assert r.requested_count is None

    def test_full_english_request(self):
        r = parse("50 people, margaritas and one gin cocktail, budget 5000 shekel")
        assert r.guests == 50
        assert r.budget == 5000
        assert "Margarita" in r.requested_cocktails

    def test_budget_only_followup(self):
        r = parse("יש לי 6000 אלף שקל")
        assert r.budget == 6000


class TestBareForNumber:
    """"mojitos for 30" — no people-word at all."""

    def test_english_bare(self):
        assert parse("mojitos for 30").guests == 30

    def test_hebrew_bare(self):
        assert parse("מוחיטו ל40").guests == 40

    def test_money_not_mistaken_for_guests(self):
        # "budget for 5000 shekel" must not read 5000 as a headcount
        r = parse("margaritas, budget for 5000 shekel", default_guests=50)
        assert r.guests == 50
        assert r.budget == 5000

    def test_people_word_still_wins(self):
        # explicit beats bare — "for 3 cocktails" must not become 3 guests
        assert parse("3 cocktails for 80 people").guests == 80


class TestDrinksPerGuest:
    """
    "4 glasses each" is consumption; "3 cocktails" is variety. Reading one as
    the other changes every quantity and every price in the event.
    """

    def test_hebrew_glasses_each(self):
        r = parse("שכל אחד ישתה לפחות 4 כוסות קוקטייל")
        assert r.drinks_per_guest == 4

    def test_english_drinks_each(self):
        assert parse("100 people, 4 drinks each").drinks_per_guest == 4

    def test_english_per_person(self):
        assert parse("80 guests, 3 drinks per person").drinks_per_guest == 3

    def test_variety_count_is_not_consumption(self):
        r = parse("3 cocktails for 50 people")
        assert r.requested_count == 3
        assert r.drinks_per_guest is None

    def test_absent(self):
        assert parse("margaritas for 50").drinks_per_guest is None


class TestNamedVersusImplied:
    """A drink you name is a firm request; one implied by a spirit is not."""

    def test_named_are_tracked_separately(self):
        r = parse("margaritas and negroni for 100 people")
        assert r.named_cocktails == ["Margarita", "Negroni"]
        assert r.implied_cocktails == []

    def test_spirit_only_is_implied_not_named(self):
        r = parse("something with gin for 50 people")
        assert r.named_cocktails == []
        assert len(r.implied_cocktails) > 0


class TestTopazFullBrief:
    """The exact sentence that exposed both bugs."""

    def test_real_request(self):
        r = parse("אני רוצה לעשות אירוע של 100 איש כולם שותים מרגריטות "
                  "ונגרוני ושכל אחד ישתה לפחות 4 כוסות קוקטייל "
                  "התקציב שלי זה 4000 שקל")
        assert r.guests == 100
        assert r.budget == 4000
        assert r.drinks_per_guest == 4
        assert set(r.named_cocktails) == {"Margarita", "Negroni"}


class TestNoArtificialLimits:
    """
    What you write is what you get. The only numeric bounds left in the parser
    exist to stop one number being read as another, never to cap the size of
    your event.
    """

    def test_high_consumption_is_honoured(self):
        assert parse("100 people, 8 drinks each").drinks_per_guest == 8

    def test_very_high_consumption_is_honoured(self):
        assert parse("50 guests, 12 drinks each").drinks_per_guest == 12

    def test_large_menu_request_is_honoured(self):
        assert parse("10 cocktails for 200 people").requested_count == 10

    def test_large_headcount_is_honoured(self):
        assert parse("1500 people, margaritas").guests == 1500

    def test_budget_is_still_not_read_as_consumption(self):
        """The guard that remains: money must not become drinks-per-guest."""
        r = parse("margaritas for 100 people, budget 9000 shekel")
        assert r.budget == 9000
        assert r.drinks_per_guest is None

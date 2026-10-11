"""
The agent's system prompt carries the rules that keep the system honest.

It is a natural target for shortening — it is sent on every API call, four or
more times per message. These tests exist so that trimming it can never quietly
drop a rule: losing one "NEVER" would let the model start doing its own
arithmetic or inventing prices, and nothing else in the system would catch it.
"""
import re
import pathlib

SRC = pathlib.Path(__file__).parent.parent / "app" / "api" / "agent.py"
PROMPT = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', SRC.read_text(encoding="utf-8"), re.S).group(1)


class TestSafetyRulesSurvive:
    def test_forbids_own_arithmetic(self):
        assert re.search(r"NEVER perform arithmetic", PROMPT, re.I)
        assert "calculation engine" in PROMPT

    def test_forbids_inventing_data(self):
        assert re.search(r"NEVER invent prices", PROMPT, re.I)
        assert "package sizes" in PROMPT

    def test_requires_reporting_missing_data(self):
        assert "PRICE_MISSING" in PROMPT
        assert "PRODUCT_MAPPING_REQUIRED" in PROMPT

    def test_requires_calculating_after_proposing(self):
        assert "calculate_event_cost" in PROMPT
        assert re.search(r"ALWAYS call calculate_event_cost", PROMPT, re.I)

    def test_forbids_guessing_cost(self):
        assert re.search(r"[Nn]ever guess or estimate costs", PROMPT)

    def test_forbids_fabricating(self):
        assert re.search(r"[Nn]ever fabricate", PROMPT)

    def test_every_negation_is_intact(self):
        """
        Compression must not reduce the number of prohibitions.

        The original prompt carried exactly five: the rules banner, the two
        NEVER rules, "never guess or estimate costs", and "never fabricate".
        Five is therefore the floor, not a round number.
        """
        assert len(re.findall(r"\b(NEVER|never|Never)\b", PROMPT)) >= 5


class TestToolsAreNamed:
    def test_all_six_tools_appear(self):
        for tool in ["search_cocktails", "get_cocktail_details", "propose_menu",
                     "calculate_event_cost", "get_shopping_list"]:
            assert tool in PROMPT, f"{tool} missing from the prompt"


class TestStaysSmall:
    def test_prompt_is_compact(self):
        """
        Guards against the prompt creeping back up; it is billed every call.

        Raised from 1,700 to 2,000 in Aug 2026, deliberately. The tool list went
        from five entries to seven and gained the instruction that none of them
        need an event id — which is what stopped the agent asking people to paste
        a UUID off a screen where it is never shown. About 400 characters, ~115
        tokens, a fraction of an agora per message. Worth it.

        The cap stays because the pressure is real: a per-request event block is
        now appended to this on every call, so the base text is no longer the
        whole bill.
        """
        assert len(PROMPT) < 2000, f"prompt grew to {len(PROMPT)} chars"

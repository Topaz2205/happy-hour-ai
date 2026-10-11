"""
Tests for the provider abstraction.

The translation between dialects is where a silent bug would hurt most: if a
tool result is attached to the wrong turn, the model sees a conversation that
never happened and answers confidently about nothing. None of this needs a
network — the shapes are the whole contract.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.llm import (
    Message, ToolCall, PRESETS, tools_to_openai, describe_config,
    AnthropicProvider, OpenAICompatProvider,
)

TOOLS = [{
    "name": "search_cocktails",
    "description": "Search the cocktail database.",
    "input_schema": {
        "type": "object",
        "properties": {"theme": {"type": "string"}},
        "required": ["theme"],
    },
}]

CONVERSATION = [
    Message(role="user", content="make it cheaper"),
    Message(role="assistant", content="Looking.", tool_calls=[
        ToolCall(id="t1", name="search_cocktails", arguments={"theme": "classic"}),
    ]),
    Message(role="tool", tool_call_id="t1", content='{"found": 3}'),
]


class TestToolSchemaTranslation:
    def test_openai_nests_under_function(self):
        got = tools_to_openai(TOOLS)[0]
        assert got["type"] == "function"
        assert got["function"]["name"] == "search_cocktails"

    def test_input_schema_becomes_parameters(self):
        """The schema itself must survive intact — required fields included."""
        got = tools_to_openai(TOOLS)[0]["function"]["parameters"]
        assert got == TOOLS[0]["input_schema"]
        assert got["required"] == ["theme"]

    def test_missing_schema_does_not_crash(self):
        got = tools_to_openai([{"name": "ping", "description": "d"}])
        assert got[0]["function"]["parameters"]["type"] == "object"


class TestAnthropicTranslation:
    """Anthropic carries tool results as content blocks on a *user* turn."""

    def _native(self):
        p = AnthropicProvider.__new__(AnthropicProvider)
        return p._to_native(CONVERSATION)

    def test_roles(self):
        assert [m["role"] for m in self._native()] == ["user", "assistant", "user"]

    def test_tool_use_block(self):
        block = self._native()[1]["content"][-1]
        assert block["type"] == "tool_use"
        assert block["id"] == "t1"
        assert block["input"] == {"theme": "classic"}

    def test_tool_result_is_a_user_block(self):
        block = self._native()[2]["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "t1"

    def test_parallel_results_merge_into_one_turn(self):
        """
        Two tools called in one turn produce two results. They must arrive as
        one user message: the API rejects a tool_result that is not answering
        the assistant turn immediately before it, so a second message would be
        refused outright.
        """
        convo = [
            Message(role="user", content="go"),
            Message(role="assistant", tool_calls=[
                ToolCall(id="a", name="search_cocktails", arguments={}),
                ToolCall(id="b", name="search_cocktails", arguments={}),
            ]),
            Message(role="tool", tool_call_id="a", content="{}"),
            Message(role="tool", tool_call_id="b", content="{}"),
        ]
        native = AnthropicProvider.__new__(AnthropicProvider)._to_native(convo)
        assert len(native) == 3
        assert len(native[2]["content"]) == 2

    def test_assistant_turn_is_never_empty(self):
        """An empty content list is rejected; a blank text block is not."""
        convo = [Message(role="assistant", content="")]
        native = AnthropicProvider.__new__(AnthropicProvider)._to_native(convo)
        assert native[0]["content"]


class TestOpenAITranslation:
    """OpenAI carries tool results on their own `tool` role."""

    def _native(self):
        p = OpenAICompatProvider.__new__(OpenAICompatProvider)
        return p._to_native("SYS", CONVERSATION)

    def test_system_is_the_first_message(self):
        assert self._native()[0] == {"role": "system", "content": "SYS"}

    def test_roles(self):
        assert [m["role"] for m in self._native()] == \
            ["system", "user", "assistant", "tool"]

    def test_arguments_are_json_encoded(self):
        """OpenAI takes arguments as a string; Anthropic takes an object."""
        call = self._native()[2]["tool_calls"][0]
        assert isinstance(call["function"]["arguments"], str)
        assert json.loads(call["function"]["arguments"]) == {"theme": "classic"}

    def test_tool_result_keeps_its_id(self):
        assert self._native()[3]["tool_call_id"] == "t1"

    def test_ids_match_across_both_dialects(self):
        """
        The id is what links a result to its call. If the two adapters disagreed
        the model would be answered about a call it never made.
        """
        a = AnthropicProvider.__new__(AnthropicProvider)._to_native(CONVERSATION)
        o = OpenAICompatProvider.__new__(OpenAICompatProvider)._to_native("S", CONVERSATION)
        assert a[1]["content"][-1]["id"] == o[2]["tool_calls"][0]["id"] == "t1"
        assert a[2]["content"][0]["tool_use_id"] == o[3]["tool_call_id"] == "t1"


class TestConfigValidation:
    """Problems are caught before a network call, so they read as setup steps."""

    def test_missing_key_names_the_provider_and_where_to_get_one(self):
        msg = describe_config("groq", "", "m")
        assert "Groq" in msg and "console.groq.com" in msg

    def test_placeholder_is_recognised(self):
        assert "placeholder" in describe_config("groq", "REPLACE-ME", "m").lower()

    def test_wrong_prefix_for_anthropic(self):
        assert "sk-ant-" in describe_config("anthropic", "gsk_abc123", "m")

    def test_unknown_provider_lists_the_valid_ones(self):
        msg = describe_config("hal9000", "k", "m")
        assert "groq" in msg and "anthropic" in msg

    def test_a_good_config_has_no_complaint(self):
        assert describe_config("groq", "gsk_realkey", "openai/gpt-oss-120b") is None

    def test_gemini_key_has_no_prefix_rule(self):
        """Gemini keys have no stable prefix — better unchecked than checked wrongly."""
        assert describe_config("gemini", "AIzaSyExample", "gemini-2.0-flash") is None


class TestPresets:
    def test_every_preset_is_complete(self):
        for name, p in PRESETS.items():
            for field in ("label", "base_url", "default_model", "keys_url", "note"):
                assert field in p, f"{name} is missing {field}"

    def test_anthropic_alone_has_no_base_url(self):
        """It uses its own SDK; the others share the OpenAI-compatible path."""
        assert PRESETS["anthropic"]["base_url"] == ""
        assert all(p["base_url"].startswith("https://")
                   for n, p in PRESETS.items() if n != "anthropic")


class TestToolFailureIsRecoverable:
    """
    A model that gets a tool's arguments wrong must be told so, not crash the
    request. Smaller free-tier models do this often enough that the difference
    decides whether the agent panel is usable on them at all.
    """

    def test_dispatch_returns_the_error_to_the_model(self):
        import asyncio
        from unittest.mock import AsyncMock
        from app.api.agent import dispatch_tool

        db = AsyncMock()
        # get_cocktail_details requires cocktail_ids; send nothing and watch it cope.
        #
        # This probed get_event_details until Aug 2026, when that tool stopped
        # taking an event id at all — the event is bound by the request, and
        # asking the model for a UUID it could not know was itself the bug. The
        # test now uses a tool that still has a genuinely required argument,
        # because the behaviour being checked is recovery, not that particular
        # tool.
        out = asyncio.run(dispatch_tool("get_cocktail_details", {}, None, db))

        assert isinstance(out, dict) and "error" in out
        assert "KeyError" in out["error"]
        assert out["tool"] == "get_cocktail_details"
        assert out["arguments_received"] == {}
        # The transaction is rolled back, or every later query on this session
        # fails with "current transaction is aborted".
        db.rollback.assert_awaited_once()

    def test_unknown_tool_is_reported_not_raised(self):
        import asyncio
        from unittest.mock import AsyncMock
        from app.api.agent import dispatch_tool

        out = asyncio.run(dispatch_tool("make_me_a_sandwich", {}, None, AsyncMock()))
        assert "Unknown tool" in out["error"]

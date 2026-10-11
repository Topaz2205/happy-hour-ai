"""
One conversation format, several providers behind it.

WHY
---
The agent needs a model that can call tools. Anthropic's own models are the
best at it, but a Console account with no credits cannot call them at all, and
"buy credits before you can see whether this works" is a bad first experience
for something that is otherwise fully functional offline.

Several providers expose an OpenAI-compatible endpoint with a usable free
tier — Groq, Google's Gemini, OpenRouter — and they speak a different dialect
of the same idea. Rather than fork the agent loop per provider, the loop speaks
one neutral format and an adapter translates at the edge.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No model names are hardcoded as defaults beyond one per provider, and none of
them are load-bearing: the model string comes from .env. Provider catalogues
change every few months, and a list baked into this file would quietly rot
into a wrong recommendation. `scripts/check_llm.py` asks the provider what it
actually offers, which is the only answer that stays true.

The choice of provider changes nothing about correctness. The model picks
cocktails and calls tools; every quantity and every price is computed by
app/engine/calculator.py. A weaker model can choose a duller menu — it cannot
produce a wrong number, because it is never the thing doing arithmetic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

# ── Neutral conversation format ───────────────────────────────────────────────


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Message:
    """
    role="user"       → content is the person's text
    role="assistant"  → content is the model's text; tool_calls may be present
    role="tool"       → content is the JSON result; tool_call_id links it back
    """
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str


class LLMError(Exception):
    """
    A provider failure already phrased for the person reading it.

    `status` is what the HTTP layer should return: 503 for "not configured or
    upstream is unhappy", 429 for rate limits. The agent endpoint re-raises it
    as an HTTPException without having to know which provider produced it.
    """

    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.message = message
        self.status = status


# ── Provider presets ──────────────────────────────────────────────────────────
#
# Base URLs only. These are the providers' documented OpenAI-compatible
# endpoints and they change far more slowly than model catalogues do.

PRESETS: dict[str, dict[str, str]] = {
    "anthropic": {
        "label": "Anthropic",
        "base_url": "",  # native SDK, not OpenAI-compatible
        "default_model": "claude-sonnet-5",
        "keys_url": "https://console.anthropic.com/settings/keys",
        "note": "Best tool-calling. Needs credits on the account.",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "openai/gpt-oss-120b",
        "keys_url": "https://console.groq.com/keys",
        "note": "Free tier, no card. Very fast. Rate-limited per minute.",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "keys_url": "https://aistudio.google.com/apikey",
        "note": "Free tier. Generous daily allowance.",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "keys_url": "https://openrouter.ai/keys",
        "note": "Many models behind one key; some are free.",
    },
}


# ── Tool schema translation ───────────────────────────────────────────────────
#
# The tools are declared once, in Anthropic's shape (app/api/agent.py). The two
# dialects differ only in nesting and in the name of the schema field.


def tools_to_openai(tools: list[dict]) -> list[dict]:
    """Anthropic tool declarations → OpenAI `function` declarations."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Already in Anthropic shape; returned as-is so callers can be uniform."""
    return tools


# ── Anthropic adapter ─────────────────────────────────────────────────────────


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        import anthropic

        self._sdk = anthropic
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.AsyncAnthropic(**kwargs)
        self.model = model

    def _to_native(self, messages: list[Message]) -> list[dict]:
        """
        Neutral → Anthropic. Tool results are user-turn content blocks here, and
        consecutive results must be merged into one message rather than sent as
        several — the API rejects a tool_result that is not answering the
        assistant turn immediately before it.
        """
        out: list[dict] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                blocks: list[dict] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append({
                        "type": "tool_use", "id": tc.id,
                        "name": tc.name, "input": tc.arguments,
                    })
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            else:  # tool
                block = {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": m.content,
                }
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    async def chat(self, system: str, messages: list[Message],
                   tools: list[dict], max_tokens: int = 4096) -> Reply:
        anthropic = self._sdk
        try:
            res = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                tools=tools_to_anthropic(tools),
                messages=self._to_native(messages),
            )
        except anthropic.AuthenticationError:
            raise LLMError(
                "Anthropic rejected the API key in backend/.env. Check it at "
                "console.anthropic.com/settings/keys, then restart the API."
            )
        except anthropic.PermissionDeniedError:
            raise LLMError("This Anthropic API key isn't allowed to use the Messages API.")
        except anthropic.RateLimitError:
            raise LLMError("Anthropic rate limit reached. Wait a moment and try again.", 429)
        except anthropic.NotFoundError:
            raise LLMError(
                f"Model '{self.model}' is not available to this API key. "
                f"Set LLM_MODEL in backend/.env to one your account can use."
            )
        except anthropic.APIConnectionError:
            raise LLMError("Could not reach the Anthropic API. Check your internet connection.")
        except anthropic.APIStatusError as e:
            raise LLMError(_upstream_message("Anthropic", e))

        text, calls = "", []
        for block in res.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
        return Reply(text=text, tool_calls=calls, stop_reason=res.stop_reason or "end_turn")


# ── OpenAI-compatible adapter ─────────────────────────────────────────────────


class OpenAICompatProvider:
    """Groq, Gemini, OpenRouter, Together, a local server — same wire format."""

    def __init__(self, api_key: str, model: str, base_url: str, name: str = "openai"):
        try:
            import openai
        except ModuleNotFoundError:
            raise LLMError(
                "The 'openai' package is needed for this provider. Install it with:\n"
                "  cd backend && source venv/bin/activate && pip install openai"
            )
        self._sdk = openai
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self.model = model
        self.name = name

    def _to_native(self, system: str, messages: list[Message]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                msg: dict[str, Any] = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name,
                                         "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in m.tool_calls
                    ]
                out.append(msg)
            else:  # tool
                out.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                })
        return out

    async def chat(self, system: str, messages: list[Message],
                   tools: list[dict], max_tokens: int = 4096) -> Reply:
        openai = self._sdk
        label = PRESETS.get(self.name, {}).get("label", self.name)
        try:
            res = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=self._to_native(system, messages),
                tools=tools_to_openai(tools),
            )
        except openai.AuthenticationError:
            raise LLMError(
                f"{label} rejected the API key in backend/.env. "
                f"Check LLM_API_KEY, then restart the API."
            )
        except openai.PermissionDeniedError:
            raise LLMError(f"This {label} key isn't allowed to use that model.")
        except openai.RateLimitError:
            raise LLMError(
                f"{label} rate limit reached. Free tiers allow a limited number of "
                f"requests per minute — wait a moment and try again.", 429
            )
        except openai.NotFoundError:
            raise LLMError(
                f"Model '{self.model}' is not available on {label}. "
                f"Run 'python scripts/check_llm.py' to see what your key can reach."
            )
        except openai.APIConnectionError:
            raise LLMError(f"Could not reach {label}. Check your internet connection.")
        except openai.APIStatusError as e:
            raise LLMError(_upstream_message(label, e))

        choice = res.choices[0]
        msg = choice.message
        calls = []
        for tc in (msg.tool_calls or []):
            # A model can emit malformed JSON arguments. Failing the whole
            # request over it hides which tool misfired, so surface the name.
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                raise LLMError(
                    f"{label} returned arguments for '{tc.function.name}' that "
                    f"were not valid JSON. Try a different LLM_MODEL — smaller "
                    f"models sometimes malform tool calls."
                )
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=arguments))

        stop = "tool_use" if calls else "end_turn"
        return Reply(text=msg.content or "", tool_calls=calls, stop_reason=stop)


def _upstream_message(label: str, e: Any) -> str:
    """
    Pass the provider's own wording through. It is usually the most useful thing
    available — a fresh account with no credits says "your credit balance is too
    low", which no generic message of ours would ever say.
    """
    upstream = ""
    try:
        body = e.response.json()
        upstream = (body.get("error") or {}).get("message", "")
    except Exception:
        upstream = str(e)
    status = getattr(e, "status_code", "?")
    return (f"{label} API error ({status}): {upstream}" if upstream
            else f"{label} API error ({status}). Try again shortly.")


# ── Factory ───────────────────────────────────────────────────────────────────

_PLACEHOLDER_MARKERS = ("replace", "your-key", "xxx", "placeholder", "changeme")


def describe_config(provider: str, api_key: str, model: str) -> str | None:
    """
    Return why the configuration is unusable, or None if it looks fine.

    Checked before any network call so a missing key reads as "you haven't set
    this up yet" instead of an opaque 401 from a server.
    """
    if provider not in PRESETS:
        known = ", ".join(PRESETS)
        return f"LLM_PROVIDER='{provider}' is not one of: {known}."
    if not api_key or not api_key.strip():
        url = PRESETS[provider]["keys_url"]
        return (f"No API key is set for {PRESETS[provider]['label']}. Run "
                f"'bash set-key.sh' to add one — get it from {url}")
    k = api_key.strip()
    if any(m in k.lower() for m in _PLACEHOLDER_MARKERS):
        return ("The API key in backend/.env is still a placeholder. "
                "Run 'bash set-key.sh' to set a real one.")
    if provider == "anthropic" and not k.startswith("sk-ant-"):
        return "The Anthropic key doesn't look right — it should start with 'sk-ant-'."
    if not model or not model.strip():
        return "LLM_MODEL is empty in backend/.env."
    return None


def build_provider(provider: str, api_key: str, model: str, base_url: str = ""):
    """Construct the adapter for a provider name. Raises LLMError if unusable."""
    problem = describe_config(provider, api_key, model)
    if problem:
        raise LLMError(problem)
    preset = PRESETS[provider]
    url = base_url or preset["base_url"]
    if provider == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model, base_url=url)
    return OpenAICompatProvider(api_key=api_key, model=model, base_url=url, name=provider)

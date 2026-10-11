"""
Ask the configured provider what it can actually do, with the key you have.

Model catalogues change every few months, so any list written into this project
would eventually be wrong. This asks the provider directly and then proves the
answer by making a real tool call — the one thing the agent depends on and the
thing most likely to be missing from a smaller free model.

    python scripts/check_llm.py            # check the configured provider
    python scripts/check_llm.py --models   # also list every model it offers
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.llm import (
    PRESETS, build_provider, describe_config, LLMError, Message,
)

# A tool the model cannot answer from memory, so calling it is the only way to
# produce a number. If it replies without calling, tool use is not working.
PROBE_TOOL = [{
    "name": "get_bottle_size_ml",
    "description": "Return the size in millilitres of a bottle in the inventory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "The product to look up"},
        },
        "required": ["product_name"],
    },
}]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", action="store_true", help="list every model offered")
    args = ap.parse_args()

    provider = settings.LLM_PROVIDER
    key = settings.resolved_llm_key
    model = settings.resolved_llm_model
    label = PRESETS.get(provider, {}).get("label", provider)

    print(f"Provider  {label}  ({provider})")
    print(f"Model     {model or '(none set)'}")
    print(f"Key       {'set, ' + str(len(key)) + ' chars' if key else 'NOT SET'}")
    print()

    problem = describe_config(provider, key, model)
    if problem:
        print(f"✗ {problem}")
        return 1

    try:
        llm = build_provider(provider, key, model, settings.LLM_BASE_URL)
    except LLMError as e:
        print(f"✗ {e.message}")
        return 1

    if args.models and hasattr(llm, "client") and provider != "anthropic":
        try:
            listing = await llm.client.models.list()
            names = sorted(m.id for m in listing.data)
            print(f"Models this key can reach ({len(names)}):")
            for n in names:
                print(f"  {'→' if n == model else ' '} {n}")
            print()
        except Exception as e:
            print(f"  (could not list models: {e})\n")

    print("Testing a real tool call…")
    try:
        reply = await llm.chat(
            system=("You look things up with tools. You do not know bottle sizes "
                    "from memory — always call the tool."),
            messages=[Message(role="user",
                              content="How many millilitres are in our bottle of Olmeca Tequila?")],
            tools=PROBE_TOOL,
            max_tokens=512,
        )
    except LLMError as e:
        print(f"✗ {e.message}")
        return 1

    if reply.tool_calls:
        tc = reply.tool_calls[0]
        print(f"✓ Tool calling works — called {tc.name}({tc.arguments})")
        print(f"\n✓ {label} is ready. The agent panel will work.")
        return 0

    print("✗ The model replied without calling the tool:")
    print(f"    {reply.text[:200]}")
    print("\n  This model can chat but is not reliably using tools, so the agent")
    print("  panel would not be able to change your event. Pick another model:")
    print("    python scripts/check_llm.py --models")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.ai_rate_limit import enforce_ai_rate_limit
from app.db.session import get_db
from app.models import Cocktail
from app.services.llm import Message, OpenAICompatProvider, PRESETS


router = APIRouter()


class BuilderTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2500)


class BuilderRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2500)
    draft: dict[str, Any] = Field(default_factory=dict)
    history: list[BuilderTurn] = Field(default_factory=list)


class BuilderUpdates(BaseModel):
    name: str | None = None
    company_name: str | None = None
    event_type: str | None = None
    event_date: str | None = None
    location: str | None = None

    guest_count: int | None = Field(None, ge=1, le=100000)
    budget: float | None = Field(None, ge=0)

    duration_hours: float | None = Field(None, ge=0.5, le=48)
    cocktail_count: int | None = Field(None, ge=1, le=12)

    expected_drinks_per_guest: float | None = Field(
        None,
        ge=0.5,
        le=50,
    )

    non_alcoholic_pct: float | None = Field(
        None,
        ge=0,
        le=1,
    )

    preferences: str | None = None


def extract_json(text: str) -> dict:
    cleaned = (text or "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("The model did not return JSON")

    return json.loads(cleaned[start : end + 1])


@router.post("/advice")
async def event_builder_advice(
    body: BuilderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    enforce_ai_rate_limit(request)

    provider_name = settings.LLM_PROVIDER

    if provider_name == "anthropic":
        raise HTTPException(
            status_code=503,
            detail=(
                "The pre-event coach currently uses the "
                "OpenAI-compatible provider path. "
                "Set LLM_PROVIDER to groq, gemini or openrouter."
            ),
        )

    preset = PRESETS.get(provider_name)

    if not preset:
        raise HTTPException(
            status_code=503,
            detail=f"Unknown AI provider: {provider_name}",
        )

    api_key = settings.resolved_llm_key

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="No LLM API key is configured.",
        )

    result = await db.execute(
        select(Cocktail)
        .where(Cocktail.active == True)
        .order_by(Cocktail.name)
    )

    cocktails = result.scalars().all()

    library = [
        {
            "name": c.name,
            "theme": getattr(c, "theme", None),
            "garnish": getattr(c, "garnish", None),
            "has_non_alcoholic_variant": bool(
                getattr(c, "non_alc_variant", None)
            ),
            "taste_profile": c.taste_profile or {},
            "style_tags": c.style_tags or [],
            "strength": c.strength,
            "base_spirit": c.base_spirit,
        }
        for c in cocktails
    ]

    system = f"""
You are Happy Hour AI, an expert event-planning assistant.

You are working BEFORE an Event record is created.

Your role is similar to an in-product guided coach:
help the user make the important decisions,
ask useful questions,
spot problematic choices,
and recommend a cocktail menu.

LANGUAGE
- Understand Hebrew and English.
- Reply in the language of the user's latest real message.
- Hebrew should sound natural, not translated.
- Cocktail names stay exactly as they appear in the library.

IMPORTANT RULES
- Do NOT create an event.
- Do NOT claim that you changed anything.
- You can only SUGGEST changes to the draft.
- The user must approve suggested changes in the UI.
- Do not calculate bottle quantities or final costs.
- Python will do all final quantities and costing after creation.
- Do not promise that a budget will definitely be enough.
- You may explain whether a setup seems simple, complex,
  premium, conservative, etc.
- Ask one useful question at a time when critical information
  is missing.
- Do not interrogate the user when enough information exists.

MENU
- Recommend cocktails ONLY from AVAILABLE COCKTAILS.
- recommended_cocktails must contain the exact database names.
- Never invent a cocktail name.

COCKTAIL METADATA
Every cocktail may include:

taste_profile:
- sweet: 0-5
- sour: 0-5
- bitter: 0-5
- salty: 0-5
- umami: 0-5
- spicy: 0-5

strength:
- 1 = very light
- 5 = very strong / spirit-forward

style_tags may include concepts such as:
refreshing, summer, fizzy, citrusy, herbal, minty,
rich, dry, classic, easy_drinking, spirit_forward,
dessert, coffee, elegant, celebration and others.

base_spirit identifies the main alcohol family.

USE THE METADATA AS THE SOURCE OF TRUTH
when matching the user's taste preferences.

Examples:
- "חמוץ" / "sour" -> prefer a high sour score.
- "מתוק" / "sweet" -> prefer a high sweet score.
- "לא מתוק" / "not sweet" -> prefer a low sweet score.
- "מר" / "bitter" -> prefer a high bitter score.
- "חריף" / "spicy" -> prefer a high spicy score.
- "מרענן" / "refreshing" -> prefer refreshing.
- "קיצי" / "summer" -> prefer summer and refreshing.
- "קליל" / "light" -> prefer lower strength and easy_drinking.
- "חזק" / "strong" -> prefer higher strength or spirit_forward.
- "הדרי" / "citrusy" -> prefer citrusy.
- "צמחי" / "herbal" -> prefer herbal.

EXCLUSIONS ARE HARD CONSTRAINTS.
If the user says:
- no tequila / בלי טקילה
- no gin / בלי ג׳ין
- no rum / בלי רום
- no vodka / בלי וודקה
- no whiskey / בלי וויסקי

do NOT recommend cocktails whose base_spirit violates that exclusion.

When several cocktails fit, prefer a varied menu:
- avoid using the same base spirit for every cocktail when possible
- include different drinking experiences
- respect the user's requested cocktail count

Do not choose a famous cocktail merely because it is popular.
Choose the cocktails whose metadata best matches the user's request.

FIELD UPDATES
You may suggest values for:
name
company_name
event_type
event_date
location
guest_count
budget
duration_hours
cocktail_count
expected_drinks_per_guest
non_alcoholic_pct
preferences

non_alcoholic_pct MUST be a decimal between 0 and 1.
Example: 20% = 0.20.

Only suggest a field update when it is useful.
Do not overwrite information for no reason.

CURRENT DRAFT
{json.dumps(body.draft, ensure_ascii=False)}

AVAILABLE COCKTAILS
{json.dumps(library, ensure_ascii=False)}

Return ONLY valid JSON in this exact structure:

{{
  "message": "natural helpful answer to the user",
  "updates": {{}},
  "recommended_cocktails": [],
  "ready_to_create": false
}}

If you recommend a final menu, put the exact cocktail names
inside recommended_cocktails.
"""

    provider = OpenAICompatProvider(
        api_key=api_key,
        model=settings.resolved_llm_model,
        base_url=preset["base_url"],
        name=provider_name,
    )

    messages = [
        Message(
            role=item.role,
            content=item.content,
        )
        for item in body.history[-8:]
    ]

    messages.append(
        Message(
            role="user",
            content=body.message,
        )
    )

    try:
        reply = await provider.chat(
            system=system,
            messages=messages,
            tools=[],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Happy Hour AI could not respond: {exc}",
        )

    try:
        data = extract_json(reply.text)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Happy Hour AI returned an invalid response.",
        )

    try:
        updates = BuilderUpdates(
            **(data.get("updates") or {})
        ).model_dump(exclude_none=True)
    except Exception:
        updates = {}

    canonical_names = {
        c.name.strip().lower(): c.name
        for c in cocktails
    }

    recommended = []
    seen = set()

    for raw_name in data.get(
        "recommended_cocktails",
        [],
    ):
        if not isinstance(raw_name, str):
            continue

        canonical = canonical_names.get(
            raw_name.strip().lower()
        )

        if canonical and canonical not in seen:
            recommended.append(canonical)
            seen.add(canonical)

    try:
        target_count = int(
            updates.get(
                "cocktail_count",
                body.draft.get(
                    "cocktail_count",
                    3,
                ),
            )
        )
    except Exception:
        target_count = 3

    target_count = max(1, min(target_count, 12))

    recommended = recommended[:target_count]

    return {
        "message": str(
            data.get("message")
            or "I’m ready to help plan the event."
        ),
        "updates": updates,
        "recommended_cocktails": recommended,
        "ready_to_create": bool(
            data.get("ready_to_create")
        ),
        "provider": provider_name,
        "model": settings.resolved_llm_model,
    }

"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Check,
  ChevronLeft,
  CircleHelp,
  GlassWater,
  Sparkles,
} from "lucide-react";

import { api } from "@/lib/api";

type FormState = {
  name: string;
  company_name: string;
  event_type: string;
  event_date: string;
  location: string;
  guest_count: string;
  budget: string;
  duration_hours: string;
  expected_drinks_per_guest: string;
  cocktail_count: string;
  non_alcoholic_pct: string;
  preferences: string;
};

type FormKey = keyof FormState;

type Turn = {
  role: "user" | "assistant";
  content: string;
};

type Advice = {
  message: string;
  updates: Record<string, string | number>;
  recommended_cocktails: string[];
};

type Step = {
  key: FormKey;
  title: string;
  question: string;
  tip: string;
  example?: string;
  placeholder?: string;
  required?: boolean;
  type: "text" | "number" | "date" | "select" | "textarea";
  options?: { value: string; label: string }[];
  helpPrompt: string;
};

const STEPS: Step[] = [
  {
    key: "name",
    title: "Event name",
    question: "What should we call this event?",
    tip: "Choose a name you will easily recognize later. If you are not sure, you can skip this and we will create a name automatically.",
    example: "Example: Wix Summer Happy Hour",
    placeholder: "Company Summer Happy Hour",
    type: "text",
    helpPrompt:
      "Help me choose a short, clear event name from the information already in my form. Suggest one value for the name field.",
  },
  {
    key: "company_name",
    title: "Company",
    question: "Is this event for a company or client?",
    tip: "Add the company or client name if relevant. This field is optional.",
    example: "Example: Monday.com",
    placeholder: "Company name",
    type: "text",
    helpPrompt:
      "Help me decide what to enter in the company field. If the existing form contains enough context, suggest one company_name value. Otherwise explain that I can skip it.",
  },
  {
    key: "event_type",
    title: "Event type",
    question: "What kind of event is this?",
    tip: "The event type gives the AI context about the atmosphere and the kind of cocktail menu that fits.",
    type: "select",
    options: [
      { value: "corporate", label: "Corporate happy hour" },
      { value: "wedding", label: "Wedding" },
      { value: "private", label: "Private party" },
      { value: "rooftop", label: "Rooftop event" },
      { value: "launch", label: "Company / product launch" },
      { value: "other", label: "Other" },
    ],
    helpPrompt:
      "Based on the information already in my form, recommend the best event_type. Suggest one valid event_type value.",
  },
  {
    key: "event_date",
    title: "Event date",
    question: "When is the event?",
    tip: "The date helps with preparation and purchasing later. If it is not confirmed yet, you can skip it.",
    type: "date",
    helpPrompt:
      "I am filling the event date. Explain briefly whether the date matters for planning. Do not ask me unrelated questions.",
  },
  {
    key: "location",
    title: "Location",
    question: "Where will the event take place?",
    tip: "A useful location can be a city, office, rooftop or venue. It may affect logistics and supplier choices later.",
    example: "Example: Tel Aviv office rooftop",
    placeholder: "Tel Aviv",
    type: "text",
    helpPrompt:
      "Help me fill the location field. Explain what level of location detail is useful for cocktail event planning.",
  },
  {
    key: "guest_count",
    title: "Guests",
    question: "How many people do you realistically expect to attend?",
    tip: "Plan for expected attendance, not necessarily everyone who was invited.",
    example:
      "If 120 were invited but you expect around 100 to attend, enter 100.",
    placeholder: "e.g. 80",
    required: true,
    type: "number",
    helpPrompt:
      "Help me estimate a realistic guest_count. Use the information already in my form. Ask at most one relevant question if truly necessary. Do not ask about venue capacity unless I specifically mention a capacity limitation. When possible, suggest one numeric guest_count.",
  },
  {
    key: "budget",
    title: "Budget",
    question: "What budget do you want to allocate to the cocktail bar?",
    tip: "This is the purchasing budget. The AI can help judge the direction, but final costs will always come from the deterministic calculation engine.",
    example: "Example: ₪5,000",
    placeholder: "e.g. 5000",
    required: true,
    type: "number",
    helpPrompt:
      "Help me choose a reasonable budget based on my current guest count, duration and event type. Do not invent a final calculated cost. Suggest a budget value only as planning guidance.",
  },
  {
    key: "duration_hours",
    title: "Duration",
    question: "How long will the event last?",
    tip: "Duration affects expected drinking volume. A normal office happy hour is often around 2–3 hours.",
    example: "2.5 hours is a useful starting point for many company events.",
    type: "select",
    options: [
      { value: "1.5", label: "1.5 hours" },
      { value: "2", label: "2 hours" },
      { value: "2.5", label: "2.5 hours" },
      { value: "3", label: "3 hours" },
      { value: "3.5", label: "3.5 hours" },
      { value: "4", label: "4 hours" },
    ],
    helpPrompt:
      "Recommend an appropriate duration_hours value based on my event type and current form. Briefly explain why.",
  },
  {
    key: "expected_drinks_per_guest",
    title: "Drinks per guest",
    question: "How much drinking should we plan for?",
    tip: "This is an average used for quantity planning, not a limit for each person.",
    example:
      "1.5 = light · 2–2.5 = normal happy hour · 3+ = higher consumption",
    type: "select",
    options: [
      { value: "1.5", label: "1.5 — Light" },
      { value: "2", label: "2 — Moderate" },
      { value: "2.5", label: "2.5 — Recommended" },
      { value: "3", label: "3 — Social" },
      { value: "3.5", label: "3.5 — Generous" },
    ],
    helpPrompt:
      "Recommend expected_drinks_per_guest based on the guest count, event type and duration in my current form. Suggest one valid numeric value.",
  },
  {
    key: "cocktail_count",
    title: "Number of cocktails",
    question: "How many cocktails should be on the menu?",
    tip: "More cocktails add variety, but also split demand across more ingredients and products.",
    example:
      "For many office events, 2–4 cocktails is a practical range.",
    type: "select",
    options: [
      { value: "1", label: "1 cocktail" },
      { value: "2", label: "2 cocktails" },
      { value: "3", label: "3 cocktails" },
      { value: "4", label: "4 cocktails" },
      { value: "5", label: "5 cocktails" },
      { value: "6", label: "6 cocktails" },
    ],
    helpPrompt:
      "Recommend cocktail_count using my guest count, budget, event type and duration. Suggest one value between 1 and 6 and briefly explain why.",
  },
  {
    key: "non_alcoholic_pct",
    title: "Non-alcoholic share",
    question: "How much of the drink plan should be non-alcoholic?",
    tip: "This is the share of total planned drinks, not necessarily the percentage of guests who never drink alcohol.",
    example: "20% means roughly one in five planned drinks is non-alcoholic.",
    type: "select",
    options: [
      { value: "0.10", label: "10%" },
      { value: "0.20", label: "20%" },
      { value: "0.25", label: "25%" },
      { value: "0.30", label: "30%" },
      { value: "0.40", label: "40%" },
    ],
    helpPrompt:
      "Recommend a sensible non_alcoholic_pct for this event. Suggest one of 0.10, 0.20, 0.25, 0.30 or 0.40.",
  },
  {
    key: "preferences",
    title: "Cocktail style",
    question: "What should the cocktail menu feel like?",
    tip: "Write naturally. Tell the AI what you like, dislike or want to avoid.",
    example:
      "קיצי, חמוץ, לא מתוק, בלי טקילה, שיהיה משהו אחד עם אפרול",
    placeholder:
      "Refreshing, sour, not too sweet, no tequila… אפשר גם בעברית",
    type: "textarea",
    helpPrompt:
      "Help me define useful cocktail preferences for this event. Ask one short question if needed. You may suggest a preferences value I can apply to the form.",
  },
];

const inputClass =
  "w-full rounded-xl border border-line bg-surface px-4 py-3 text-[14px] " +
  "text-ink outline-none placeholder:text-ink-4 focus:border-accent " +
  "focus:ring-2 focus:ring-accent-soft transition-all";

export default function NewEventPage() {
  const router = useRouter();

  const [form, setForm] = useState<FormState>({
    name: "",
    company_name: "",
    event_type: "corporate",
    event_date: "",
    location: "",
    guest_count: "",
    budget: "",
    duration_hours: "2.5",
    expected_drinks_per_guest: "2.5",
    cocktail_count: "3",
    non_alcoholic_pct: "0.20",
    preferences: "",
  });

  const [stepIndex, setStepIndex] = useState(0);
  const [conversations, setConversations] = useState<Record<string, Turn[]>>({});
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [menuCocktails, setMenuCocktails] = useState<string[]>([]);
  const [menuBusy, setMenuBusy] = useState(false);
  const [error, setError] = useState("");
  const [stepError, setStepError] = useState("");
  const [creating, setCreating] = useState(false);
  const [creatingStage, setCreatingStage] = useState("");

  const cocktailTarget = Math.max(
    1,
    Math.min(Number(form.cocktail_count) || 3, 6)
  );

  const menuStartIndex = STEPS.length;
  const finalReviewIndex = STEPS.length + cocktailTarget;

  const isFieldStep = stepIndex < STEPS.length;
  const isMenuReview =
    stepIndex >= menuStartIndex &&
    stepIndex < finalReviewIndex;
  const isReview = stepIndex === finalReviewIndex;

  const menuIndex = isMenuReview
    ? stepIndex - menuStartIndex
    : -1;

  const current = isFieldStep
    ? STEPS[stepIndex]
    : null;

  const currentCocktail =
    isMenuReview && menuIndex >= 0
      ? menuCocktails[menuIndex]
      : undefined;

  const totalSteps =
    STEPS.length + cocktailTarget + 1;

  const conversationKey = isReview
    ? "review"
    : isMenuReview
      ? `cocktail-${menuIndex}`
      : current?.key ?? "unknown";

  const turns = conversations[conversationKey] ?? [];

  function saveTurns(key: string, nextTurns: Turn[]) {
    setConversations((existing) => ({
      ...existing,
      [key]: nextTurns,
    }));
  }

  function update(key: FormKey, value: string) {
    setForm((currentForm) => ({
      ...currentForm,
      [key]: value,
    }));
    setStepError("");
  }

  function valueFor(step: Step) {
    const value = form[step.key];

    if (step.type === "select") {
      return (
        step.options?.find((option) => option.value === value)?.label ??
        value
      );
    }

    return value || "—";
  }

  function validateCurrent() {
    if (!current) return true;

    const value = form[current.key].trim();

    if (!current.required) return true;

    if (!value) {
      setStepError(`Please fill in ${current.title.toLowerCase()}.`);
      return false;
    }

    if (current.key === "guest_count" && Number(value) <= 0) {
      setStepError("Guest count must be at least 1.");
      return false;
    }

    if (current.key === "budget" && Number(value) < 0) {
      setStepError("Budget cannot be negative.");
      return false;
    }

    return true;
  }

  async function nextStep() {
    if (menuBusy) return;
    if (!validateCurrent()) return;

    setStepError("");
    setAdvice(null);
    setText("");

    if (current?.key === "preferences") {
      setMenuBusy(true);
      setError("");

      try {
        const recommended = await getFinalMenu();

        setMenuCocktails(recommended);
        setStepIndex(menuStartIndex);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Happy Hour AI could not build the cocktail menu."
        );
      } finally {
        setMenuBusy(false);
      }

      return;
    }

    setStepIndex((index) =>
      Math.min(index + 1, STEPS.length - 1)
    );
  }

  function previousStep() {
    setStepError("");
    setAdvice(null);
    setText("");
    setStepIndex((index) => Math.max(index - 1, 0));
  }

  function goToStep(index: number) {
    setStepError("");
    setAdvice(null);
    setText("");
    setStepIndex(index);
  }

  async function send(message?: string, displayMessage?: string) {
    const userMessage = (message ?? text).trim();

    if (!userMessage || busy) return;

    const visibleMessage = displayMessage ?? userMessage;

    const nextTurns: Turn[] = [
      ...turns,
      {
        role: "user",
        content: visibleMessage,
      },
    ];

    saveTurns(conversationKey, nextTurns);
    setText("");
    setBusy(true);
    setError("");

    const focusText = isReview
      ? `
CURRENT TASK: REVIEW
Help the user review the whole event setup.
Do not move to a different workflow.
`
      : isMenuReview
        ? `
CURRENT TASK: COCKTAIL REVIEW

Current cocktail:
${currentCocktail}

Current proposed menu:
${menuCocktails.join(", ")}

User preferences:
${form.preferences || "No explicit preferences"}

Help the user evaluate THIS COCKTAIL ONLY.

If the user asks for a different taste, style,
base spirit, strength or experience, recommend
appropriate alternatives from the cocktail library.

Do not recommend cocktails already used elsewhere
in the current menu.

When suggesting a replacement, return the exact
database cocktail name inside recommended_cocktails.

Do not create the event.
`
        : `
CURRENT FORM FIELD:
key: ${current?.key}
label: ${current?.title}

You are helping with THIS FIELD ONLY.
Do not ask about unrelated fields.
If the user gives enough information to fill this field,
return a suggested update using exactly this field key.
Do not claim that you already changed the form.
`;

    const scopedMessage = `
${focusText}

Reply in the same language as the user's message below.
If the user writes Hebrew, reply naturally in Hebrew.
If the user writes English, reply in English.

USER MESSAGE:
${userMessage}
`.trim();

    try {
      const result = await api.eventBuilderAdvice({
        message: scopedMessage,
        draft: form,
        history: turns.slice(-8),
      });

      const nextAdvice: Advice = {
        message: result.message,
        updates: result.updates,
        recommended_cocktails: result.recommended_cocktails,
      };

      setAdvice(nextAdvice);

      saveTurns(conversationKey, [
        ...nextTurns,
        {
          role: "assistant",
          content: result.message,
        },
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Happy Hour AI could not respond."
      );
    } finally {
      setBusy(false);
    }
  }

  function applyCurrentSuggestion() {
    if (!advice || !current) return;

    const value = advice.updates[current.key];

    if (value === undefined || value === null) return;

    update(current.key, String(value));

    setAdvice((existing) =>
      existing
        ? {
            ...existing,
            updates: {},
          }
        : existing
    );
  }

  async function getFinalMenu() {
    const count = Number(form.cocktail_count) || 3;

    const result = await api.eventBuilderAdvice({
      message:
        `Build the final cocktail menu for this event. ` +
        `Return exactly ${count} cocktails from the available cocktail library. ` +
        `Use the complete draft. Respect all preferences. ` +
        `Do not ask another question. Do not invent cocktail names.`,
      draft: form,
      history: turns.slice(-8),
    });

    if (result.recommended_cocktails.length !== count) {
      throw new Error(
        "Happy Hour AI could not build a complete menu yet. " +
          "Go back to Cocktail style and add a little more direction."
      );
    }

    return result.recommended_cocktails;
  }

  function keepCurrentCocktail() {
    setAdvice(null);
    setText("");
    setStepIndex((index) =>
      Math.min(index + 1, finalReviewIndex)
    );
  }

  function applyCocktailSuggestion(name: string) {
    if (!isMenuReview || menuIndex < 0) return;

    const normalized = name.trim().toLowerCase();

    const duplicate = menuCocktails.some(
      (cocktail, index) =>
        index !== menuIndex &&
        cocktail.trim().toLowerCase() === normalized
    );

    if (duplicate) {
      setError(
        `${name} is already in the menu. Choose another cocktail.`
      );
      return;
    }

    setMenuCocktails((existing) =>
      existing.map((cocktail, index) =>
        index === menuIndex ? name : cocktail
      )
    );

    setError("");
    setAdvice(null);
    setText("");
    saveTurns(`cocktail-${menuIndex}`, []);
  }

  async function replaceCurrentCocktail() {
    if (
      !isMenuReview ||
      menuIndex < 0 ||
      !currentCocktail ||
      menuBusy
    ) {
      return;
    }

    setMenuBusy(true);
    setError("");

    const otherCocktails = menuCocktails.filter(
      (_, index) => index !== menuIndex
    );

    try {
      const result = await api.eventBuilderAdvice({
        message: `
Replace this cocktail in the proposed menu:

${currentCocktail}

Current other cocktails:
${otherCocktails.join(", ") || "None"}

Preferences:
${form.preferences || "No explicit preferences"}

Choose exactly ONE replacement cocktail.

Requirements:
- Respect the complete event draft.
- Respect taste preferences and exclusions.
- Do not choose ${currentCocktail}.
- Do not choose any cocktail already in the menu.
- Use only an exact cocktail name from the database.
- Return the replacement in recommended_cocktails.
- Briefly explain why it is a better alternative.
`.trim(),
        draft: {
          ...form,
          cocktail_count: "1",
        },
        history: turns.slice(-8),
      });

      const used = new Set(
        otherCocktails.map((name) =>
          name.trim().toLowerCase()
        )
      );

      const replacement = result.recommended_cocktails.find(
        (name) =>
          name.trim().toLowerCase() !==
            currentCocktail.trim().toLowerCase() &&
          !used.has(name.trim().toLowerCase())
      );

      if (!replacement) {
        throw new Error(
          "Happy Hour AI could not find a different cocktail. Try asking for a specific taste or style."
        );
      }

      setMenuCocktails((existing) =>
        existing.map((cocktail, index) =>
          index === menuIndex
            ? replacement
            : cocktail
        )
      );

      setAdvice({
        message: result.message,
        updates: {},
        recommended_cocktails:
          result.recommended_cocktails,
      });

      saveTurns(`cocktail-${menuIndex}`, [
        {
          role: "assistant",
          content: result.message,
        },
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not replace the cocktail."
      );
    } finally {
      setMenuBusy(false);
    }
  }

  async function buildEvent() {
    if (creating) return;

    const guests = Number(form.guest_count);
    const budget = Number(form.budget);

    if (!Number.isFinite(guests) || guests < 1) {
      setError("Please add a valid guest count before building the event.");
      return;
    }

    if (!Number.isFinite(budget) || form.budget.trim() === "" || budget < 0) {
      setError("Please add a valid budget before building the event.");
      return;
    }

    setCreating(true);
    setError("");

    let createdEventId: string | null = null;

    try {
      const cocktailCount = Number(form.cocktail_count) || 3;

      const recommended = menuCocktails;

      if (recommended.length !== cocktailCount) {
        throw new Error(
          "Please review the complete cocktail menu before building the event."
        );
      }

      setCreatingStage("Creating your event…");

      const eventName =
        form.name.trim() ||
        `${
          form.event_type === "corporate"
            ? "Company Happy Hour"
            : "Cocktail Event"
        } · ${guests} guests`;

      const brief = [
        `Event type: ${form.event_type}.`,
        `Requested cocktails: ${cocktailCount}.`,
        form.preferences.trim()
          ? `Preferences: ${form.preferences.trim()}.`
          : "",
        `AI menu: ${recommended.join(", ")}.`,
      ]
        .filter(Boolean)
        .join(" ");

      const created = await api.createEvent({
        name: eventName,
        company_name: form.company_name.trim() || undefined,
        event_date: form.event_date || undefined,
        location: form.location.trim() || undefined,
        guest_count: guests,
        budget,
        duration_hours: Number(form.duration_hours),
        expected_drinks_per_guest: Number(
          form.expected_drinks_per_guest
        ),
        non_alcoholic_pct: Number(form.non_alcoholic_pct),
        theme: "mixed",
        ai_request: brief,
        waste_buffer_pct: 0.08,
      });

      createdEventId = created.id;

      setCreatingStage("Adding the cocktail menu…");

      const library = await api.getCocktails({
        page_size: "200",
      });

      const byName = new Map(
        library.items.map((cocktail) => [
          cocktail.name.trim().toLowerCase(),
          cocktail,
        ])
      );

      const selected = recommended.map((name) =>
        byName.get(name.trim().toLowerCase())
      );

      if (selected.some((cocktail) => !cocktail)) {
        throw new Error(
          "One of the recommended cocktails was not found in the cocktail library."
        );
      }

      const validSelected = selected.filter(Boolean) as Array<
        (typeof library.items)[number]
      >;

      const allocation = 1 / validSelected.length;

      const menu = validSelected.map((cocktail, index) => ({
        cocktail_id: cocktail.id,
        allocation_pct:
          index === validSelected.length - 1
            ? 1 - allocation * (validSelected.length - 1)
            : allocation,
        ai_rationale:
          "Selected by Happy Hour AI during guided event setup.",
      }));

      await api.setMenu(created.id, menu);

      setCreatingStage("Calculating quantities and costs…");

      await api.calculate(created.id);

      setCreatingStage("Your event is ready ✓");

      router.push(`/events/${created.id}`);
    } catch (err) {
      if (createdEventId) {
        await api.deleteEvent(createdEventId).catch(() => {});
      }

      setError(
        err instanceof Error ? err.message : "Could not build the event."
      );

      setCreating(false);
      setCreatingStage("");
    }
  }

  const currentSuggestion =
    current && advice ? advice.updates[current.key] : undefined;

  const progress = ((stepIndex + 1) / totalSteps) * 100;

  return (
    <main className="w-full max-w-[1160px] mx-auto px-5 md:px-8 py-8 md:py-10">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-3 hover:text-ink mb-6"
      >
        <ArrowLeft size={14} />
        Events
      </Link>

      <header className="mb-7">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-accent-line bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent mb-2.5">
          <Sparkles size={11} />
          Guided by Happy Hour AI
        </div>

        <h1 className="text-[30px] font-semibold tracking-[-.025em] text-ink">
          Create your event
        </h1>

        <p className="mt-2 max-w-[650px] text-[14px] leading-relaxed text-ink-3">
          We’ll go through the event one decision at a time.
          You can ask Happy Hour AI for help at any step.
        </p>
      </header>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_370px] gap-6 items-start">
        <section className="rounded-[18px] border border-line bg-surface overflow-hidden">
          <div className="border-b border-line px-6 py-5">
            <div className="flex items-center justify-between gap-4">
              <div className="text-[12px] font-medium text-ink-3">
                {isReview
                  ? "Final review"
                  : isMenuReview
                    ? `Cocktail ${menuIndex + 1} of ${cocktailTarget}`
                    : `Step ${stepIndex + 1} of ${STEPS.length}`}
              </div>

              <div className="text-[11px] text-ink-4">
                {Math.round(progress)}%
              </div>
            </div>

            <div className="mt-3 h-1.5 rounded-full bg-canvas overflow-hidden">
              <div
                className="h-full rounded-full bg-accent transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {!isReview && current && (
            <div className="p-6 md:p-8">
              <div className="max-w-[650px]">
                <div className="text-[12px] font-medium text-accent mb-2">
                  {current.title}
                </div>

                <h2 className="text-[23px] font-semibold tracking-[-.02em] text-ink">
                  {current.question}
                </h2>

                <div className="mt-4 rounded-xl bg-canvas px-4 py-3.5">
                  <div className="flex gap-2.5">
                    <CircleHelp
                      size={15}
                      className="mt-0.5 shrink-0 text-accent"
                    />

                    <div>
                      <p className="text-[12.5px] leading-relaxed text-ink-3">
                        {current.tip}
                      </p>

                      {current.example && (
                        <p
                          dir="auto"
                          className="mt-2 text-[11.5px] text-ink-4"
                        >
                          {current.example}
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-6">
                  {current.type === "select" && (
                    <select
                      autoFocus
                      value={form[current.key]}
                      onChange={(e) => {
                        update(current.key, e.target.value);
                        window.setTimeout(() => {
                          nextStep();
                        }, 120);
                      }}
                      className={inputClass}
                    >
                      {current.options?.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  )}

                  {current.type === "textarea" && (
                    <textarea
                      autoFocus
                      dir="auto"
                      rows={5}
                      value={form[current.key]}
                      onChange={(e) => {
                          update(current.key, e.target.value);

                          if (current.type === "date") {
                            window.setTimeout(() => {
                              nextStep();
                            }, 120);
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            nextStep();
                          }
                        }}
                        placeholder={current.placeholder}
                      className={`${inputClass} resize-none`}
                    />
                  )}

                  {current.type !== "select" &&
                    current.type !== "textarea" && (
                      <input
                        autoFocus
                        dir={
                          current.type === "text" ? "auto" : undefined
                        }
                        type={current.type}
                        min={current.type === "number" ? "0" : undefined}
                        value={form[current.key]}
                        onChange={(e) =>
                          update(current.key, e.target.value)
                        }
                        placeholder={current.placeholder}
                        className={inputClass}
                      />
                    )}

                  {stepError && (
                    <div className="mt-2 text-[11.5px] text-red-600">
                      {stepError}
                    </div>
                  )}
                </div>

                <div className="mt-7 flex items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={previousStep}
                    disabled={stepIndex === 0}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-line px-4 py-2.5 text-[12.5px] font-medium text-ink-2 hover:bg-canvas disabled:opacity-30"
                  >
                    <ChevronLeft size={14} />
                    Back
                  </button>

                  <div className="flex items-center gap-2">
                    {!current.required &&
                      !form[current.key].trim() && (
                        <button
                          type="button"
                          onClick={nextStep}
                          className="rounded-xl px-4 py-2.5 text-[12.5px] font-medium text-ink-3 hover:bg-canvas"
                        >
                          Skip
                        </button>
                      )}

                    <button
                      type="button"
                      onClick={() => void nextStep()}
                      disabled={menuBusy}
                      className="inline-flex items-center gap-2 rounded-xl bg-ink px-5 py-2.5 text-[12.5px] font-medium text-white hover:bg-ink-2 disabled:opacity-40"
                    >
                      {menuBusy && current?.key === "preferences"
                        ? "Choosing cocktails…"
                        : current?.key === "preferences"
                          ? "Choose my cocktails"
                          : "Next"}
                      {!menuBusy && <ArrowRight size={14} />}
                    </button>
                  </div>
                </div>
              </div>

              {stepIndex > 0 && (
                <div className="mt-8 border-t border-line pt-5">
                  <div className="text-[10.5px] font-medium uppercase tracking-wide text-ink-4 mb-2.5">
                    Already filled
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {STEPS.slice(0, stepIndex).map((step, index) => (
                      <button
                        type="button"
                        key={step.key}
                        onClick={() => goToStep(index)}
                        className="rounded-full border border-line bg-canvas px-3 py-1.5 text-[11px] text-ink-2 hover:border-accent-line"
                      >
                        {step.title}: {valueFor(step)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}


          {isMenuReview && currentCocktail && (
            <div className="p-6 md:p-8">
              <div className="max-w-[700px]">
                <div className="text-[12px] font-medium text-accent mb-2">
                  Cocktail {menuIndex + 1} of {cocktailTarget}
                </div>

                <h2 className="text-[27px] font-semibold tracking-[-.02em] text-ink">
                  {currentCocktail}
                </h2>

                <p className="mt-2 text-[13px] leading-relaxed text-ink-3">
                  Happy Hour AI selected this cocktail using your event
                  details and cocktail preferences. Keep it, replace it,
                  or ask the AI to adjust this choice.
                </p>

                {form.preferences.trim() && (
                  <div
                    dir="auto"
                    className="mt-5 rounded-xl bg-canvas px-4 py-3 text-[12px] text-ink-3"
                  >
                    <span className="font-medium text-ink">
                      Your brief:{" "}
                    </span>
                    {form.preferences}
                  </div>
                )}

                <div className="mt-6 rounded-xl border border-line p-4">
                  <div className="text-[10.5px] uppercase tracking-wide text-ink-4">
                    Proposed menu
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {menuCocktails.map((name, index) => (
                      <span
                        key={`${name}-${index}`}
                        className={
                          index === menuIndex
                            ? "rounded-full bg-accent px-3 py-1.5 text-[11.5px] font-medium text-white"
                            : "rounded-full bg-canvas px-3 py-1.5 text-[11.5px] text-ink-3"
                        }
                      >
                        {index + 1}. {name}
                      </span>
                    ))}
                  </div>
                </div>

                {error && (
                  <div
                    dir="auto"
                    className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[12px] text-red-700"
                  >
                    {error}
                  </div>
                )}

                <div className="mt-7 flex flex-wrap items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={previousStep}
                    disabled={menuBusy}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-line px-4 py-2.5 text-[12.5px] font-medium text-ink-2 hover:bg-canvas disabled:opacity-30"
                  >
                    <ChevronLeft size={14} />
                    Back
                  </button>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void replaceCurrentCocktail()}
                      disabled={menuBusy}
                      className="rounded-xl border border-line px-4 py-2.5 text-[12.5px] font-medium text-ink hover:bg-canvas disabled:opacity-40"
                    >
                      {menuBusy ? "Finding another…" : "Replace"}
                    </button>

                    <button
                      type="button"
                      onClick={keepCurrentCocktail}
                      disabled={menuBusy}
                      className="inline-flex items-center gap-2 rounded-xl bg-ink px-5 py-2.5 text-[12.5px] font-medium text-white hover:bg-ink-2 disabled:opacity-40"
                    >
                      <Check size={14} />
                      {menuIndex === cocktailTarget - 1
                        ? "Keep & review event"
                        : "Keep & next cocktail"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {isReview && (
            <div className="p-6 md:p-8">
              <div className="max-w-[700px]">
                <div className="text-[12px] font-medium text-accent mb-2">
                  Review
                </div>

                <h2 className="text-[23px] font-semibold tracking-[-.02em] text-ink">
                  Ready to build your event?
                </h2>

                <p className="mt-2 text-[13px] text-ink-3">
                  Check the details below. You can edit any field before we
                  create the event and build the cocktail menu.
                </p>

                <div className="mt-6 rounded-xl border border-accent-line bg-accent-soft p-4">
                  <div className="flex items-center gap-2">
                    <GlassWater size={14} className="text-accent" />
                    <span className="text-[12px] font-medium text-ink">
                      Approved cocktail menu
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {menuCocktails.map((name, index) => (
                      <span
                        key={`${name}-${index}`}
                        className="rounded-full bg-surface px-3 py-1.5 text-[11.5px] font-medium text-ink-2"
                      >
                        {index + 1}. {name}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="mt-4 rounded-xl border border-line overflow-hidden">
                  {STEPS.map((step, index) => (
                    <button
                      type="button"
                      key={step.key}
                      onClick={() => goToStep(index)}
                      className="w-full flex items-center justify-between gap-4 border-b border-line last:border-0 px-4 py-3 text-left hover:bg-canvas"
                    >
                      <span className="text-[11.5px] text-ink-4">
                        {step.title}
                      </span>

                      <span
                        dir="auto"
                        className="text-[12.5px] font-medium text-ink"
                      >
                        {valueFor(step)}
                      </span>
                    </button>
                  ))}
                </div>

                {error && (
                  <div
                    dir="auto"
                    className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[12px] text-red-700"
                  >
                    {error}
                  </div>
                )}

                {creating && (
                  <div className="mt-4 rounded-xl border border-accent-line bg-accent-soft px-4 py-3 text-[12px] text-accent">
                    {creatingStage}
                  </div>
                )}

                <div className="mt-6 flex items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={previousStep}
                    disabled={creating}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-line px-4 py-2.5 text-[12.5px] font-medium text-ink-2 hover:bg-canvas disabled:opacity-30"
                  >
                    <ChevronLeft size={14} />
                    Back
                  </button>

                  <button
                    type="button"
                    onClick={buildEvent}
                    disabled={creating}
                    className="inline-flex items-center gap-2 rounded-xl bg-ink px-6 py-3 text-[13px] font-medium text-white hover:bg-ink-2 disabled:opacity-40"
                  >
                    {creating ? "Building your event…" : "Build my event"}

                    {!creating && <ArrowRight size={14} />}
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>

        <aside className="lg:sticky lg:top-6">
          <div className="rounded-[18px] border border-line bg-surface overflow-hidden shadow-sm">
            <div className="border-b border-line px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent-soft text-accent">
                  <Sparkles size={16} />
                </div>

                <div>
                  <div className="text-[13.5px] font-semibold text-ink">
                    Happy Hour AI
                  </div>

                  <div className="text-[11px] text-ink-4">
                    {isReview
                      ? "Reviewing your event"
                      : isMenuReview
                        ? `Reviewing cocktail ${menuIndex + 1} of ${cocktailTarget}`
                        : `Helping with ${current?.title}`}
                  </div>
                </div>
              </div>
            </div>

            <div className="p-5">
              <div className="rounded-xl bg-canvas px-4 py-3.5">
                <div className="text-[11px] font-medium text-accent">
                  {isReview
                    ? "Final review"
                    : isMenuReview
                      ? currentCocktail
                      : current?.title}
                </div>

                <p
                  dir="auto"
                  className="mt-1.5 text-[12px] leading-relaxed text-ink-3"
                >
                  {isReview
                    ? "You can ask me to review the setup or explain any choice before you build the event."
                    : isMenuReview
                      ? "Ask why this cocktail fits, request a different taste, or describe what you want instead."
                      : current?.tip}
                </p>

                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    send(
                      isReview
                        ? "Review my complete event setup. Tell me if anything looks unusual before I build it. Do not change anything automatically."
                        : isMenuReview
                          ? `Explain why ${currentCocktail} fits my event and preferences. If there is a meaningful concern, tell me.`
                          : current?.helpPrompt,
                      isReview
                        ? "Review my event before I build it"
                        : isMenuReview
                          ? `Why did you choose ${currentCocktail}?`
                          : `Help me with ${current?.title}`
                    )
                  }
                  className="mt-3 inline-flex items-center gap-1.5 text-[11.5px] font-medium text-accent hover:underline disabled:opacity-40"
                >
                  <Sparkles size={12} />
                  {isReview
                    ? "Ask AI to review"
                    : isMenuReview
                      ? "Ask AI about this cocktail"
                      : "Ask AI about this"}
                </button>
              </div>

              {turns.length > 0 && (
                <div className="mt-4 max-h-[310px] overflow-y-auto flex flex-col gap-2.5">
                  {turns.map((turn, index) => (
                    <div
                      key={index}
                      dir="auto"
                      className={
                        turn.role === "user"
                          ? "self-end max-w-[88%] rounded-xl rounded-br-sm bg-ink px-3 py-2 text-[12px] leading-relaxed text-white"
                          : "self-start max-w-[92%] rounded-xl rounded-tl-sm bg-canvas px-3 py-2.5 text-[12px] leading-relaxed text-ink-2"
                      }
                    >
                      {turn.content}
                    </div>
                  ))}
                </div>
              )}

              {busy && (
                <div className="mt-3 flex items-center gap-2 text-[11.5px] text-ink-4">
                  <Sparkles
                    size={12}
                    className="animate-pulse text-accent"
                  />
                  Thinking…
                </div>
              )}

              {!isReview &&
                currentSuggestion !== undefined &&
                currentSuggestion !== null && (
                  <div className="mt-4 rounded-xl border border-accent-line bg-accent-soft p-3.5">
                    <div className="text-[11px] font-medium text-accent">
                      Suggested value
                    </div>

                    <div
                      dir="auto"
                      className="mt-1 text-[13px] font-medium text-ink"
                    >
                      {String(currentSuggestion)}
                    </div>

                    <button
                      type="button"
                      onClick={applyCurrentSuggestion}
                      className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[11.5px] font-medium text-white"
                    >
                      <Check size={12} />
                      Apply to {current?.title}
                    </button>
                  </div>
                )}

              {advice &&
                advice.recommended_cocktails.length > 0 &&
                (current?.key === "preferences" || isReview) && (
                  <div className="mt-4 rounded-xl border border-line p-3.5">
                    <div className="flex items-center gap-2 mb-2.5">
                      <GlassWater size={13} className="text-accent" />

                      <span className="text-[11.5px] font-medium text-ink">
                        Suggested menu
                      </span>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {advice.recommended_cocktails.map((name) =>
                      isMenuReview ? (
                        <button
                          type="button"
                          key={name}
                          onClick={() => applyCocktailSuggestion(name)}
                          className="rounded-full bg-canvas px-2.5 py-1 text-[11.5px] text-ink-2 hover:bg-accent-soft hover:text-accent"
                        >
                          Use {name}
                        </button>
                      ) : (
                        <span
                          key={name}
                          className="rounded-full bg-canvas px-2.5 py-1 text-[11.5px] text-ink-2"
                        >
                          {name}
                        </span>
                      )
                    )}
                    </div>
                  </div>
                )}

              <div className="mt-4 flex items-end gap-2 rounded-xl border border-line-2 px-3 py-2 focus-within:border-accent">
                <textarea
                  dir="auto"
                  rows={1}
                  value={text}
                  disabled={busy}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  placeholder={
                    isReview
                      ? "Ask about the event… אפשר בעברית"
                      : isMenuReview
                        ? `Ask about ${currentCocktail}… אפשר בעברית`
                        : `Ask about ${current?.title}… אפשר בעברית`
                  }
                  className="flex-1 resize-none bg-transparent text-[12.5px] outline-none placeholder:text-ink-4"
                />

                <button
                  type="button"
                  onClick={() => send()}
                  disabled={busy || !text.trim()}
                  className="grid h-7 w-7 place-items-center rounded-lg bg-ink text-white disabled:opacity-30"
                >
                  <ArrowUp size={13} />
                </button>
              </div>

              {error && !isReview && (
                <div
                  dir="auto"
                  className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-[11.5px] text-red-700"
                >
                  {error}
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}

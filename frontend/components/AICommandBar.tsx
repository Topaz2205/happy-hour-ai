"use client";

import { useState, useRef, useEffect } from "react";
import { Sparkles, ArrowUp, CornerDownLeft, Languages } from "lucide-react";
import { cx, Chip } from "./ui";

const CHIPS = [
  { label: "Corporate happy hour", prompt: "Corporate happy hour for 120 people, 3 cocktails, budget ₪9,000" },
  { label: "Wedding", prompt: "Wedding for 180 guests, margaritas and something with gin, budget ₪14,000" },
  { label: "Private party", prompt: "Private party for 40 people, mojitos and negronis" },
  { label: "Cocktail workshop", prompt: "Cocktail workshop for 25 people, 4 classic cocktails" },
  { label: "Rooftop event", prompt: "Rooftop event for 80 guests, light refreshing cocktails, budget ₪6,000" },
  { label: "Summer launch", prompt: "Summer product launch for 150 guests, one signature cocktail plus two classics" },
];

/**
 * The front door.
 *
 * This is the only surface in the product that carries a gradient, a coloured
 * focus ring and a shadow at once. That is deliberate and it is the reason the
 * rest of the app is kept flat: emphasis only exists where something else is
 * restrained, and everything here is spent on the single action the product is
 * for — describing an event in your own words.
 */
export default function AICommandBar({
  onSubmit, busy, autoFocus = true, compact = false,
}: {
  onSubmit: (text: string) => void;
  busy?: boolean;
  autoFocus?: boolean;
  compact?: boolean;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with the content instead of scrolling inside a fixed box — people
  // paste multi-line briefs in here.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 220) + "px";
  }, [text]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  function send() {
    const t = text.trim();
    if (!t || busy) return;
    onSubmit(t);
  }

  const ready = text.trim().length > 0 && !busy;

  return (
    <div>
      <div
        className={cx(
          "hh-hero-surface border border-line-2 rounded-[16px]",
          "shadow-[var(--shadow-hero)] transition-shadow",
          "focus-within:border-accent/45",
          "focus-within:shadow-[0_0_0_3px_var(--color-accent-soft),var(--shadow-hero)]",
          busy && "opacity-70 pointer-events-none"
        )}
      >
        <div className={cx("flex items-start gap-3", compact ? "px-4 pt-3.5" : "px-5 pt-5")}>
          <span className="mt-[3px] shrink-0 w-7 h-7 grid place-items-center rounded-lg bg-accent-soft border border-accent-line">
            <Sparkles size={15} strokeWidth={1.75} className="text-accent" />
          </span>
          <textarea
            ref={ref}
            rows={compact ? 1 : 3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            dir="auto"
            disabled={busy}
            placeholder="Plan a cocktail event for 180 guests, corporate event, budget ₪10,000, 4 cocktails including a signature drink…"
            aria-label="Describe the event you're planning"
            className={cx(
              "flex-1 min-w-0 resize-none bg-transparent outline-none",
              "focus:outline-none focus-visible:outline-none",
              compact ? "text-[14px]" : "text-[15px]",
              "leading-relaxed text-ink placeholder:text-ink-4 py-[3px]"
            )}
          />
        </div>

        <div
          className={cx(
            "flex items-center justify-between gap-3",
            compact ? "px-4 pb-3 pt-1.5" : "px-5 pb-4 pt-2"
          )}
        >
          <span className="text-[11.5px] text-ink-4 inline-flex items-center gap-1.5 min-w-0">
            <CornerDownLeft size={11} strokeWidth={2} className="shrink-0" />
            <span>to plan</span>
            <span className="text-line-2">·</span>
            <Languages size={11} strokeWidth={2} className="shrink-0" />
            <span className="truncate">Hebrew or English</span>
          </span>
          <button
            onClick={send}
            disabled={!ready}
            aria-label="Plan event"
            className={cx(
              "h-9 px-3.5 inline-flex items-center gap-1.5 rounded-[10px] shrink-0",
              "text-[13px] font-medium transition-all",
              ready
                ? "bg-accent text-white hover:bg-accent-hi shadow-[var(--shadow-xs)]"
                : "bg-sunk text-ink-4 cursor-not-allowed"
            )}
          >
            Plan
            <ArrowUp size={14} strokeWidth={2.25} />
          </button>
        </div>
      </div>

      {!compact && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {CHIPS.map((c) => (
            <Chip key={c.label} disabled={busy} onClick={() => setText(c.prompt)}>
              {c.label}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}

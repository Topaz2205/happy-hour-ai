"use client";

import { Check, Loader2 } from "lucide-react";
import { cx } from "./ui";

/**
 * What the agent is doing, at the level a person cares about.
 *
 * Deliberately operational, never internal reasoning: "Calculating ingredient
 * quantities", not the arithmetic. The steps mirror the real pipeline the
 * request goes through, so the list is honest about the work rather than
 * theatre timed to a spinner.
 */
export const PLAN_STEPS = [
  "Understanding your event",
  "Choosing the cocktail menu",
  "Calculating ingredient quantities",
  "Matching bottle and package sizes",
  "Costing the shopping list",
  "Finding where to buy",
];

export default function AgentActivity({
  steps = PLAN_STEPS,
  activeIndex,
  done = false,
  title = "Happy Hour AI",
  className,
}: {
  steps?: string[];
  activeIndex: number;
  done?: boolean;
  title?: string;
  className?: string;
}) {
  return (
    <div className={cx("bg-surface border border-line rounded-[10px] p-4", className)}>
      <div className="flex items-center gap-2 mb-3">
        <span className="relative flex w-1.5 h-1.5">
          {!done && (
            <span className="absolute inline-flex w-full h-full rounded-full bg-accent hh-pulse" />
          )}
          <span
            className={cx(
              "relative inline-flex w-1.5 h-1.5 rounded-full",
              done ? "bg-good" : "bg-accent"
            )}
          />
        </span>
        <span className="text-[12.5px] font-medium text-ink">{title}</span>
      </div>

      <ol className="flex flex-col gap-[7px]">
        {steps.map((step, i) => {
          const complete = done || i < activeIndex;
          const active = !done && i === activeIndex;
          return (
            <li key={step} className="flex items-center gap-2.5">
              <span className="w-4 h-4 grid place-items-center shrink-0">
                {complete ? (
                  <Check size={13} strokeWidth={2.5} className="text-good" />
                ) : active ? (
                  <Loader2 size={13} strokeWidth={2.25} className="text-accent animate-spin" />
                ) : (
                  <span className="w-[6px] h-[6px] rounded-full border border-line-2" />
                )}
              </span>
              <span
                className={cx(
                  "text-[13px] leading-tight transition-colors",
                  complete ? "text-ink-2" : active ? "text-ink font-medium" : "text-ink-4"
                )}
              >
                {step}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/**
 * Advances through the step list while a request is in flight.
 *
 * The steps are real, but their timing is not measured — the backend returns
 * one response, not progress events. It therefore stops on the last step
 * rather than claiming completion the server has not confirmed.
 */
export function useAgentSteps(active: boolean, steps: string[] = PLAN_STEPS) {
  const [i, setI] = useStateSafe(0);

  useIntervalWhen(
    () => setI((n) => Math.min(n + 1, steps.length - 1)),
    active ? 900 : null,
    () => setI(0)
  );

  return i;
}

// Small local hooks, kept here so the component file stays self-contained.
import { useState, useEffect, useRef } from "react";

function useStateSafe(initial: number) {
  return useState(initial);
}

function useIntervalWhen(fn: () => void, ms: number | null, onStop: () => void) {
  const saved = useRef(fn);
  const stop = useRef(onStop);
  saved.current = fn;
  stop.current = onStop;

  useEffect(() => {
    if (ms == null) {
      stop.current();
      return;
    }
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [ms]);
}

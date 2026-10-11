"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Printer,
  ChefHat,
  AlertTriangle,
  Beaker,
} from "lucide-react";

import {
  api,
  type Event,
  type PrepSheet,
  type PrepCocktail,
} from "@/lib/api";

import {
  Card,
  Button,
  EmptyState,
  Note,
  Skeleton,
} from "@/components/ui";

import BatchBuilder from "./BatchBuilder";

const DEFAULT_BATCH_METHOD =
  "Take a container and pour in all the ingredients. Add ice to the container just before the event.";

const NO_BATCH_METHOD =
  "This cocktail cannot be prepared as a batch. Prepare it only in the glass.";

// HH_SYRUP_PREP_HELPER
function syrupPrepInstruction(name: string): string | null {
  const key = name.toLowerCase();

  if (key.includes("simple syrup")) {
    return (
      "1:1 Simple Syrup — combine 1 part sugar with 1 part hot water. " +
      "Stir until completely dissolved, allow to cool, bottle and keep chilled until the event."
    );
  }

  if (key.includes("rich syrup")) {
    return (
      "2:1 Rich Syrup — combine 2 parts sugar with 1 part hot water. " +
      "Stir until completely dissolved, allow to cool, bottle and keep chilled until the event."
    );
  }

  if (key.includes("syrup")) {
    return (
      "Prepare this syrup before the event and keep it chilled. " +
      "A specific house recipe has not yet been defined for this syrup."
    );
  }

  return null;
}


export default function PrepSection({
  event,
  eventId,
}: {
  event: Event;
  eventId: string;
  onChanged?: () => void;
}) {
  const [sheet, setSheet] = useState<PrepSheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    setSheet(null);
    setError(null);

    api
      .getPrepSheet(eventId)
      .then((s) => {
        if (alive) setSheet(s);
      })
      .catch((e) => {
        if (alive) {
          setError(
            e instanceof Error
              ? e.message
              : "Could not load prep data"
          );
        }
      });

    return () => {
      alive = false;
    };
  }, [eventId, event.menu.length]);

  if (event.menu.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={ChefHat}
          title="Nothing to prepare yet."
          body="Add cocktails on the Menu tab and the prep quantities appear here."
        />
      </Card>
    );
  }

  if (error) {
    return (
      <Note tone="warn" icon={AlertTriangle}>
        {error}
      </Note>
    );
  }

  if (!sheet) {
    return (
      <div className="flex flex-col gap-3">
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-[220px]" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-[15px] font-medium text-ink">
            Prep
          </h2>

          <p className="text-[12.5px] text-ink-3 mt-0.5">
            {sheet.total_drinks} drinks across{" "}
            {sheet.cocktails.length}{" "}
            {sheet.cocktails.length === 1
              ? "cocktail"
              : "cocktails"}{" "}
            · quantities include the waste buffer
          </p>
        </div>

        <Link href={`/events/${eventId}/print`}>
          <Button variant="primary" icon={Printer}>
            Print full prep pack
          </Button>
        </Link>
      </div>

      {sheet.cocktails.map((cocktail) => (
        <PrepCard
          key={cocktail.cocktail_id}
          cocktail={cocktail}
          eventId={eventId}
        />
      ))}
    </div>
  );
}

function PrepCard({
  cocktail,
  eventId,
}: {
  cocktail: PrepCocktail;
  eventId: string;
}) {
  const [batching, setBatching] = useState(false);

  const batchAllowed =
    cocktail.batch_allowed !== false;

  const glassMethod =
    cocktail.glass_instruction ??
    cocktail.technique ??
    "No glass preparation method saved.";

  const batchMethod = batchAllowed
    ? cocktail.batch_instruction ??
      DEFAULT_BATCH_METHOD
    : NO_BATCH_METHOD;

  return (
    <Card className="p-0 overflow-hidden">
      {/* HEADER */}
      <div className="px-4 py-3.5 border-b border-line flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h3
            dir="auto"
            className="text-[16px] font-semibold text-ink tracking-[-.015em]"
          >
            {cocktail.name}
          </h3>

          <p className="text-[12px] text-ink-3 mt-0.5">
            {[
              cocktail.glass &&
                `Glass: ${cocktail.glass}`,
              cocktail.garnish &&
                `Garnish: ${cocktail.garnish}`,
            ]
              .filter(Boolean)
              .join("  ·  ") || "—"}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="text-end">
            <div className="text-[22px] font-semibold text-accent tnum leading-none">
              {cocktail.servings}
            </div>

            <div className="text-[11px] text-ink-4 mt-0.5">
              to make
            </div>
          </div>

          {batchAllowed ? (
            <Button
              icon={Beaker}
              onClick={() =>
                setBatching((value) => !value)
              }
            >
              {batching
                ? "Hide batch"
                : "Create batch"}
            </Button>
          ) : (
            <div
              className="rounded-full border border-orange-200 bg-orange-50 px-4 py-2 text-[12px] font-semibold text-orange-700"
              title={
                cocktail.batch_blocked_by?.length
                  ? `Blocked by: ${cocktail.batch_blocked_by.join(
                      ", "
                    )}`
                  : undefined
              }
            >
              GLASS ONLY
            </div>
          )}
        </div>
      </div>

      {/* INGREDIENTS */}
      <div className="px-4 py-3">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="text-[10.5px] uppercase tracking-[.05em] text-ink-3">
              <th className="text-start font-medium pb-1.5">
                Ingredient
              </th>

              <th className="text-end font-medium pb-1.5 w-[90px]">
                Per drink
              </th>

              <th className="text-end font-medium pb-1.5 w-[112px]">
                All {cocktail.servings}
              </th>
            </tr>
          </thead>

          <tbody>
            {cocktail.ingredients.map(
              (line, index) => (
                <tr
                  key={index}
                  className="border-t border-line/70"
                >
                  <td
                    dir="auto"
                    className="py-1.5 pe-2 text-ink"
                  >
                    {line.name}
                  </td>

                  <td className="py-1.5 text-end tnum text-ink-3">
                    {line.per_drink != null
                      ? `${line.per_drink} ${line.unit}`
                      : "—"}
                  </td>

                  <td className="py-1.5 text-end tnum font-medium text-ink">
                    {line.batch_total != null ? (
                      `${line.batch_total.toLocaleString()} ${line.unit}`
                    ) : (
                      <span className="text-warn text-[12px]">
                        {line.note ?? "—"}
                      </span>
                    )}
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>

        {/* GLASS METHOD */}
        <div className="mt-3 pt-3 border-t border-line">
          <h4 className="text-[10.5px] uppercase tracking-[.05em] text-ink-3 mb-1">
            Glass method
          </h4>

          <p
            dir="auto"
            className="text-[13px] text-ink-2 leading-relaxed whitespace-pre-wrap"
          >
            {glassMethod}
          </p>
        </div>

        {/* BATCH METHOD */}
        <div className="mt-3 pt-3 border-t border-line">
          <h4 className="text-[10.5px] uppercase tracking-[.05em] text-ink-3 mb-1">
            Batch method
          </h4>

          <p className="text-[13px] text-ink-2 leading-relaxed whitespace-pre-wrap">
            {batchMethod}
          </p>

          {!batchAllowed &&
            cocktail.batch_blocked_by &&
            cocktail.batch_blocked_by.length > 0 && (
              <p className="mt-1 text-[11.5px] text-ink-4">
                Glass only because of:{" "}
                {cocktail.batch_blocked_by.join(
                  ", "
                )}
              </p>
            )}
        </div>
      </div>

      {/* BATCH BUILDER — ONLY WHEN ALLOWED */}
      {/* HH_SYRUP_PREP_UI */}
      {cocktail.ingredients.some(
        (ingredient) =>
          syrupPrepInstruction(ingredient.name) !== null
      ) && (
        <div className="border-t border-line px-4 py-4">
          <div className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-ink-4">
            Syrup prep
          </div>

          <div className="mt-3 space-y-3">
            {cocktail.ingredients
              .filter(
                (ingredient) =>
                  syrupPrepInstruction(ingredient.name) !== null
              )
              .map((ingredient) => (
                <div
                  key={ingredient.name}
                  className="rounded-xl bg-canvas px-4 py-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-[12.5px] font-medium text-ink">
                      {ingredient.name}
                    </div>

                    {ingredient.batch_total !== null &&
                      ingredient.batch_total !== undefined && (
                        <div className="text-[11.5px] text-ink-3">
                          Need for event:{" "}
                          <span className="font-medium text-ink-2">
                            {Number(
                              ingredient.batch_total
                            ).toLocaleString()}{" "}
                            {ingredient.unit}
                          </span>
                        </div>
                      )}
                  </div>

                  <p className="mt-2 text-[12px] leading-relaxed text-ink-3">
                    {syrupPrepInstruction(ingredient.name)}
                  </p>
                </div>
              ))}
          </div>
        </div>
      )}

      {batchAllowed && batching && (
        <div className="border-t border-line bg-canvas px-4 py-3.5 hh-rise">
          <BatchBuilder
            eventId={eventId}
            cocktailId={cocktail.cocktail_id}
            name={cocktail.name}
            eventServings={cocktail.servings}
          />
        </div>
      )}
    </Card>
  );
}

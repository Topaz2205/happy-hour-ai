"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Printer, ArrowLeft, AlertCircle } from "lucide-react";
import { api, type PrepSheet } from "@/lib/api";
import { Button, Note, Skeleton } from "@/components/ui";

/**
 * The sheet you print and hand to whoever is pouring.
 *
 * This is the only page in the product designed to leave the screen, and that
 * changes what belongs on it. No navigation, no costs, no budget — none of it
 * helps someone standing behind a bar with a shaker. What helps is: which drink,
 * how many, how much of what goes in, and how to make it.
 *
 * Amounts are given three ways because three different people read this. The
 * per-drink figure is for making one to check the balance; the batch total is
 * for mixing ahead; the bottle count is for the person carrying crates in from
 * the car. The same number in the units each of them actually thinks in.
 */
export default function PrepSheetPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const [sheet, setSheet] = useState<PrepSheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getPrepSheet(id)
      .then(setSheet)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the prep sheet"));
  }, [id]);

  if (error) {
    return (
      <main className="max-w-[700px] mx-auto px-5 py-16">
        <Note tone="warn" icon={AlertCircle}>{error}</Note>
        <div className="mt-4">
          <Link href={`/events/${id}`}><Button icon={ArrowLeft}>Back to the event</Button></Link>
        </div>
      </main>
    );
  }

  if (!sheet) {
    return (
      <main className="max-w-[820px] mx-auto px-5 py-10">
        <Skeleton className="h-8 w-72 mb-4" />
        <Skeleton className="h-40 mb-3" />
        <Skeleton className="h-40" />
      </main>
    );
  }

  return (
    <main className="hh-print-root max-w-[820px] mx-auto px-5 md:px-8 py-8 md:py-10">
      <div className="hh-no-print flex items-center justify-between gap-3 mb-7">
        <Link
          href={`/events/${id}`}
          className="inline-flex items-center gap-1.5 text-[13px] text-ink-3 hover:text-ink transition-colors"
        >
          <ArrowLeft size={14} strokeWidth={1.75} /> Back to the event
        </Link>
        <Button variant="primary" icon={Printer} onClick={() => window.print()}>
          Print
        </Button>
      </div>

      <header className="mb-7 pb-5 border-b border-line">
        <h1 dir="auto" className="text-[24px] font-semibold tracking-[-.02em] text-ink">
          {sheet.event_name}
        </h1>
        <p className="mt-1.5 text-[13.5px] text-ink-2">
          {sheet.guests} guests · {sheet.total_drinks} drinks ·{" "}
          {sheet.cocktails.length} {sheet.cocktails.length === 1 ? "cocktail" : "cocktails"} ·{" "}
          {sheet.duration_hours} hours
        </p>
      </header>

      <div className="flex flex-col gap-7">
        {sheet.cocktails.map((c) => (
          <section key={c.cocktail_id} className="hh-keep-together">
            <div className="flex items-baseline justify-between gap-3 flex-wrap mb-1">
              <h2 dir="auto" className="text-[18px] font-semibold text-ink tracking-[-.015em]">
                {c.name}
              </h2>
              <span className="text-[14px] font-medium text-accent tnum">
                make {c.servings}
              </span>
            </div>

            {(c.glass || c.garnish) && (
              <p className="text-[12.5px] text-ink-3 mb-3">
                {[c.glass && `Glass: ${c.glass}`, c.garnish && `Garnish: ${c.garnish}`]
                  .filter(Boolean).join("  ·  ")}
              </p>
            )}

            <table className="w-full text-[13px] border-collapse">
              <thead>
                <tr className="text-[11px] uppercase tracking-[.05em] text-ink-3">
                  <th className="text-start font-medium pb-1.5 border-b border-line">
                    Ingredient
                  </th>
                  <th className="text-end font-medium pb-1.5 border-b border-line w-[92px]">
                    Per drink
                  </th>
                  <th className="text-end font-medium pb-1.5 border-b border-line w-[110px]">
                    Whole batch
                  </th>
                  <th className="text-end font-medium pb-1.5 border-b border-line w-[128px]">
                    Bottles
                  </th>
                </tr>
              </thead>
              <tbody>
                {c.ingredients.map((l, i) => (
                  <tr key={i} className="border-b border-line/60">
                    <td dir="auto" className="py-1.5 pe-2 text-ink">{l.name}</td>
                    <td className="py-1.5 text-end tnum text-ink-2">
                      {l.per_drink != null ? `${l.per_drink} ${l.unit}` : "—"}
                    </td>
                    <td className="py-1.5 text-end tnum font-medium text-ink">
                      {l.batch_total != null
                        ? `${l.batch_total.toLocaleString()} ${l.unit}`
                        : (l.note ?? "—")}
                    </td>
                    <td className="py-1.5 text-end tnum text-ink-2">
                      {/* Rounded up, because you cannot buy 8.04 bottles. The
                          exact figure sits beside it so nobody wonders where
                          the spare came from. */}
                      {l.bottles != null && l.bottle_size_ml
                        ? `${Math.ceil(l.bottles)} × ${l.bottle_size_ml}ml`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {c.technique && (
              <div className="mt-3">
                <h3 className="text-[11px] uppercase tracking-[.05em] text-ink-3 mb-1">
                  Method
                </h3>
                <p dir="auto" className="text-[13px] text-ink-2 leading-relaxed whitespace-pre-wrap">
                  {c.technique}
                </p>
              </div>
            )}

            {c.non_alc_variant && (
              <div className="mt-2.5">
                <h3 className="text-[11px] uppercase tracking-[.05em] text-ink-3 mb-1">
                  Without alcohol
                </h3>
                <p dir="auto" className="text-[13px] text-ink-2 leading-relaxed">
                  {c.non_alc_variant}
                </p>
              </div>
            )}
          </section>
        ))}
      </div>

      <footer className="mt-9 pt-4 border-t border-line text-[11.5px] text-ink-4">
        Bottle counts are rounded up to whole bottles. Quantities include the
        event&apos;s waste buffer. Prepared with Happy Hour AI.
      </footer>
    </main>
  );
}

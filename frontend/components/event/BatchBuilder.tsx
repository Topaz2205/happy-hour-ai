"use client";

import { useEffect, useState } from "react";
import { Loader2, AlertTriangle, Printer } from "lucide-react";
import { api, type Batch } from "@/lib/api";
import { Button, Note, Chip, cx } from "@/components/ui";

const PRESETS = [10, 20, 50];

/**
 * "How much do I put in for twenty of these."
 *
 * Every number here is computed by app/engine/batch.py against the same
 * canonical recipe the shopping list uses, so a batch sheet and a purchase list
 * can never describe different drinks. Nothing is calculated in this component;
 * it asks the API and renders what comes back.
 *
 * The event's own servings count is offered as a preset alongside the round
 * numbers, because "make the whole lot" is the most common thing someone
 * actually wants and having to type it would be silly.
 */
export default function BatchBuilder({
  eventId, cocktailId, name, eventServings,
}: {
  eventId: string;
  cocktailId: string;
  name: string;
  eventServings: number;
}) {
  const [servings, setServings] = useState(
    PRESETS.includes(eventServings) ? eventServings : 20
  );
  const [custom, setCustom] = useState("");
  const [batch, setBatch] = useState<Batch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    setError(null);
    api.getBatch(eventId, cocktailId, servings)
      .then((b) => { if (alive) setBatch(b); })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : "Could not build the batch");
      })
      .finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [eventId, cocktailId, servings]);

  const options = Array.from(new Set([...PRESETS, eventServings])).sort((a, b) => a - b);

  function applyCustom() {
    const n = parseInt(custom, 10);
    if (Number.isFinite(n) && n > 0) setServings(n);
  }

  return (
    <div>
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <span className="text-[12px] text-ink-3">Batch for</span>
        {options.map((n) => (
          <Chip key={n} active={n === servings} onClick={() => setServings(n)}>
            {n}
            {n === eventServings && <span className="opacity-60"> · all</span>}
          </Chip>
        ))}
        <span className="inline-flex items-center gap-1">
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => { if (e.key === "Enter") applyCustom(); }}
            onBlur={applyCustom}
            inputMode="numeric"
            placeholder="Custom"
            aria-label={`Custom batch size for ${name}`}
            className="w-[74px] h-7 px-2 text-[12.5px] tnum rounded-full border border-line bg-surface focus:border-accent/50 placeholder:text-ink-4"
          />
        </span>
        {busy && <Loader2 size={13} className="text-ink-4 animate-spin" />}
      </div>

      {error && <Note tone="warn" icon={AlertTriangle}>{error}</Note>}

      {batch && !error && (
        <>
          <div className="bg-surface border border-line rounded-[10px] overflow-hidden">
            <table className="w-full text-[13.5px]">
              <tbody>
                {batch.lines.map((l) => (
                  <tr key={l.ingredient_id} className="border-b border-line/70 last:border-0">
                    <td dir="auto" className="py-2 px-3 text-ink">{l.name}</td>
                    <td className="py-2 px-3 text-end">
                      {l.total != null ? (
                        // The quantity is the largest thing in the row. This is
                        // read while pouring, not while browsing.
                        <span className="text-[15px] font-semibold tnum text-ink">
                          {l.total.toLocaleString()}{" "}
                          <span className="text-[12px] font-normal text-ink-3">{l.unit}</span>
                        </span>
                      ) : (
                        <span className="text-[12.5px] text-warn">{l.note}</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-end w-[120px] text-[12px] text-ink-4 tnum">
                      {l.bottles_to_buy != null && l.package_size
                        ? `${l.bottles_to_buy} × ${l.package_size}${l.package_unit ?? "ml"}`
                        : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-2 flex items-center justify-between gap-3 flex-wrap text-[12px] text-ink-4">
            <span>
              {batch.measured_volume_ml != null && (
                <>
                  {batch.measured_volume_ml.toLocaleString()} ml of measured liquid
                  {batch.has_unmeasured && ", before anything added during service"}
                </>
              )}
            </span>
          </div>

          {batch.has_unmeasured && (
            <div className="mt-2">
              {/* Named, not silently dropped. A batch that quietly omits an
                  ingredient is a batch someone makes wrong. */}
              <Note tone="warn" icon={AlertTriangle}>
                Not scaled: {batch.unmeasured.join(", ")}. The master recipe gives
                no measured amount for {batch.unmeasured.length === 1 ? "it" : "these"},
                so nothing has been invented — add during service.
              </Note>
            </div>
          )}
        </>
      )}
    </div>
  );
}

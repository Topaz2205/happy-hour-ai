"use client";

import { useEffect, useState } from "react";
import {
  X, Check, RotateCcw, AlertTriangle, Loader2, Home,
} from "lucide-react";
import { api, type Alternatives } from "@/lib/api";
import { Button, Note, money, money2, cx } from "@/components/ui";

/**
 * Every product this event could use for one ingredient, priced as this event.
 *
 * THE NUMBER THAT MATTERS IS THE EVENT TOTAL, NOT THE BOTTLE PRICE
 * A cheaper bottle in a smaller size can cost more once whole packages are
 * counted. So the event total is the emphasised figure and the bottle price is
 * small grey supporting detail — the layout makes the honest comparison the
 * easy one, rather than relying on someone reading a warning.
 *
 * Choosing here changes this event only. The house recommendation for every
 * other event is untouched, and the badge says which one that is.
 */
export default function ProductAlternatives({
  eventId, ingredientId, onClose, onApplied,
}: {
  eventId: string;
  ingredientId: string;
  onClose: () => void;
  onApplied: () => void;
}) {
  const [data, setData] = useState<Alternatives | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getAlternatives(eventId, ingredientId)
      .then((d) => { if (alive) setData(d); })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : "Could not load alternatives");
      });
    return () => { alive = false; };
  }, [eventId, ingredientId]);

  async function choose(productId: string) {
    setBusy(productId);
    setError(null);
    try {
      // Applying recalculates the event server-side, so the caller only has to
      // reload — every tab then reads the same new truth.
      setData(await api.setEventProduct(eventId, ingredientId, productId));
      onApplied();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not apply that product");
    } finally {
      setBusy(null);
    }
  }

  async function revert() {
    setBusy("revert");
    setError(null);
    try {
      setData(await api.clearEventProduct(eventId, ingredientId));
      onApplied();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not restore the recommendation");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-6">
      <button
        aria-label="Close"
        className="absolute inset-0 bg-ink/25"
        onClick={onClose}
      />
      <div className="relative w-full sm:max-w-[640px] max-h-[86vh] overflow-y-auto bg-surface border border-line rounded-t-[16px] sm:rounded-[16px] shadow-[var(--shadow-md)] hh-rise">
        <header className="sticky top-0 bg-surface border-b border-line px-5 py-3.5 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 dir="auto" className="text-[15px] font-medium text-ink truncate">
              {data?.ingredient_name ?? "Alternatives"}
            </h2>
            {data && (
              <p className="text-[12px] text-ink-3 mt-0.5">
                This event needs {data.required_amount.toLocaleString()} {data.required_unit}
                {data.current_total != null && <> · currently {money2(data.current_total)}</>}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 grid place-items-center rounded-lg text-ink-3 hover:bg-sunk shrink-0"
          >
            <X size={17} />
          </button>
        </header>

        <div className="p-4">
          {error && <div className="mb-3"><Note tone="warn" icon={AlertTriangle}>{error}</Note></div>}

          {!data ? (
            <p className="text-[13px] text-ink-4 py-6 text-center">Loading…</p>
          ) : data.options.length === 0 ? (
            <p className="text-[13px] text-ink-3 py-6 text-center">
              No other priced product is mapped to this ingredient.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {data.options.map((o) => {
                const diff = o.difference_vs_current;
                return (
                  <div
                    key={o.product_id}
                    className={cx(
                      "flex items-center gap-3 px-3.5 py-3 rounded-[10px] border",
                      o.is_current
                        ? "border-accent-line bg-accent-soft"
                        : "border-line bg-canvas"
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span dir="auto" className="text-[13.5px] font-medium text-ink truncate">
                          {o.product_name}
                        </span>
                        {o.is_current && (
                          <span className="text-[10.5px] uppercase tracking-[.05em] text-accent">
                            in use
                          </span>
                        )}
                        {o.is_house_recommendation && !o.is_current && (
                          <span className="inline-flex items-center gap-1 text-[10.5px] uppercase tracking-[.05em] text-ink-4">
                            <Home size={9} strokeWidth={2} /> recommended
                          </span>
                        )}
                      </div>
                      {/* Supporting detail, deliberately quiet: this is the
                          number that misleads if you rank by it. */}
                      <div className="text-[11.5px] text-ink-4 mt-0.5 tnum">
                        {o.packages_required} × {o.package_size}{o.package_unit} at{" "}
                        {money2(o.price_per_package)} each
                        {o.supplier_name && ` · ${o.supplier_name}`}
                      </div>
                    </div>

                    <div className="text-end shrink-0">
                      <div className="text-[15px] font-semibold tnum text-ink leading-none">
                        {money(o.event_total)}
                      </div>
                      <div
                        className={cx(
                          "text-[11.5px] mt-1 tnum",
                          diff == null ? "text-ink-4"
                            : diff < 0 ? "text-good" : diff > 0 ? "text-ink-3" : "text-ink-4"
                        )}
                      >
                        {diff == null ? "for this event"
                          : diff === 0 ? "same"
                          : `${diff < 0 ? "saves " : "adds "}${money(Math.abs(diff))}`}
                      </div>
                    </div>

                    <Button
                      onClick={() => choose(o.product_id)}
                      disabled={o.is_current || busy !== null}
                      icon={busy === o.product_id ? Loader2 : Check}
                    >
                      {o.is_current ? "In use" : "Use"}
                    </Button>
                  </div>
                );
              })}
            </div>
          )}

          {data?.is_overridden && (
            <div className="mt-3 flex items-center justify-between gap-3 flex-wrap pt-3 border-t border-line">
              <p className="text-[12px] text-ink-3">
                This event is using its own choice, not the house recommendation.
              </p>
              <Button icon={RotateCcw} onClick={revert} disabled={busy !== null}>
                Back to recommended
              </Button>
            </div>
          )}

          <p className="mt-3 text-[11.5px] text-ink-4 leading-relaxed">
            Compare the event total, not the bottle price — a cheaper bottle in a
            smaller size can cost more once whole packages are counted. Choosing
            here changes this event only.
          </p>
        </div>
      </div>
    </div>
  );
}
